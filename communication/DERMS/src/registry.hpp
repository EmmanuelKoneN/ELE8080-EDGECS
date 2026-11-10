#pragma once
#include "common.hpp"
#include <map>
#include <string>

namespace edgecs {

// Device configuration and runtime discovery state. DNP3 indices are local to a
// device and point type. The caller must synchronize all access (including get()
// pointers) when using this registry from HTTPS, MQTT, and DNP3 callbacks.
class ConfigRegistry {
public:
    enum class Decision { NewDevice, AlreadyRegistered };
    // Vérifie la config et les collisions. Ne modifie pas le registre.
    Decision inspect(const Json& cfg) const;
    // À appeler uniquement quand la création de session DNP3 a réussi.
    void insert(const Json& cfg);
    const Json* get(const std::string& device_id) const;
    const Json* point(const std::string& device_id, const std::string& point_name,
                      const std::string& direction) const;
    // Discovery snapshots are independent JSON copies; get() remains raw config.
    Json device(const std::string& device_id) const;
    Json devices() const;
    void touch_registration(const std::string& device_id);
    void set_connection_state(const std::string& device_id, const std::string& state);
    Json update_telemetry(const std::string& device_id, const std::string& type,
                          std::uint16_t index, const Json& value,
                          std::uint8_t flags, std::uint64_t dnp3_timestamp);
private:
    std::map<std::string, Json> devices_;
    std::map<std::string, Json> runtime_;
};

// Atténuation SSRF via l'API d'enregistrement; seulement adresses de labo.
bool allowed_dnp3_host(const std::string& ip);
} // namespace edgecs
