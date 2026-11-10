// EDGECS - Simulateur de DER configure entierement depuis les points JSON.
// Laboratoire uniquement : ne pas connecter a un equipement reel.
// Version non bloquante : la console reste disponible sans broker MQTT.
#include "common.hpp"
#include <mqtt/async_client.h>

#include <chrono>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

namespace {
using Json = edgecs::Json;
using namespace std::chrono_literals;

Json parse_measurement(const Json& point, const std::string& text) {
    if (point.at("dnp3_type") == "BI") {
        if (text == "1" || text == "true" || text == "on") return true;
        if (text == "0" || text == "false" || text == "off") return false;
        throw std::runtime_error("Valeur booleenne attendue: 0/1, true/false, on/off");
    }
    size_t used = 0;
    const double value = std::stod(text, &used);
    if (used != text.size() || !std::isfinite(value))
        throw std::runtime_error("Valeur numerique invalide");
    return value;
}

class DerSimulator final : public mqtt::callback {
public:
    explicit DerSimulator(Json cfg, bool gui_mode = false)
        : cfg_(std::move(cfg)),
          dev_(cfg_.at("device_id").get<std::string>()),
          gui_mode_(gui_mode),
          client_("tcp://" + edgecs::mqtt_host(cfg_) + ":" +
                      std::to_string(edgecs::mqtt_port(cfg_)),
                  "edgecs-simulator-" + dev_) {
        for (const auto& p : cfg_.at("points")) {
            if (p.at("direction") != "telemetry") continue;
            const bool binary = p.at("dnp3_type") == "BI";
            const auto name = p.at("name").get<std::string>();
            measurements_[name] = p.value("initial", binary ? Json(false) : Json(0.0));
            measurement_times_[name] = edgecs::timestamp_now();
            measurement_sources_[name] = "initial";
        }
        client_.set_callback(*this);
    }

    ~DerSimulator() override { stop(); }

    // Ne bloque pas : le reseau MQTT est gere par un thread distinct.
    void start() {
        log("[DER ", dev_, "] Console disponible. Connexion MQTT en cours...\n");
        emit_status("starting", "Simulateur demarre; valeurs internes initialisees.");
        snapshot();
        worker_ = std::thread(&DerSimulator::mqtt_loop, this);
    }

    // Callbacks Paho : aucun subscribe(), publish() ou wait() ici.
    void connected(const std::string&) override {
        {
            std::lock_guard<std::mutex> lock(work_mutex_);
            if (stopping_) return;
            mqtt_connected_ = true;
            ever_connected_ = true;
            subscribed_ = false;
            needs_setup_ = true;
            ++connection_generation_;
            outbox_.clear(); // Un instantane actuel sera envoye apres abonnement.
        }
        cv_.notify_one();
    }

    void connection_lost(const std::string& why) override {
        {
            std::lock_guard<std::mutex> lock(work_mutex_);
            if (stopping_) return;
            mqtt_connected_ = false;
            subscribed_ = false;
            needs_setup_ = false;
            ++connection_generation_;
            outbox_.clear();
        }
        log_error("\n[DER] MQTT perdu : ", why, "\nDER> ");
        emit_status("disconnected", why);
        cv_.notify_one();
    }

    void message_arrived(mqtt::const_message_ptr packet) override {
        if (packet->get_topic() != edgecs::topic(dev_, "edge/command")) return;
        Json msg;
        try {
            if (stopping()) return;
            msg = Json::parse(packet->to_string());
            const auto& command_point = edgecs::validate_message(msg, cfg_, "command");
            const auto name = command_point.at("name").get<std::string>();
            const auto received_at = edgecs::timestamp_now();
            const auto request_id = msg.at("request_id").get<std::string>();
            // Valider aussi le retour avant toute modification de l'etat interne.
            const Json* feedback = nullptr;
            if (command_point.contains("feedback_point")) {
                const auto target = command_point.at("feedback_point").get<std::string>();
                feedback = edgecs::find_point(cfg_, target, "telemetry");
                if (!feedback) throw std::runtime_error("feedback_point inconnu: " + target);
                edgecs::validate_value(*feedback, msg.at("value"));
            }
            log("\n[DER] Commande ", name, " = ", msg.at("value"), '\n');
            emit({{"kind", "command_result"}, {"point", name},
                  {"dnp3_type", command_point.at("dnp3_type")},
                  {"index", command_point.at("index")}, {"value", msg.at("value")},
                  {"received_at", received_at}, {"request_id", request_id},
                  {"status", "accepted_by_simulator"},
                  {"feedback_point", feedback ? feedback->at("name") : Json(nullptr)},
                  {"feedback_simulated", feedback != nullptr}});

            // Comportement de simulation parametrable.
            if (feedback) {
                const auto target = feedback->at("name").get<std::string>();
                update_measurement(*feedback, msg.at("value"), "feedback", request_id);
                // Mise en file seulement, pas d'appel MQTT dans le callback.
                log("[DER] Retour simule ", target, " = ", msg.at("value"), '\n');
            } else {
                log("[DER] Commande recue sans feedback_point : mesure inchangee.\n");
            }
            log("DER> ");
        } catch (const std::exception& ex) {
            log_error("[DER] Commande refusee : ", ex.what(), '\n');
            emit_error("command", msg, ex.what());
        }
    }

    void change_measurement(const std::string& key, const std::string& input) {
        const auto* p = edgecs::find_cli_point(cfg_, key, "telemetry");
        if (!p) throw std::runtime_error("Mesure inconnue: " + key + ". Saisir 'list'.");
        const auto value = parse_measurement(*p, input);
        update_measurement(*p, value, "manual", "");
    }

    // IPC local de laboratoire. Les commandes IPC ne passent jamais par MQTT.
    bool gui_request(const std::string& line) {
        Json request;
        std::string operation;
        try {
            request = Json::parse(line);
            if (!request.is_object() || !request.contains("op") || !request.at("op").is_string())
                throw std::runtime_error("La requete IPC doit contenir une operation op.");
            operation = request.at("op").get<std::string>();
            if (request.contains("request_id") && !request.at("request_id").is_string())
                throw std::runtime_error("request_id doit etre une chaine.");
            const auto request_id = request.value("request_id", std::string());
            if (operation == "quit") return false;
            if (operation == "snapshot") snapshot(request_id);
            else if (operation == "set") {
                if (!request.contains("point") || !request.at("point").is_string() ||
                    !request.contains("value"))
                    throw std::runtime_error("Utilisation IPC: {op:set, point:nom, value:valeur}.");
                const auto name = request.at("point").get<std::string>();
                const auto* point = edgecs::find_point(cfg_, name, "telemetry");
                if (!point) throw std::runtime_error("Mesure inconnue: " + name);
                update_measurement(*point, request.at("value"), "manual", request_id);
            } else throw std::runtime_error("Operation IPC inconnue: " + operation);
        } catch (const std::exception& ex) {
            emit_error(operation.empty() ? "ipc" : operation, request, ex.what());
        }
        return true;
    }

    void snapshot(const std::string& request_id = "") const {
        Json values = Json::array();
        {
            std::lock_guard<std::mutex> lock(mutex_);
            for (const auto& p : cfg_.at("points")) {
                if (p.at("direction") == "telemetry") values.push_back(measurement_info(p));
            }
            // Ne pas emettre un instantane ancien apres un changement plus recent.
            emit({{"kind", "snapshot"}, {"request_id", request_id}, {"measurements", values}});
        }
    }

    void publish_all() {
        // Le verrou d'etat precede toujours celui de la file de travail. Ainsi
        // un instantane ne peut pas republier une valeur anterieure a un set.
        std::lock_guard<std::mutex> lock(mutex_);
        for (const auto& item : measurements_) publish_point(item.first, item.second);
    }

    void list() const {
        std::ostringstream output;
        output << "\nDER " << dev_ << " - points de telemesure:\n";
        for (const auto& p : cfg_.at("points")) {
            if (p.at("direction") != "telemetry") continue;
            output << "  " << p.at("name").get<std::string>();
            if (p.contains("alias")) output << " (alias " << p.at("alias") << ")";
            output << " " << p.at("dnp3_type") << '[' << p.at("index")
                      << "] " << p.at("unit") << '\n';
        }
        log(output.str());
    }

    void status() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::ostringstream output;
        output << "[DER " << dev_ << "] Etat local:\n";
        for (const auto& item : measurements_)
            output << "  " << item.first << " = " << item.second << '\n';
        log(output.str());
    }

    void stop() {
        {
            std::lock_guard<std::mutex> lock(work_mutex_);
            if (stopping_) return;
            stopping_ = true;
        }
        cv_.notify_all();
        if (worker_.joinable()) worker_.join();
        try {
            if (client_.is_connected()) {
                const auto token = client_.disconnect();
                if (!token->wait_for(2s))
                    log_error("[DER] Deconnexion MQTT : delai depasse.\n");
            }
        } catch (const std::exception& ex) {
            log_error("[DER] Deconnexion MQTT : ", ex.what(), '\n');
        }
        client_.disable_callbacks();
        emit_status("stopped", "Simulateur arrete.");
    }

    const Json& config() const { return cfg_; }

private:
    // Chaque ligne IPC est ecrite sous un verrou unique. En mode GUI, les
    // journaux humains vont sur stderr: aucun prompt ne coupe une ligne JSON.
    template<typename... Args> void log(Args&&... parts) const {
        std::ostringstream message;
        (message << ... << parts);
        const auto line = message.str();
        std::lock_guard<std::mutex> lock(output_mutex_);
        auto& out = gui_mode_ ? std::cerr : std::cout;
        out << line;
        // QProcess peut fusionner stdout et stderr. Terminer aussi les prompts
        // humains en mode GUI pour conserver le prefixe IPC en debut de ligne.
        if (gui_mode_ && (line.empty() || line.back() != '\n')) out << '\n';
        out << std::flush;
    }

    template<typename... Args> void log_error(Args&&... parts) const {
        std::ostringstream message;
        (message << ... << parts);
        const auto line = message.str();
        std::lock_guard<std::mutex> lock(output_mutex_);
        std::cerr << line;
        if (gui_mode_ && (line.empty() || line.back() != '\n')) std::cerr << '\n';
        std::cerr << std::flush;
    }

    void emit(Json event) const {
        if (!gui_mode_) return;
        event["device_id"] = dev_;
        event["timestamp"] = edgecs::timestamp_now();
        const auto line = "EDGECS_GUI " + event.dump() + "\n";
        std::lock_guard<std::mutex> lock(output_mutex_);
        std::cout << line << std::flush;
    }

    void emit_error(const std::string& op, const Json& request, const std::string& message) const {
        Json event{{"kind", "error"}, {"op", op}, {"request_id", ""}, {"message", message}};
        for (const auto* field : {"request_id", "point"}) {
            if (request.is_object() && request.contains(field) && request.at(field).is_string())
                event[field] = request.at(field);
        }
        emit(std::move(event));
    }

    void emit_status(const std::string& state, const std::string& message) {
        bool connected = false, subscribed = false;
        {
            std::lock_guard<std::mutex> lock(work_mutex_);
            connected = mqtt_connected_ && !stopping_;
            subscribed = subscribed_ && !stopping_;
        }
        emit({{"kind", "status"}, {"state", state}, {"message", message},
              {"mqtt_connected", connected}, {"mqtt_subscribed", subscribed}});
    }

    // L'appelant detient mutex_.
    Json measurement_info(const Json& point) const {
        const auto name = point.at("name").get<std::string>();
        const auto& source = measurement_sources_.at(name);
        return {{"point", name}, {"dnp3_type", point.at("dnp3_type")},
                {"index", point.at("index")}, {"value", measurements_.at(name)},
                {"updated_at", measurement_times_.at(name)}, {"source", source},
                {"simulated", source == "feedback"}};
    }

    void update_measurement(const Json& point, const Json& value,
                            const std::string& source, const std::string& request_id) {
        const auto name = point.at("name").get<std::string>();
        // Une valeur refusee ne doit modifier ni la mesure ni son horodatage.
        edgecs::validate_value(point, value);
        Json event;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            measurements_.at(name) = value;
            measurement_times_.at(name) = edgecs::timestamp_now();
            measurement_sources_.at(name) = source;
            // File de publication et evenement suivent le meme ordre que l'etat.
            // Aucun appel MQTT ni attente n'est effectue sous ce verrou.
            publish_point(name, value);
            event = measurement_info(point);
            event["kind"] = "measurement";
            event["request_id"] = request_id;
            // Garder l'ordre des changements locaux et de leurs evenements.
            emit(std::move(event));
        }
    }

    struct PendingTelemetry {
        std::string name;
        Json value;
    };

    bool stopping() {
        std::lock_guard<std::mutex> lock(work_mutex_);
        return stopping_;
    }

    // Attente bornee, interrompable par 'quit'. Ne tourne jamais dans le callback.
    bool wait_token(const mqtt::token_ptr& token, std::chrono::milliseconds timeout) {
        const auto deadline = std::chrono::steady_clock::now() + timeout;
        while (std::chrono::steady_clock::now() < deadline) {
            if (stopping()) return false;
            if (token->wait_for(100ms)) return true;
        }
        return false;
    }

    void mqtt_loop() {
        mqtt::connect_options opts;
        opts.set_automatic_reconnect(true);
        opts.set_clean_session(true);
        opts.set_connect_timeout(4);
        const auto user = edgecs::env("MQTT_USERNAME");
        if (!user.empty()) {
            opts.set_user_name(user);
            opts.set_password(edgecs::env("MQTT_PASSWORD"));
        }

        while (!stopping()) {
            bool ever_connected = false;
            {
                std::lock_guard<std::mutex> lock(work_mutex_);
                ever_connected = ever_connected_;
            }

            // Tentatives initiales : Paho ne garantit pas la reconnexion automatique
            // tant qu'une premiere connexion n'a jamais reussi.
            if (!ever_connected) {
                try {
                    log("[DER] Connexion au broker MQTT...\n");
                    emit_status("connecting", "Connexion au broker MQTT en cours.");
                    const auto token = client_.connect(opts);
                    if (!wait_token(token, 6s)) {
                        if (!stopping())
                            log_error("[DER] MQTT : connexion non terminee. Nouvelle tentative.\n");
                    }
                } catch (const std::exception& ex) {
                    if (!stopping()) {
                        log_error("[DER] MQTT indisponible : ", ex.what(), '\n');
                        emit_status("disconnected", ex.what());
                    }
                }
                std::unique_lock<std::mutex> lock(work_mutex_);
                cv_.wait_for(lock, 2s, [this] { return stopping_ || ever_connected_; });
                continue;
            }

            bool setup = false;
            std::size_t generation = 0;
            PendingTelemetry next;
            bool have_next = false;
            {
                std::unique_lock<std::mutex> lock(work_mutex_);
                cv_.wait_for(lock, 500ms, [this] {
                    return stopping_ || needs_setup_ || (subscribed_ && !outbox_.empty());
                });
                if (stopping_) break;
                // Aucun appel Paho sous work_mutex_: les callbacks Paho
                // prennent aussi ce verrou et peuvent detenir leurs verrous.
                if (needs_setup_ && mqtt_connected_) {
                    setup = true;
                    needs_setup_ = false;
                    generation = connection_generation_;
                } else if (subscribed_ && mqtt_connected_ && !outbox_.empty()) {
                    next = std::move(outbox_.front());
                    outbox_.pop_front();
                    have_next = true;
                }
            }

            if (setup) {
                bool ok = false;
                try {
                    const auto token = client_.subscribe(edgecs::topic(dev_, "edge/command"), 1);
                    ok = wait_token(token, 5s);
                } catch (const std::exception& ex) {
                    if (!stopping())
                        log_error("[DER] Abonnement MQTT impossible : ", ex.what(), '\n');
                }
                {
                    std::lock_guard<std::mutex> lock(work_mutex_);
                    if (generation != connection_generation_ || !mqtt_connected_)
                        ok = false;
                    if (ok && !stopping_) subscribed_ = true;
                    else if (!stopping_ && mqtt_connected_) needs_setup_ = true;
                }
                if (ok) {
                    log("\n[DER ", dev_, "] Simulateur generique connecte.\n",
                        "[DER] Abonne a ", edgecs::topic(dev_, "edge/command"), "\nDER> ");
                    emit_status("connected", "Connexion MQTT et abonnement aux commandes confirmes.");
                    publish_all(); // Instantane courant apres chaque (re)abonnement.
                } else if (!stopping()) {
                    log_error("[DER] Abonnement non confirme, nouvelle tentative.\n");
                    emit_status("connecting", "Abonnement MQTT non confirme; nouvelle tentative.");
                    std::unique_lock<std::mutex> lock(work_mutex_);
                    cv_.wait_for(lock, 2s, [this] { return stopping_; });
                }
            } else if (have_next) {
                send_telemetry(next);
            }
        }
    }

    // Publication MQTT uniquement depuis le thread de travail.
    void send_telemetry(const PendingTelemetry& item) {
        if (!client_.is_connected()) return;
        try {
            auto msg = edgecs::envelope(dev_, item.name, item.value, "telemetry");
            auto packet = mqtt::make_message(edgecs::topic(dev_, "edge/telemetry"), msg.dump());
            packet->set_qos(1);
            client_.publish(packet); // Asynchrone, sans wait().
            log("[DER >> Gateway MQTT] ", item.name, " = ", item.value, '\n');
        } catch (const std::exception& ex) {
            log_error("[DER] Publication impossible : ", ex.what(), '\n');
            emit_error("publish", Json{{"point", item.name}}, ex.what());
        }
    }

    // Appelee par la console ou le callback : validation + mise en file seulement.
    void publish_point(const std::string& name, const Json& value) {
        try {
            auto msg = edgecs::envelope(dev_, name, value, "telemetry");
            edgecs::validate_message(msg, cfg_, "telemetry");
            {
                std::lock_guard<std::mutex> lock(work_mutex_);
                if (stopping_) return;
                if (outbox_.size() >= 256) outbox_.pop_front();
                outbox_.push_back({name, value});
            }
            cv_.notify_one();
        } catch (const std::exception& ex) {
            log_error("[DER] Mesure refusee : ", ex.what(), '\n');
            emit_error("publish", Json{{"point", name}}, ex.what());
        }
    }

    // Les dependances du client MQTT restent vivantes jusqu'a sa destruction.
    Json cfg_;
    std::string dev_;
    bool gui_mode_;
    mutable std::mutex output_mutex_;
    mutable std::mutex mutex_;
    std::map<std::string, Json> measurements_;
    std::map<std::string, std::string> measurement_times_;
    std::map<std::string, std::string> measurement_sources_;
    std::mutex work_mutex_;
    std::condition_variable cv_;
    std::deque<PendingTelemetry> outbox_;
    bool stopping_ = false;
    bool mqtt_connected_ = false;
    bool ever_connected_ = false;
    bool needs_setup_ = false;
    bool subscribed_ = false;
    std::size_t connection_generation_ = 0;
    std::thread worker_;
    mqtt::async_client client_; // Dernier membre declare : detruit avant les mutex.
};

void help() {
    std::cout << "\n  list                  lister les mesures definies dans le JSON\n"
              << "  set <point> <valeur>  modifier et publier une mesure de la DER simulee\n"
              << "  <alias> <valeur>      raccourci configure dans le JSON\n"
              << "  send                  publier toutes les mesures vers la Gateway\n"
              << "  status                afficher les valeurs internes\n"
              << "  help, quit            aide, quitter\n\n";
}
} // namespace

int main(int argc, char** argv) {
    try {
        bool gui_mode = false;
        std::string path;
        for (int i = 1; i < argc; ++i) {
            const std::string arg(argv[i]);
            if (arg == "--gui") gui_mode = true;
            else if (path.empty()) path = arg;
            else throw std::runtime_error("Utilisation: edgecs_bess_sim [configuration.json] [--gui]");
        }
        if (path.empty()) path = edgecs::env("EDGECS_CONFIG", "config/outstation_config.json");
        DerSimulator der(edgecs::load_config(path), gui_mode);
        der.start();
        if (!gui_mode) {
            help();
            der.list();
        }
        std::string line;
        while ((gui_mode || (std::cout << "DER> " << std::flush)) && std::getline(std::cin, line)) {
            if (gui_mode) {
                if (!der.gui_request(line)) break;
                continue;
            }
            std::istringstream in(line);
            std::string cmd, point, value, extra;
            in >> cmd;
            try {
                if (cmd == "quit" || cmd == "exit") break;
                if (cmd == "help") help();
                else if (cmd == "list") der.list();
                else if (cmd == "status") der.status();
                else if (cmd == "send") der.publish_all();
                else if (cmd == "set") {
                    if (!(in >> point >> value) || (in >> extra))
                        throw std::runtime_error("Utilisation : set <point> <valeur>");
                    der.change_measurement(point, value);
                } else if (!cmd.empty()) {
                    if (in >> value && !(in >> extra) &&
                        edgecs::find_cli_point(der.config(), cmd, "telemetry")) {
                        der.change_measurement(cmd, value);
                    } else {
                        std::cout << "Commande inconnue. Saisir 'list' ou 'help'.\n";
                    }
                }
            } catch (const std::exception& ex) {
                std::cerr << "[DER] " << ex.what() << '\n';
            }
        }
        der.stop();
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Erreur simulateur : " << ex.what() << '\n';
        return 1;
    }
}
