#include "registry.hpp"
#include <arpa/inet.h>
#include <stdexcept>

namespace edgecs {

bool allowed_dnp3_host(const std::string& ip) {
    in_addr v4{};
    if (inet_pton(AF_INET, ip.c_str(), &v4) == 1) {
        const auto a = reinterpret_cast<const unsigned char*>(&v4.s_addr);
        // Loopback 127/8, RFC1918: 10/8, 172.16/12, 192.168/16.
        return a[0] == 127 || a[0] == 10 ||
               (a[0] == 172 && a[1] >= 16 && a[1] <= 31) ||
               (a[0] == 192 && a[1] == 168);
    }
    in6_addr v6{};
    if (inet_pton(AF_INET6, ip.c_str(), &v6) == 1) {
        const auto* b = v6.s6_addr;
        bool loopback = true;
        for (int i = 0; i < 15; ++i) if (b[i] != 0) loopback = false;
        if (loopback && b[15] == 1) return true;
        return (b[0] & 0xFE) == 0xFC; // fc00::/7 (ULA)
    }
    return false;
}

ConfigRegistry::Decision ConfigRegistry::inspect(const Json& cfg) const {
    validate_config(cfg);
    const std::string dev = cfg.at("device_id").get<std::string>();
    const std::string host = cfg.at("dnp3").at("host").get<std::string>();
    const int port = cfg.at("dnp3").at("port").get<int>();
    if (!allowed_dnp3_host(host))
        throw std::runtime_error("Adresse DNP3 non privee ou non autorisee: " + host);
    auto existing = devices_.find(dev);
    if (existing != devices_.end()) {
        if (existing->second == cfg) return Decision::AlreadyRegistered;
        throw std::runtime_error("device_id deja utilise avec une configuration differente: " + dev);
    }
    for (const auto& [other_dev, other_cfg] : devices_) {
        const auto& remote = other_cfg.at("dnp3");
        if (remote.at("host") == host && remote.at("port") == port)
            throw std::runtime_error("Une autre Gateway utilise deja ce host:port: " + other_dev);
    }
    return Decision::NewDevice;
}

void ConfigRegistry::insert(const Json& cfg) {
    if (inspect(cfg) != Decision::NewDevice)
        throw std::runtime_error("Enregistrement deja present");
    const auto dev = cfg.at("device_id").get<std::string>();
    const auto now = timestamp_now();
    devices_.emplace(dev, cfg);
    runtime_.emplace(dev, Json{
        {"registered_at", now}, {"last_registration_at", now},
        {"connection", {{"state", "created"}, {"updated_at", now}}},
        {"latest_telemetry", Json::object()}
    });
}

const Json* ConfigRegistry::get(const std::string& device_id) const {
    auto i = devices_.find(device_id);
    return i == devices_.end() ? nullptr : &i->second;
}

const Json* ConfigRegistry::point(const std::string& device_id,
                                  const std::string& point_name,
                                  const std::string& direction) const {
    auto* cfg = get(device_id);
    return cfg ? find_cli_point(*cfg, point_name, direction) : nullptr;
}

Json ConfigRegistry::device(const std::string& device_id) const {
    const auto* cfg = get(device_id);
    if (!cfg) return nullptr;
    Json snapshot = *cfg;
    snapshot["commands"] = Json::array();
    snapshot["telemetry"] = Json::array();
    for (const auto& point : cfg->at("points")) {
        snapshot[point.at("direction") == "command" ? "commands" : "telemetry"].push_back(point);
    }
    snapshot.update(runtime_.at(device_id));
    return snapshot;
}

Json ConfigRegistry::devices() const {
    Json list = Json::array();
    for (const auto& entry : devices_) list.push_back(device(entry.first));
    return list;
}

void ConfigRegistry::touch_registration(const std::string& device_id) {
    auto found = runtime_.find(device_id);
    if (found == runtime_.end()) throw std::runtime_error("Unknown registered device: " + device_id);
    found->second["last_registration_at"] = timestamp_now();
}

void ConfigRegistry::set_connection_state(const std::string& device_id, const std::string& state) {
    auto found = runtime_.find(device_id);
    if (found == runtime_.end()) throw std::runtime_error("Unknown registered device: " + device_id);
    if (state.empty()) throw std::runtime_error("Connection state must be nonempty");
    found->second["connection"] = {{"state", state}, {"updated_at", timestamp_now()}};
}

Json ConfigRegistry::update_telemetry(const std::string& device_id, const std::string& type,
                                     std::uint16_t index, const Json& value,
                                     std::uint8_t flags, std::uint64_t dnp3_timestamp) {
    const auto* cfg = get(device_id);
    if (!cfg) throw std::runtime_error("Unknown registered device: " + device_id);
    const auto* point = find_index(*cfg, type, index);
    if (!point || point->at("direction") != "telemetry")
        throw std::runtime_error("Unknown telemetry mapping for " + device_id + ": " + type +
                                 "[" + std::to_string(index) + "]");
    validate_value(*point, value);
    const auto name = point->at("name").get<std::string>();
    auto message = envelope(device_id, name, value, "telemetry");
    message["dnp3_type"] = type;
    message["dnp3_index"] = index;
    message["quality_flags"] = flags;
    message["dnp3_timestamp"] = dnp3_timestamp;
    message["received_at"] = message.at("timestamp");
    runtime_.at(device_id)["latest_telemetry"][name] = message;
    return message;
}
} // namespace edgecs
