// EDGECS DERMS/Master C++ : HTTPS auto-enregistrement, multi-gateways,
// commandes MQTT -> DNP3 et telemesures DNP3 -> MQTT.
// PROTOTYPE DE LABORATOIRE - NE PAS CONTROLER UN RESEAU REEL.
#include "common.hpp"
#include "registry.hpp"

#include <drogon/drogon.h>
#include <mqtt/async_client.h>

#include <opendnp3/ConsoleLogger.h>
#include <opendnp3/DNP3Manager.h>
#include <opendnp3/channel/ChannelRetry.h>
#include <opendnp3/channel/IPEndpoint.h>
#include <opendnp3/channel/IChannelListener.h>
#include <opendnp3/logging/LogLevels.h>
#include <opendnp3/master/DefaultMasterApplication.h>
#include <opendnp3/master/ICommandTaskResult.h>
#include <opendnp3/master/IMaster.h>
#include <opendnp3/master/IMasterScan.h>
#include <opendnp3/master/ITaskCallback.h>
#include <opendnp3/master/ISOEHandler.h>
#include <opendnp3/master/MasterStackConfig.h>
#include <opendnp3/app/ClassField.h>
#include <opendnp3/app/AnalogOutput.h>
#include <opendnp3/app/ControlRelayOutputBlock.h>
#include <opendnp3/gen/OperationType.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>

namespace dnp = opendnp3;
using EdgeJson = edgecs::Json;

namespace {

// Ne pas comparer les jetons avec un early-return au premier octet different.
bool constant_time_equal(const std::string& lhs, const std::string& rhs) {
    size_t diff = lhs.size() ^ rhs.size();
    for (size_t i = 0; i < std::max(lhs.size(), rhs.size()); ++i) {
        unsigned char a = i < lhs.size() ? static_cast<unsigned char>(lhs[i]) : 0;
        unsigned char b = i < rhs.size() ? static_cast<unsigned char>(rhs[i]) : 0;
        diff |= static_cast<size_t>(a ^ b);
    }
    return diff == 0;
}

void publish_json(mqtt::async_client& mqtt, const std::string& topic_name, const EdgeJson& obj) {
    auto packet = mqtt::make_message(topic_name, obj.dump());
    packet->set_qos(1);
    mqtt.publish(packet); // publication soumise au client, pas confirmation de livraison a la DER
}

using TelemetrySink = std::function<EdgeJson(const std::string&, const std::string&, std::uint16_t,
                                           const EdgeJson&, std::uint8_t, std::uint64_t)>;
using ConnectionSink = std::function<void(const std::string&, const std::string&)>;

class SessionChannelListener final : public dnp::IChannelListener {
public:
    SessionChannelListener(std::string device, ConnectionSink sink)
        : device_(std::move(device)), sink_(std::move(sink)) {}

    void OnStateChange(dnp::ChannelState state) override {
        state_.store(state);
        try { sink_(device_, state_name(state)); }
        catch (const std::exception& ex) { std::cerr << "Connection state: " << ex.what() << '\n'; }
    }
    std::string state() const { return state_name(state_.load()); }
private:
    static std::string state_name(dnp::ChannelState state) {
        switch (state) {
        case dnp::ChannelState::CLOSED: return "closed";
        case dnp::ChannelState::OPENING: return "opening";
        case dnp::ChannelState::OPEN: return "open";
        case dnp::ChannelState::SHUTDOWN: return "shutdown";
        }
        return "unknown";
    }
    const std::string device_;
    const ConnectionSink sink_;
    std::atomic<dnp::ChannelState> state_{dnp::ChannelState::CLOSED};
};

class ReadCompletion final : public dnp::ITaskCallback {
public:
    ReadCompletion(mqtt::async_client& mqtt, std::string device, std::string request)
        : mqtt_(mqtt), device_(std::move(device)), request_(std::move(request)) {}
    void OnStart() override {}
    void OnDestroyed() override {}
    void OnComplete(dnp::TaskCompletion result) override {
        try {
            auto reply = edgecs::envelope(device_, "*", nullptr, "read_result");
            reply["request_id"] = request_;
            reply["status"] = result == dnp::TaskCompletion::SUCCESS ? "read_completed" : "read_failed";
            reply["dnp3_summary_code"] = static_cast<int>(result);
            publish_json(mqtt_, edgecs::topic(device_, "read_result"), reply);
        } catch (const std::exception& ex) { std::cerr << "Read result: " << ex.what() << '\n'; }
    }
private:
    mqtt::async_client& mqtt_;
    const std::string device_;
    const std::string request_;
};

class GatewaySOE final : public dnp::ISOEHandler {
public:
    GatewaySOE(EdgeJson cfg, mqtt::async_client& client, TelemetrySink sink)
        : cfg_(std::move(cfg)), client_(client), device_(cfg_.at("device_id").get<std::string>()),
          sink_(std::move(sink)) {}

    void BeginFragment(const dnp::ResponseInfo&) override {}
    void EndFragment(const dnp::ResponseInfo&) override {}

    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::Analog>>& vals) override {
        vals.ForeachItem([this](const dnp::Indexed<dnp::Analog>& item) {
            receive("AI", item.index, item.value.value, item.value.flags.value, item.value.time.value);
        });
    }
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::Binary>>& vals) override {
        vals.ForeachItem([this](const dnp::Indexed<dnp::Binary>& item) {
            receive("BI", item.index, item.value.value, item.value.flags.value, item.value.time.value);
        });
    }
    // Autres categories non deployees dans ce prototype : signatures requises par ISOEHandler.
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::DoubleBitBinary>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::Counter>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::FrozenCounter>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::BinaryOutputStatus>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::AnalogOutputStatus>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::OctetString>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::TimeAndInterval>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::BinaryCommandEvent>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::Indexed<dnp::AnalogCommandEvent>>&) override {}
    void Process(const dnp::HeaderInfo&, const dnp::ICollection<dnp::DNPTime>&) override {}

private:
    void receive(const std::string& type, std::uint16_t index, const EdgeJson& value,
                 std::uint8_t flags, std::uint64_t timestamp) {
        try {
            // ATTENTION : la recherche se fait dans LA configuration de CETTE session.
            // AI[0] de bess-01 et AI[0] de bess-02 ne se melangent jamais.
            const auto* point = edgecs::find_index(cfg_, type, index);
            if (!point) {
                std::cerr << "[" << device_ << "] Point inconnu " << type << '[' << index << "]\n";
                return;
            }
            const auto name = point->at("name").get<std::string>();
            // Cache the actual DNP3 observation before attempting MQTT delivery.
            // REST discovery therefore continues to work when the broker is offline.
            auto msg = sink_(device_, type, index, value, flags, timestamp);
            // Ne pas filtrer les valeurs identiques: chaque lecture manuelle
            // doit afficher les valeurs meme si elles n'ont pas change.
            publish_json(client_, edgecs::topic(device_, "telemetry"), msg);
            std::cout << "[" << device_ << "] " << type << '[' << index << "] -> MQTT "
                      << name << " = " << value << '\n';
        } catch (const std::exception& e) {
            std::cerr << "[" << device_ << "] SOE non publie: " << e.what() << '\n';
        }
    }

    const EdgeJson cfg_;
    mqtt::async_client& client_;
    const std::string device_;
    const TelemetrySink sink_;
};

class MasterSession {
public:
    MasterSession(EdgeJson cfg, dnp::DNP3Manager& manager, mqtt::async_client& mqtt,
                  TelemetrySink telemetry, ConnectionSink connection)
        : cfg_(std::move(cfg)), mqtt_(mqtt) {
        const auto device = cfg_.at("device_id").get<std::string>();
        const auto& opts = cfg_.at("dnp3");
        const auto host = opts.at("host").get<std::string>();
        const auto port = opts.at("port").get<std::uint16_t>();
        handler_ = std::make_shared<GatewaySOE>(cfg_, mqtt_, std::move(telemetry));
        listener_ = std::make_shared<SessionChannelListener>(device, std::move(connection));

        channel_ = manager.AddTCPClient(
            "channel-" + device, dnp::levels::NORMAL, dnp::ChannelRetry::Default(),
            { dnp::IPEndpoint(host, port) }, "0.0.0.0", listener_);
        if (!channel_) throw std::runtime_error("Creation du canal DNP3 impossible");

        try {
            dnp::MasterStackConfig stack;
            stack.link.LocalAddr = opts.at("master_address").get<std::uint16_t>();
            stack.link.RemoteAddr = opts.at("outstation_address").get<std::uint16_t>();
            stack.master.responseTimeout = dnp::TimeDuration::Seconds(4);
            stack.master.disableUnsolOnStartup = true;
            stack.master.unsolClassMask = dnp::ClassField::None();
            // Pas de scans de telemesures automatiques, y compris au demarrage.
            stack.master.startupIntegrityClassMask = dnp::ClassField::None();
            stack.master.integrityOnEventOverflowIIN = false;
            stack.master.eventScanOnEventsAvailableClassMask = dnp::ClassField::None();
            stack.master.ignoreRestartIIN = true;
            master_ = channel_->AddMaster("master-" + device, handler_,
                                         dnp::DefaultMasterApplication::Create(), stack);
            if (!master_) throw std::runtime_error("Creation de la station Master impossible");
            master_->SetLogFilters(dnp::levels::NORMAL);
            if (!master_->Enable()) throw std::runtime_error("Activation de la station Master impossible");
            std::cout << "Session DNP3 creee: " << device << " -> " << host << ':' << port << '\n';
        } catch (...) {
            // A failed registration must not leave a manager-owned TCP client running.
            channel_->Shutdown();
            throw;
        }
    }

    std::string connection_state() const { return listener_->state(); }

    void read_measurements(const std::string& request_id) {
        // Requete DNP3 READ de classe 0: l'Outstation renvoie son etat statique AI/BI.
        // Le handler SOE publie les valeurs sur le topic MQTT telemetry.
        auto completion = std::make_shared<ReadCompletion>(mqtt_, cfg_.at("device_id").get<std::string>(), request_id);
        master_->ScanClasses(dnp::ClassField(dnp::PointClass::Class0), handler_, dnp::TaskConfig::With(completion));
        std::cout << '[' << cfg_.at("device_id").get<std::string>()
                  << "] Requete de lecture DNP3 Class 0 envoyee.\n";
    }

    void command(const EdgeJson& msg) {
        const EdgeJson& point = edgecs::validate_message(msg, cfg_, "command");
        const auto type = point.at("dnp3_type").get<std::string>();
        const auto index = point.at("index").get<std::uint16_t>();
        const auto device = cfg_.at("device_id").get<std::string>();
        const auto point_name = point.at("name").get<std::string>();
        const auto value = msg.at("value");
        const auto request_id = msg.at("request_id").get<std::string>();
        auto callback = [this, device, point_name, value, request_id, type, index]
                        (const dnp::ICommandTaskResult& result) {
            try {
                EdgeJson entries = EdgeJson::array();
                bool all_ok = true;
                bool found_point = false;
                result.ForeachItem([&](const dnp::CommandPointResult& item) {
                    const bool accepted = item.status == dnp::CommandStatus::SUCCESS &&
                                          item.state == dnp::CommandPointState::SUCCESS;
                    all_ok = all_ok && accepted;
                    found_point = true;
                    entries.push_back({{"header_index", item.headerIndex},
                                       {"index", item.index},
                                       {"status_code", static_cast<int>(item.status)}});
                });
                const bool task_ok = result.summary == dnp::TaskCompletion::SUCCESS;
                auto reply = edgecs::envelope(device, point_name, value, "command_result");
                reply["request_id"] = request_id;
                reply["dnp3_type"] = type;
                reply["dnp3_index"] = index;
                reply["status"] = (task_ok && all_ok && found_point)
                                  ? "accepted_by_outstation" : "rejected_by_dnp3";
                reply["dnp3_summary_code"] = static_cast<int>(result.summary);
                reply["dnp3_points"] = entries;
                publish_json(mqtt_, edgecs::topic(device, "command_result"), reply);
            } catch (const std::exception& ex) {
                std::cerr << "Retour DNP3 non publie: " << ex.what() << '\n';
            }
        };

        // Le mapping est charge dynamiquement du JSON enregistre; aucun index fixe.
        if (type == "AO") {
            master_->DirectOperate(dnp::AnalogOutputDouble64(value.get<double>()), index, callback);
        } else if (type == "BO") {
            const auto operation = value.get<bool>() ? dnp::OperationType::LATCH_ON
                                                     : dnp::OperationType::LATCH_OFF;
            master_->DirectOperate(dnp::ControlRelayOutputBlock(operation), index, callback);
        } else {
            throw std::runtime_error("Seules les commandes AO/BO sont supportees");
        }
        std::cout << '[' << device << "] MQTT " << point_name << " -> " << type << '[' << index << "]\n";
    }
private:
    const EdgeJson cfg_;
    mqtt::async_client& mqtt_;
    std::shared_ptr<SessionChannelListener> listener_;
    std::shared_ptr<GatewaySOE> handler_;
    std::shared_ptr<dnp::IChannel> channel_;
    std::shared_ptr<dnp::IMaster> master_;
};

class MasterService : public mqtt::callback {
public:
    MasterService()
        : mqtt_("tcp://" + edgecs::env("MQTT_HOST", "127.0.0.1") + ":" + edgecs::env("MQTT_PORT", "1883"),
                "edgecs-derms-master"),
          manager_(2, dnp::ConsoleLogger::Create()),
          token_(edgecs::env("EDGECS_REGISTRATION_TOKEN")) {
        if (token_.size() < 16)
            throw std::runtime_error("EDGECS_REGISTRATION_TOKEN obligatoire (au moins 16 caracteres)");
        mqtt_.set_callback(*this);
    }

    void start() {
        mqtt::connect_options opts;
        opts.set_clean_session(true);
        opts.set_automatic_reconnect(true);
        const auto user = edgecs::env("MQTT_USERNAME");
        if (!user.empty()) { opts.set_user_name(user); opts.set_password(edgecs::env("MQTT_PASSWORD")); }
        mqtt_.connect(opts)->wait();
        mqtt_.subscribe("edgecs/+/command", 1)->wait();
        mqtt_.subscribe("edgecs/+/read", 1)->wait();
    }
    void stop() {
        if (stopped_.exchange(true)) return;
        std::lock_guard<std::mutex> registration(registration_mutex_);
        // Attendre que les callbacks DNP3 terminent avant de detruire les sessions.
        manager_.Shutdown();
        {
            std::lock_guard<std::mutex> lock(mutex_);
            sessions_.clear();
        }
        try { if (mqtt_.is_connected()) mqtt_.disconnect()->wait(); } catch (...) {}
    }
    ~MasterService() { stop(); }

    bool mqtt_connected() const { return mqtt_.is_connected(); }

    void connected(const std::string&) override {
        try {
            mqtt_.subscribe("edgecs/+/command", 1);
            mqtt_.subscribe("edgecs/+/read", 1);
        }
        catch (const std::exception& e) { std::cerr << "Reabonnement MQTT: " << e.what() << '\n'; }
    }
    void connection_lost(const std::string& why) override {
        std::cerr << "MQTT deconnecte: " << why << '\n';
    }
    void message_arrived(mqtt::const_message_ptr packet) override {
        if (stopped_.load()) return;
        EdgeJson request;
        try {
            request = EdgeJson::parse(packet->to_string());
            if (!request.is_object() || !request.contains("device_id") || !request["device_id"].is_string() ||
                !request.contains("kind") || !request["kind"].is_string() ||
                !request.contains("schema_version") || !request["schema_version"].is_number_integer() ||
                request["schema_version"] != 1)
                throw std::runtime_error("MQTT envelope: invalid schema_version/device_id/kind");
            const auto dev = request.at("device_id").get<std::string>();
            const auto kind = request.at("kind").get<std::string>();
            if ((kind != "read" && kind != "command") ||
                packet->get_topic() != edgecs::topic(dev, kind))
                throw std::runtime_error("MQTT topic/schema/kind/device_id incoherent");
            if (!request.contains("request_id") || !request["request_id"].is_string() ||
                request["request_id"].get<std::string>().empty() ||
                !request.contains("timestamp") || !request["timestamp"].is_string() ||
                request["timestamp"].get<std::string>().empty())
                throw std::runtime_error("request_id and timestamp must be nonempty strings");
            std::shared_ptr<MasterSession> dest;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                auto it = sessions_.find(dev);
                if (it == sessions_.end()) throw std::runtime_error("Gateway non enregistree: " + dev);
                dest = it->second;
            }
            if (kind == "read") {
                if (!request.contains("point") || !request["point"].is_string() || request["point"] != "*" ||
                    !request.contains("value") || !request["value"].is_null())
                    throw std::runtime_error("READ requires point='*' and value=null");
                auto reply = edgecs::envelope(dev, "*", nullptr, "read_result");
                reply["request_id"] = request["request_id"];
                reply["status"] = "scan_requested"; // pas une preuve que le scan a reussi
                publish_json(mqtt_, edgecs::topic(dev, "read_result"), reply);
                dest->read_measurements(request["request_id"].get<std::string>());
            } else {
                dest->command(request);
            }
        } catch (const std::exception& ex) {
            std::cerr << "Commande MQTT rejetee: " << ex.what() << '\n';
            try {
                if (!request.is_object() || !request.contains("device_id") ||
                    !request.at("device_id").is_string()) return;
                const auto dev = request.at("device_id").get<std::string>();
                // Jamais publier sur un topic injecte via des separateurs MQTT.
                if (dev.empty() || dev.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
                        != std::string::npos) return;
                const auto string_field = [&request](const char* key, const std::string& fallback) {
                    return request.contains(key) && request.at(key).is_string()
                        ? request.at(key).get<std::string>() : fallback;
                };
                const bool read_request = string_field("kind", "") == "read";
                auto reply = edgecs::envelope(dev, string_field("point", ""),
                                              request.contains("value") ? request.at("value") : EdgeJson(nullptr),
                                              read_request ? "read_result" : "command_result");
                reply["request_id"] = string_field("request_id", "unknown");
                reply["status"] = "rejected_by_master";
                reply["reason"] = ex.what();
                publish_json(mqtt_, edgecs::topic(dev, read_request ? "read_result" : "command_result"), reply);
            } catch (const std::exception& error) {
                std::cerr << "Rejection result could not be published: " << error.what() << '\n';
            }
        }
    }

    EdgeJson register_gateway(const EdgeJson& cfg) {
        // Serialize registration separately: OpenDNP3 operations are synchronous
        // and its callbacks also update the registry. Never hold mutex_ across
        // those operations, including Enable() and Shutdown().
        std::lock_guard<std::mutex> registration(registration_mutex_);
        if (stopped_.load()) throw std::runtime_error("Master service is shutting down");
        std::string device;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            const auto decision = registry_.inspect(cfg);
            device = cfg.at("device_id").get<std::string>();
            if (decision == edgecs::ConfigRegistry::Decision::AlreadyRegistered) {
                registry_.touch_registration(device);
                return {{"device_id", device}, {"status", "already_registered"}};
            }
        }
        auto telemetry = [this](const std::string& dev, const std::string& type, std::uint16_t index,
                                const EdgeJson& value, std::uint8_t flags, std::uint64_t timestamp) {
            std::lock_guard<std::mutex> lock(mutex_);
            return registry_.update_telemetry(dev, type, index, value, flags, timestamp);
        };
        auto connection = [this](const std::string& dev, const std::string& state) {
            std::lock_guard<std::mutex> lock(mutex_);
            // Startup can report a state before the new entry is committed.
            if (registry_.get(dev)) registry_.set_connection_state(dev, state);
        };
        auto session = std::make_shared<MasterSession>(cfg, manager_, mqtt_, telemetry, connection);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            registry_.insert(cfg);
            sessions_.emplace(device, session);
            registry_.set_connection_state(device, session->connection_state());
        }
        return {{"device_id", device}, {"status", "registered"}};
    }
    EdgeJson registered() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return registry_.devices();
    }
    EdgeJson registered_device(const std::string& device) const {
        std::lock_guard<std::mutex> lock(mutex_);
        return registry_.device(device);
    }
    bool authorized(const std::string& header) const {
        return constant_time_equal(header, "Bearer " + token_);
    }
private:
    std::atomic<bool> stopped_{false};
    std::mutex registration_mutex_;
    mutable std::mutex mutex_;
    edgecs::ConfigRegistry registry_;
    std::map<std::string, std::shared_ptr<MasterSession>> sessions_;
    mqtt::async_client mqtt_;
    dnp::DNP3Manager manager_;
    const std::string token_;
};

using Respond = std::function<void(const drogon::HttpResponsePtr&)>;
void json_response(const Respond& reply, drogon::HttpStatusCode status, const EdgeJson& obj) {
    auto response = drogon::HttpResponse::newHttpResponse();
    response->setStatusCode(status);
    response->setContentTypeCode(drogon::CT_APPLICATION_JSON);
    response->setBody(obj.dump());
    reply(response);
}

} // namespace

int main() {
    try {
        const auto cert = edgecs::env("EDGECS_TLS_CERT", "certs/server.crt");
        const auto key = edgecs::env("EDGECS_TLS_KEY", "certs/server.key");
        const auto host = edgecs::prompt_ipv4(
            "Adresse IPv4 locale du Master (ecoute HTTPS)",
            edgecs::env("EDGECS_API_HOST", "127.0.0.1"));
        const int port_num = std::stoi(edgecs::env("EDGECS_API_PORT", "8443"));
        if (port_num < 1 || port_num > 65535) throw std::runtime_error("Port HTTPS invalide");
        MasterService service;
        service.start();
        drogon::app().registerHandler(
            "/api/v1/outstations/register",
            [&service](const drogon::HttpRequestPtr& req, Respond&& reply) {
                if (!service.authorized(req->getHeader("authorization"))) {
                    json_response(reply, drogon::k401Unauthorized, {{"error", "Non autorise"}});
                    return;
                }
                try {
                    const auto cfg = EdgeJson::parse(req->getBody());
                    json_response(reply, drogon::k200OK, service.register_gateway(cfg));
                } catch (const std::exception& ex) {
                    json_response(reply, drogon::k400BadRequest, {{"error", ex.what()}});
                }
            }, {drogon::Post});
        drogon::app().registerHandler(
            "/api/v1/outstations",
            [&service](const drogon::HttpRequestPtr& req, Respond&& reply) {
                if (!service.authorized(req->getHeader("authorization"))) {
                    json_response(reply, drogon::k401Unauthorized, {{"error", "Non autorise"}});
                    return;
                }
                json_response(reply, drogon::k200OK, {{"outstations", service.registered()}});
            }, {drogon::Get});
        drogon::app().registerHandler(
            "/api/v1/outstations/{1}",
            [&service](const drogon::HttpRequestPtr& req, Respond&& reply, std::string device) {
                if (!service.authorized(req->getHeader("authorization"))) {
                    json_response(reply, drogon::k401Unauthorized, {{"error", "Non autorise"}});
                    return;
                }
                const auto descriptor = service.registered_device(device);
                if (descriptor.is_null()) {
                    json_response(reply, drogon::k404NotFound, {{"error", "Unknown device: " + device}});
                    return;
                }
                json_response(reply, drogon::k200OK, descriptor);
            }, {drogon::Get});
        drogon::app().registerHandler(
            "/api/v1/outstations/{1}/telemetry",
            [&service](const drogon::HttpRequestPtr& req, Respond&& reply, std::string device) {
                if (!service.authorized(req->getHeader("authorization"))) {
                    json_response(reply, drogon::k401Unauthorized, {{"error", "Non autorise"}});
                    return;
                }
                const auto descriptor = service.registered_device(device);
                if (descriptor.is_null()) {
                    json_response(reply, drogon::k404NotFound, {{"error", "Unknown device: " + device}});
                    return;
                }
                json_response(reply, drogon::k200OK,
                    {{"device_id", device}, {"latest_telemetry", descriptor.at("latest_telemetry")},
                     {"connection", descriptor.at("connection")}});
            }, {drogon::Get});
        drogon::app().registerHandler(
            "/health",
            [&service](const drogon::HttpRequestPtr&, Respond&& reply) {
                json_response(reply, drogon::k200OK,
                    {{"status", "ok"}, {"mqtt_connected", service.mqtt_connected()}});
            }, {drogon::Get});
        drogon::app().addListener(host, static_cast<uint16_t>(port_num), true, cert, key);
        drogon::app().setThreadNum(2);
        std::cout << "DERMS Master C++ HTTPS " << host << ':' << port_num << " (MQTT/DNP3)\n";
        drogon::app().run();
    } catch (const std::exception& ex) {
        std::cerr << "ERREUR Master: " << ex.what() << '\n';
        return 1;
    }
    return 0;
}
