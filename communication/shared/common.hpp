#pragma once

#include <nlohmann/json.hpp>
#include <string>
#include <cstdint>

namespace edgecs {
using Json = nlohmann::json;

std::string env(const char* key, const std::string& fallback = "");
// Demande une IP IPv4 (Entrée = suggestion). Une IP vide ou invalide est rejetee.
std::string mqtt_host(const Json& cfg);
int mqtt_port(const Json& cfg);
std::string prompt_ipv4(const std::string& question, const std::string& suggestion = "127.0.0.1");
// Recherche le nom exact OU un alias CLI defini dans le JSON, pour une direction donnee.
const Json* find_cli_point(const Json& cfg, const std::string& name_or_alias, const std::string& direction);
Json load_config(const std::string& path);
void validate_config(const Json& cfg);
const Json* find_index(const Json& cfg, const std::string& type, std::uint16_t index);
const Json* find_point(const Json& cfg, const std::string& name, const std::string& direction);
// Shared validation for values entering a protocol adapter or simulator.
void validate_value(const Json& point, const Json& value);
// Command aliases are accepted here; the returned point always has its canonical name.
const Json& validate_message(const Json& msg, const Json& cfg, const std::string& kind);
std::string timestamp_now();
Json envelope(const std::string& device, const std::string& point, const Json& value,
              const std::string& kind);
std::string topic(const std::string& device, const std::string& suffix);
} // namespace edgecs
