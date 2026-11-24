#include "common.hpp"

#include <arpa/inet.h>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>

namespace edgecs {
std::string env(const char* key, const std::string& fallback) {
    const char* ptr = std::getenv(key);
    return ptr ? std::string(ptr) : fallback;
}

std::string mqtt_host(const Json& cfg) {
    return cfg.contains("mqtt") ? cfg.at("mqtt").at("host").get<std::string>()
                                : env("MQTT_HOST", "127.0.0.1");
}
int mqtt_port(const Json& cfg) {
    return cfg.contains("mqtt") ? cfg.at("mqtt").at("port").get<int>()
                                : std::stoi(env("MQTT_PORT", "1883"));
}

std::string prompt_ipv4(const std::string& question, const std::string& suggestion) {
    unsigned char parsed[4];
    if (inet_pton(AF_INET, suggestion.c_str(), parsed) != 1)
        throw std::runtime_error("Suggestion IPv4 invalide: " + suggestion);
    while (true) {
        std::cout << question << " [" << suggestion << "] : " << std::flush;
        std::string value;
        if (!std::getline(std::cin, value)) {
            if (std::cin.eof()) return suggestion; // execution non interactive
            throw std::runtime_error("Lecture de l'adresse IP impossible");
        }
        const auto first = value.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) return suggestion;
        const auto last = value.find_last_not_of(" \t\r\n");
        value = value.substr(first, last - first + 1);
        if (inet_pton(AF_INET, value.c_str(), parsed) == 1) return value;
        std::cerr << "Adresse IPv4 invalide (ex. 127.0.0.1 ou 192.168.1.10). Reessayer.\n";
    }
}

static void only_keys(const Json& obj, const std::set<std::string>& allowed,
                      const std::string& where) {
    for (auto it = obj.begin(); it != obj.end(); ++it) {
        if (!allowed.count(it.key()))
            throw std::runtime_error("Cle inconnue dans " + where + ": " + it.key());
    }
}

static bool number(const Json& x) { return x.is_number() && std::isfinite(x.get<double>()); }
static bool unsigned_number(const Json& x, std::uint64_t max) {
    if (x.is_number_unsigned()) return x.get<std::uint64_t>() <= max;
    if (!x.is_number_integer()) return false;
    const auto value = x.get<std::int64_t>();
    return value >= 0 && static_cast<std::uint64_t>(value) <= max;
}

static bool schema_one(const Json& object) {
    return object.contains("schema_version") && unsigned_number(object.at("schema_version"), 1) &&
           object.at("schema_version").get<int>() == 1;
}

static void ipv4(const Json& value, const std::string& field) {
    unsigned char parsed[4];
    if (!value.is_string() || inet_pton(AF_INET, value.get<std::string>().c_str(), parsed) != 1)
        throw std::runtime_error(field + " must be an IPv4 address");
}

static bool nonempty_string(const Json& object, const std::string& field) {
    return object.contains(field) && object.at(field).is_string() &&
           !object.at(field).get_ref<const std::string&>().empty();
}

void validate_config(const Json& c) {
    if (!c.is_object() || !schema_one(c))
        throw std::runtime_error("schema_version must be the integer 1");
    only_keys(c, {"schema_version", "device_id", "name", "der_type", "dnp3",
                  "mqtt", "master_api_host", "master_api_port", "points"}, "racine JSON");
    if (!c.contains("device_id") || !c["device_id"].is_string()) throw std::runtime_error("device_id manquant");
    auto dev = c["device_id"].get<std::string>();
    if (dev.empty() || dev.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_") != std::string::npos)
        throw std::runtime_error("device_id invalide");
    if (!c.contains("name") || !c["name"].is_string() || c["name"].get<std::string>().empty())
        throw std::runtime_error("name absent");
    // Device categories are metadata, never a dispatch table in the application.
    if (!nonempty_string(c, "der_type")) throw std::runtime_error("der_type must be a nonempty string");
    if (!c.contains("dnp3") || !c["dnp3"].is_object()) throw std::runtime_error("dnp3 manquant");
    const auto& d = c["dnp3"];
    only_keys(d, {"host", "port", "master_address", "outstation_address"}, "dnp3");
    if (!d.contains("host") || !d["host"].is_string()) throw std::runtime_error("IP manquante");
    const auto host = d["host"].get<std::string>();
    unsigned char parsed[4];
    if (inet_pton(AF_INET, host.c_str(), parsed) != 1)
        throw std::runtime_error("dnp3.host doit etre une adresse IPv4");
    if (!d.contains("port") || !unsigned_number(d["port"], 65535) || d["port"].get<int>() == 0)
        throw std::runtime_error("port DNP3 invalide");
    for (auto field: {"master_address", "outstation_address"}) {
        if (!d.contains(field) || !unsigned_number(d[field], 65519))
            throw std::runtime_error(std::string(field) + " invalide");
    }
    if (d["master_address"] == d["outstation_address"]) throw std::runtime_error("adresses DNP3 identiques");
    if (c.contains("mqtt")) {
        const auto& m = c["mqtt"];
        if (m.is_object()) only_keys(m, {"host", "port"}, "mqtt");
        if (!m.is_object() || !m.contains("host") || !m["host"].is_string() ||
            !m.contains("port") || !unsigned_number(m["port"], 65535) ||
            m["port"].get<int>() == 0)
            throw std::runtime_error("mqtt.host ou mqtt.port invalide");
        unsigned char ip[4];
        if (inet_pton(AF_INET, m["host"].get<std::string>().c_str(), ip) != 1)
            throw std::runtime_error("mqtt.host doit etre une IPv4");
    }
    if (c.contains("master_api_port") &&
        (!unsigned_number(c["master_api_port"], 65535) || c["master_api_port"].get<int>() == 0))
        throw std::runtime_error("master_api_port invalide");
    if (c.contains("master_api_host")) ipv4(c.at("master_api_host"), "master_api_host");
    if (!c.contains("points") || !c["points"].is_array() || c["points"].empty())
        throw std::runtime_error("points manquants");
    std::set<std::string> names;
    std::set<std::pair<std::string,int>> indexes;
    std::set<std::pair<std::string,std::string>> cli_names;
    for (const auto& p : c["points"]) {
        if (!p.is_object() || !p.contains("name") || !p["name"].is_string() ||
            !p.contains("dnp3_type") || !p["dnp3_type"].is_string() ||
            !p.contains("direction") || !p["direction"].is_string() ||
            !p.contains("index") || !unsigned_number(p["index"], 65535))
            throw std::runtime_error("point incomplet");
        only_keys(p, {"name", "alias", "direction", "dnp3_type", "index", "unit",
                      "min", "max", "initial", "feedback_point"}, "point");
        const auto n = p["name"].get<std::string>();
        const auto t = p["dnp3_type"].get<std::string>();
        const auto dir = p["direction"].get<std::string>();
        const int i = p["index"].get<int>();
        if (n.empty() || n.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") != std::string::npos || !names.insert(n).second)
            throw std::runtime_error("nom de point vide, interdit ou duplique");
        if (t != "AI" && t != "BI" && t != "AO" && t != "BO") throw std::runtime_error("type DNP3 invalide");
        if (dir != ((t == "AO" || t == "BO") ? "command" : "telemetry"))
            throw std::runtime_error("direction de point incompatible");
        if (!indexes.insert({t,i}).second) throw std::runtime_error("index DNP3 duplique");
        if (!p.contains("unit") || !p["unit"].is_string())
            throw std::runtime_error("unit manquant pour " + n);
        if (p.contains("alias") && !p["alias"].is_string())
            throw std::runtime_error("alias doit etre une chaine pour " + n);
        const auto label = p.value("alias", n);
        if (label.empty() || label.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") != std::string::npos)
            throw std::runtime_error("alias invalide pour " + n);
        if (!cli_names.insert({dir, label}).second)
            throw std::runtime_error("alias CLI duplique dans la direction " + dir + ": " + label);
        if (p.contains("feedback_point") && !p["feedback_point"].is_string())
            throw std::runtime_error("feedback_point doit etre une chaine pour " + n);
        if (t == "AO") {
            if (!p.contains("min") || !p.contains("max") || !number(p["min"]) || !number(p["max"]) ||
                p["min"].get<double>() >= p["max"].get<double>())
                throw std::runtime_error("limites AO invalides");
        }
        if (t != "AO" && (p.contains("min") || p.contains("max")))
            throw std::runtime_error("min/max reserves aux commandes AO");
        if (dir == "telemetry") {
            if (p.contains("feedback_point")) throw std::runtime_error("feedback_point reserve aux commandes");
            if (p.contains("initial") &&
                ((t == "AI" && !number(p["initial"])) || (t == "BI" && !p["initial"].is_boolean())))
                throw std::runtime_error("initial incoherent pour " + n);
        } else if (p.contains("initial")) {
            throw std::runtime_error("initial reserve aux telemesures");
        }
    }
    for (const auto& p : c["points"]) {
        if (!p.contains("feedback_point")) continue;
        const std::string feedback = p["feedback_point"].get<std::string>();
        const auto* target = find_point(c, feedback, "telemetry");
        if (!target) throw std::runtime_error("feedback_point inconnu pour " + p["name"].get<std::string>());
        const std::string cmd_type = p["dnp3_type"].get<std::string>();
        const std::string measure_type = target->at("dnp3_type").get<std::string>();
        if ((cmd_type == "AO" && measure_type != "AI") || (cmd_type == "BO" && measure_type != "BI"))
            throw std::runtime_error("feedback_point de type incompatible pour " + p["name"].get<std::string>());
    }
    // Evite une ambiguite nom/alias au sein de la meme direction.
    for (const auto& p : c["points"]) {
        const auto alias = p.value("alias", p["name"].get<std::string>());
        if (alias == p["name"]) continue;
        for (const auto& other : c["points"]) {
            if (other["direction"] == p["direction"] && other["name"] == alias)
                throw std::runtime_error("alias identique au nom d'un autre point: " + alias);
        }
    }
}

Json load_config(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) throw std::runtime_error("Configuration introuvable: " + path);
    Json cfg = Json::parse(file);
    validate_config(cfg);
    return cfg;
}

const Json* find_index(const Json& cfg, const std::string& type, std::uint16_t index) {
    for (const auto& p : cfg["points"]) if (p["dnp3_type"] == type && p["index"] == index) return &p;
    return nullptr;
}

const Json* find_point(const Json& cfg, const std::string& name, const std::string& direction) {
    for (const auto& p : cfg["points"]) if (p["name"] == name && p["direction"] == direction) return &p;
    return nullptr;
}

const Json* find_cli_point(const Json& cfg, const std::string& key, const std::string& direction) {
    for (const auto& p : cfg["points"]) {
        if (p["direction"] == direction &&
            (p["name"] == key || (p.contains("alias") && p["alias"] == key))) return &p;
    }
    return nullptr;
}

void validate_value(const Json& point, const Json& value) {
    const auto type = point.at("dnp3_type").get<std::string>();
    const auto name = point.at("name").get<std::string>();
    if (type == "AI" || type == "AO") {
        if (!number(value)) throw std::runtime_error("Point " + name + ": expected a finite analog number");
        if (type == "AO" && (value.get<double>() < point.at("min").get<double>() ||
                              value.get<double>() > point.at("max").get<double>()))
            throw std::runtime_error("Point " + name + ": value outside configured min/max limits");
    } else if (type == "BI" || type == "BO") {
        if (!value.is_boolean()) throw std::runtime_error("Point " + name + ": expected a JSON boolean");
    } else {
        throw std::runtime_error("Point " + name + ": unsupported DNP3 type " + type);
    }
}

const Json& validate_message(const Json& msg, const Json& cfg, const std::string& kind) {
    if (kind != "command" && kind != "telemetry")
        throw std::runtime_error("Unsupported message direction: " + kind);
    if (!msg.is_object() || !schema_one(msg))
        throw std::runtime_error("Message schema_version must be the integer 1");
    for (const auto& field : {"kind", "device_id", "point", "request_id", "timestamp"}) {
        if (!nonempty_string(msg, field))
            throw std::runtime_error(std::string("Message ") + field + " must be a nonempty string");
    }
    if (msg.at("kind") != kind || msg.at("device_id") != cfg.at("device_id"))
        throw std::runtime_error("Message kind or device_id does not match the destination");
    const auto name = msg.at("point").get<std::string>();
    const auto* p = kind == "command" ? find_cli_point(cfg, name, kind) : find_point(cfg, name, kind);
    if (!p) throw std::runtime_error("Unknown " + kind + " point: " + name);
    if (!msg.contains("value")) throw std::runtime_error("Message value is required");
    validate_value(*p, msg.at("value"));
    return *p;
}

static std::string uuid() {
    std::random_device dev; std::mt19937_64 gen(dev());
    std::uniform_int_distribution<std::uint64_t> dist;
    const auto a = dist(gen), b = dist(gen);
    std::ostringstream ss;
    ss << std::hex << std::setfill('0') << std::setw(8) << (a >> 32) << "-"
       << std::setw(4) << ((a >> 16) & 0xffff) << "-"
       << std::setw(4) << (a & 0xffff) << "-"
       << std::setw(4) << (b >> 48) << "-"
       << std::setw(12) << (b & 0xffffffffffffULL);
    return ss.str();
}

std::string timestamp_now() {
    const auto now = std::chrono::system_clock::now();
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
    auto tt = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
    gmtime_r(&tt, &tm);
    std::ostringstream stamp;
    stamp << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S") << "." << std::setw(3)
          << std::setfill('0') << ms.count() << "+00:00";
    return stamp.str();
}

Json envelope(const std::string& device, const std::string& point, const Json& value, const std::string& kind) {
    return { {"schema_version", 1}, {"device_id", device}, {"point", point},
             {"value", value}, {"kind", kind}, {"request_id", uuid()}, {"timestamp", timestamp_now()} };
}

std::string topic(const std::string& device, const std::string& suffix) {
    return "edgecs/" + device + "/" + suffix;
}
} // namespace edgecs
