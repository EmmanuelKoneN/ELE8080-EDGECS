// EDGECS — Passerelle C++ : Outstation DNP3 <-> MQTT + enregistrement HTTPS.
// Démonstration pour DER simulées uniquement. Ne pas connecter à un équipement réel.
#include "common.hpp"

#include <mqtt/async_client.h>
#include <curl/curl.h>

#include <opendnp3/DNP3Manager.h>
#include <opendnp3/ConsoleLogger.h>
#include <opendnp3/channel/IPEndpoint.h>
#include <opendnp3/channel/IChannel.h>
#include <opendnp3/outstation/IOutstation.h>
#include <opendnp3/channel/PrintingChannelListener.h>
#include <opendnp3/gen/ServerAcceptMode.h>
#include <opendnp3/gen/OperationType.h>
#include <opendnp3/gen/CommandStatus.h>
#include <opendnp3/logging/LogLevels.h>
#include <opendnp3/outstation/DefaultOutstationApplication.h>
#include <opendnp3/outstation/ICommandHandler.h>
#include <opendnp3/outstation/OutstationStackConfig.h>
#include <opendnp3/outstation/UpdateBuilder.h>

#include <algorithm>
#include <cstdint>
#include <chrono>
#include <csignal>
#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>

using edgecs::Json;
namespace dnp = opendnp3;
namespace {
volatile std::sig_atomic_t stopping = 0;
void stop_signal(int) { stopping = 1; }

std::string registration_url(const Json& cfg) {
    const auto configured_url = edgecs::env("MASTER_REGISTER_URL");
    if (!configured_url.empty()) {
        if (configured_url.compare(0, 8, "https://") != 0 || configured_url.size() <= 8 ||
            configured_url.find_first_of(" \t\r\n") != std::string::npos)
            throw std::runtime_error("MASTER_REGISTER_URL doit etre une URL HTTPS valide");
        return configured_url;
    }
    const auto master_host = cfg.contains("master_api_host")
        ? cfg.at("master_api_host").get<std::string>()
        : edgecs::prompt_ipv4("Adresse IPv4 du Master DERMS (enregistrement HTTPS)", "127.0.0.1");
    return "https://" + master_host + ":" + std::to_string(cfg.value("master_api_port", 8443)) +
           "/api/v1/outstations/register";
}

size_t capture_response(char* data, size_t size, size_t count, void* context) {
    const auto bytes = size * count;
    auto& body = *static_cast<std::string*>(context);
    constexpr size_t limit = 4096;
    if (body.size() < limit) body.append(data, std::min(bytes, limit - body.size()));
    return bytes;
}

class CommandHandler final : public dnp::ICommandHandler {
public:
    CommandHandler(const Json& cfg, mqtt::async_client& client) : cfg_(cfg), client_(client) {}
    void Begin() override {}
    void End() override {}

    dnp::CommandStatus Select(const dnp::AnalogOutputInt16& c, uint16_t i) override { return check("AO", i, double(c.value)); }
    dnp::CommandStatus Select(const dnp::AnalogOutputInt32& c, uint16_t i) override { return check("AO", i, double(c.value)); }
    dnp::CommandStatus Select(const dnp::AnalogOutputFloat32& c, uint16_t i) override { return check("AO", i, double(c.value)); }
    dnp::CommandStatus Select(const dnp::AnalogOutputDouble64& c, uint16_t i) override { return check("AO", i, double(c.value)); }
    dnp::CommandStatus Select(const dnp::ControlRelayOutputBlock& c, uint16_t i) override { return binary_check(c, i); }

    dnp::CommandStatus Operate(const dnp::AnalogOutputInt16& c, uint16_t i, dnp::IUpdateHandler&, dnp::OperateType) override { return send("AO", i, double(c.value)); }
    dnp::CommandStatus Operate(const dnp::AnalogOutputInt32& c, uint16_t i, dnp::IUpdateHandler&, dnp::OperateType) override { return send("AO", i, double(c.value)); }
    dnp::CommandStatus Operate(const dnp::AnalogOutputFloat32& c, uint16_t i, dnp::IUpdateHandler&, dnp::OperateType) override { return send("AO", i, double(c.value)); }
    dnp::CommandStatus Operate(const dnp::AnalogOutputDouble64& c, uint16_t i, dnp::IUpdateHandler&, dnp::OperateType) override { return send("AO", i, double(c.value)); }
    dnp::CommandStatus Operate(const dnp::ControlRelayOutputBlock& c, uint16_t i, dnp::IUpdateHandler&, dnp::OperateType) override {
        if (binary_check(c, i) != dnp::CommandStatus::SUCCESS) return dnp::CommandStatus::NOT_SUPPORTED;
        return send("BO", i, c.opType == dnp::OperationType::LATCH_ON);
    }
private:
    dnp::CommandStatus binary_check(const dnp::ControlRelayOutputBlock& c, uint16_t i) const {
        if (c.opType != dnp::OperationType::LATCH_ON && c.opType != dnp::OperationType::LATCH_OFF)
            return dnp::CommandStatus::NOT_SUPPORTED;
        // This mapping represents one Boolean latch, not a trip/close or pulse sequence.
        if (c.tcc != dnp::TripCloseCode::NUL || c.clear || c.count != 1 || c.IsQUFlagSet())
            return dnp::CommandStatus::NOT_SUPPORTED;
        return check("BO", i, c.opType == dnp::OperationType::LATCH_ON);
    }

    dnp::CommandStatus check(const std::string& type, uint16_t index, const Json& value) const {
        auto* point = edgecs::find_index(cfg_, type, index);
        if (!point) return dnp::CommandStatus::NOT_SUPPORTED;
        if (type == "AO" && value.is_number() && std::isfinite(value.get<double>()) &&
            (value.get<double>() < (*point)["min"].get<double>() || value.get<double>() > (*point)["max"].get<double>()))
            return dnp::CommandStatus::OUT_OF_RANGE;
        try {
            edgecs::validate_value(*point, value);
            return dnp::CommandStatus::SUCCESS;
        } catch (...) { return dnp::CommandStatus::NOT_SUPPORTED; }
    }

    dnp::CommandStatus send(const std::string& type, uint16_t index, const Json& value) {
        const auto status = check(type, index, value);
        if (status != dnp::CommandStatus::SUCCESS) return status;
        if (!client_.is_connected()) return dnp::CommandStatus::LOCAL;
        try {
            const auto* point = edgecs::find_index(cfg_, type, index);
            const auto msg = edgecs::envelope(cfg_["device_id"].get<std::string>(),
                                             (*point)["name"].get<std::string>(), value, "command");
            auto mqtt_msg = mqtt::make_message(edgecs::topic(cfg_["device_id"].get<std::string>(), "edge/command"), msg.dump());
            mqtt_msg->set_qos(1);
            client_.publish(mqtt_msg);
            std::cout << "DNP3 " << type << '[' << index << "] => MQTT " << (*point)["name"] << " = " << value << '\n';
            // SUCCESS = publication MQTT soumise, et NON exécution confirmée par la DER.
            return dnp::CommandStatus::SUCCESS;
        } catch (const std::exception& ex) {
            std::cerr << "Publication MQTT impossible: " << ex.what() << '\n';
            return dnp::CommandStatus::LOCAL;
        }
    }
    const Json& cfg_;
    mqtt::async_client& client_;
};

class Gateway final : public mqtt::callback {
public:
    explicit Gateway(Json cfg, std::string registration_url)
        : cfg_(std::move(cfg)), device_(cfg_["device_id"].get<std::string>()),
          registration_url_(std::move(registration_url)),
          mqtt_("tcp://" + edgecs::mqtt_host(cfg_) + ":" + std::to_string(edgecs::mqtt_port(cfg_)),
                "edgecs-outstation-" + device_),
          manager_(1, dnp::ConsoleLogger::Create()) {
        mqtt_.set_callback(*this);
    }

    ~Gateway() override { shutdown(); }

    void start() {
        dnp::OutstationStackConfig stack;
        for (const auto& p: cfg_["points"]) {
            const auto idx = p["index"].get<std::uint16_t>();
            const auto type = p["dnp3_type"].get<std::string>();
            if (type == "AI") {
                stack.database.analog_input[idx].clazz = dnp::PointClass::Class1;
                stack.database.analog_input[idx].svariation = dnp::StaticAnalogVariation::Group30Var6;
            } else if (type == "BI") {
                stack.database.binary_input[idx].clazz = dnp::PointClass::Class1;
            }
            // AO et BO désignent ici des commandes, pas des points de mesure.
        }
        stack.outstation.eventBufferConfig = dnp::EventBufferConfig::AllTypes(100);
        stack.outstation.params.allowUnsolicited = false;
        stack.link.LocalAddr = cfg_["dnp3"]["outstation_address"].get<std::uint16_t>();
        stack.link.RemoteAddr = cfg_["dnp3"]["master_address"].get<std::uint16_t>();
        auto bind_host = edgecs::env("DNP3_BIND_HOST", "0.0.0.0");
        auto port = cfg_["dnp3"]["port"].get<std::uint16_t>();
        channel_ = manager_.AddTCPServer("edgecs-gateway", dnp::levels::NORMAL,
                  dnp::ServerAcceptMode::CloseExisting, dnp::IPEndpoint(bind_host, port),
                  dnp::PrintingChannelListener::Create());
        if (!channel_) throw std::runtime_error("Creation du serveur DNP3 impossible");
        handler_ = std::make_shared<CommandHandler>(cfg_, mqtt_);
        station_ = channel_->AddOutstation("edgecs-outstation", handler_,
                   dnp::DefaultOutstationApplication::Create(), stack);
        if (!station_) throw std::runtime_error("Creation de l'Outstation DNP3 impossible");
        station_->Enable();
        // Initialise la base statique DNP3 depuis le JSON. Le simulateur peut
        // ensuite modifier ces valeurs via MQTT; le Master ne les voit que par READ.
        dnp::UpdateBuilder initial;
        for (const auto& p : cfg_["points"]) {
            if (p["direction"] != "telemetry") continue;
            const auto index = p["index"].get<std::uint16_t>();
            if (p["dnp3_type"] == "AI") {
                initial.Update(dnp::Analog(p.value("initial", 0.0)), index);
            } else if (p["dnp3_type"] == "BI") {
                initial.Update(dnp::Binary(p.value("initial", false)), index);
            }
        }
        station_->Apply(initial.Build());
        std::cout << "Outstation DNP3 sur " << bind_host << ':' << port << '\n';

        mqtt::connect_options options;
        options.set_clean_session(true);
        options.set_automatic_reconnect(true);
        const auto user = edgecs::env("MQTT_USERNAME");
        if (!user.empty()) { options.set_user_name(user); options.set_password(edgecs::env("MQTT_PASSWORD")); }
        mqtt_.connect(options)->wait();
        mqtt_.subscribe(edgecs::topic(device_, "edge/telemetry"), 1)->wait();
        std::cout << "MQTT connecte et abonne a edge/telemetry\n";
    }

    void connected(const std::string&) override {
        // A la reconnexion, les abonnements d'une session MQTT 'clean' sont perdus.
        try {
            mqtt_.subscribe(edgecs::topic(device_, "edge/telemetry"), 1);
        } catch (const std::exception& ex) { std::cerr << "Resubscribe: " << ex.what() << '\n'; }
    }
    void connection_lost(const std::string& why) override {
        std::cerr << "Connexion MQTT perdue: " << why << '\n';
    }
    void message_arrived(mqtt::const_message_ptr packet) override {
        if (packet->get_topic() != edgecs::topic(device_, "edge/telemetry")) return;
        try {
            Json msg = Json::parse(packet->to_string());
            const auto& point = edgecs::validate_message(msg, cfg_, "telemetry");
            dnp::UpdateBuilder builder;
            const auto index = point["index"].get<std::uint16_t>();
            if (point["dnp3_type"] == "AI") builder.Update(dnp::Analog(msg["value"].get<double>()), index);
            else if (point["dnp3_type"] == "BI") builder.Update(dnp::Binary(msg["value"].get<bool>()), index);
            else return;
            station_->Apply(builder.Build());
            std::cout << "MQTT " << msg["point"] << " => DNP3 " << point["dnp3_type"] << '[' << index << "]\n";
        } catch (const std::exception& ex) { std::cerr << "Telemesure rejetee: " << ex.what() << '\n'; }
    }

    void register_with_derms() {
        const auto token = edgecs::env("EDGECS_REGISTRATION_TOKEN");
        if (token.empty()) throw std::runtime_error("EDGECS_REGISTRATION_TOKEN manquant");
        const auto ca = edgecs::env("EDGECS_CA_CERT", "certs/master.crt");
        const std::string body = cfg_.dump();
        const auto authorization = "Authorization: Bearer " + token;
        while (!stopping) {
            std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> curl(curl_easy_init(), curl_easy_cleanup);
            if (!curl) throw std::runtime_error("Initialisation de libcurl impossible");
            struct curl_slist* headers = nullptr;
            headers = curl_slist_append(headers, "Content-Type: application/json");
            headers = curl_slist_append(headers, authorization.c_str());
            std::unique_ptr<curl_slist, decltype(&curl_slist_free_all)> owned_headers(headers, curl_slist_free_all);
            if (!headers) throw std::runtime_error("Allocation des entetes HTTPS impossible");
            std::string response;
            curl_easy_setopt(curl.get(), CURLOPT_URL, registration_url_.c_str());
            curl_easy_setopt(curl.get(), CURLOPT_HTTPHEADER, headers);
            curl_easy_setopt(curl.get(), CURLOPT_POSTFIELDS, body.c_str());
            curl_easy_setopt(curl.get(), CURLOPT_POSTFIELDSIZE, static_cast<long>(body.size()));
            curl_easy_setopt(curl.get(), CURLOPT_CAINFO, ca.c_str());
            curl_easy_setopt(curl.get(), CURLOPT_SSL_VERIFYPEER, 1L);
            curl_easy_setopt(curl.get(), CURLOPT_SSL_VERIFYHOST, 2L);
            curl_easy_setopt(curl.get(), CURLOPT_TIMEOUT, 5L);
            curl_easy_setopt(curl.get(), CURLOPT_NOSIGNAL, 1L);
            curl_easy_setopt(curl.get(), CURLOPT_WRITEFUNCTION, capture_response);
            curl_easy_setopt(curl.get(), CURLOPT_WRITEDATA, &response);
            CURLcode rc = curl_easy_perform(curl.get());
            long status = 0;
            curl_easy_getinfo(curl.get(), CURLINFO_RESPONSE_CODE, &status);
            if (rc == CURLE_OK && status >= 200 && status < 300) {
                std::cout << "Gateway enregistree aupres du DERMS (HTTP " << status << ")\n";
                return;
            }
            const auto failure = "Enregistrement HTTPS impossible: " +
                std::string(curl_easy_strerror(rc)) + ", HTTP=" + std::to_string(status) +
                (response.empty() ? "" : ", reponse=" + response);
            if (rc == CURLE_OK && status >= 400 && status < 500 && status != 408 && status != 429)
                throw std::runtime_error(failure);
            std::cerr << failure << "; nouvel essai 5s\n";
            for (int i=0;i<5 && !stopping;++i) std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }

    void shutdown() {
        if (shut_down_) return;
        shut_down_ = true;
        try {
            mqtt_.disable_callbacks();
            if (mqtt_.is_connected()) mqtt_.disconnect()->wait_for(std::chrono::seconds(2));
        } catch (...) {}
        try { if (station_) station_->Disable(); } catch (...) {}
        try { manager_.Shutdown(); } catch (...) {}
    }
private:
    Json cfg_;
    std::string device_;
    std::string registration_url_;
    bool shut_down_ = false;
    mqtt::async_client mqtt_;
    dnp::DNP3Manager manager_;
    std::shared_ptr<dnp::IChannel> channel_;
    std::shared_ptr<dnp::IOutstation> station_;
    std::shared_ptr<CommandHandler> handler_;
};
} // namespace

int main(int argc, char** argv) {
    if (argc != 2 || std::string(argv[1]).empty()) {
        std::cerr << "Usage: " << argv[0] << " <configuration.json>\n";
        return 2;
    }
    std::signal(SIGINT, stop_signal);
    std::signal(SIGTERM, stop_signal);
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != 0) { std::cerr << "libcurl indisponible\n"; return 1; }
    try {
        auto cfg = edgecs::load_config(argv[1]);
        const auto url = registration_url(cfg);
        Gateway gateway(std::move(cfg), url);
        gateway.start();
        // Renouveler l'enregistrement pour récupérer un redémarrage du Master.
        // Chaque POST identique est idempotent ("already_registered").
        while (!stopping) {
            gateway.register_with_derms();
            for (int i = 0; i < 30 && !stopping; ++i)
                std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        gateway.shutdown();
    } catch (const std::exception& e) { std::cerr << "ERREUR Gateway: " << e.what() << '\n'; curl_global_cleanup(); return 1; }
    curl_global_cleanup();
    return 0;
}
