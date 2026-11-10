#include "common.hpp"

#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>

namespace {
using edgecs::Json;
int checks = 0;
void require(bool condition, const std::string& description) {
    ++checks;
    if (!condition) throw std::runtime_error("FAILED: " + description);
}
void rejects(const std::function<void()>& action, const std::string& description) {
    ++checks;
    try { action(); }
    catch (const std::exception& error) {
        if (std::string(error.what()).empty()) throw std::runtime_error("Empty rejection: " + description);
        return;
    }
    throw std::runtime_error("FAILED to reject: " + description);
}
Json sample(const Json& point) {
    const auto type = point.at("dnp3_type").get<std::string>();
    if (type == "BI" || type == "BO") return true;
    if (type == "AO") return (point.at("min").get<double>() + point.at("max").get<double>()) / 2;
    return point.value("initial", Json(17.25));
}

// These are the actual lookup/validation/envelope functions called by Gateway's
// DNP3 command handler and MQTT telemetry callback, exercised for every point.
void mapping_roundtrip(const Json& cfg) {
    const auto device = cfg.at("device_id").get<std::string>();
    for (const auto& point : cfg.at("points")) {
        const auto name = point.at("name").get<std::string>();
        const auto direction = point.at("direction").get<std::string>();
        const auto type = point.at("dnp3_type").get<std::string>();
        const auto index = point.at("index").get<std::uint16_t>();
        const auto* by_index = edgecs::find_index(cfg, type, index);
        require(by_index && *by_index == point, device + ": DNP3 mapping for " + name);
        require(edgecs::find_point(cfg, name, direction) == &point, name + ": canonical lookup");
        require(edgecs::find_cli_point(cfg, point.value("alias", name), direction) == &point, name + ": alias lookup");
        auto message = edgecs::envelope(device, name, sample(point), direction);
        require(edgecs::validate_message(message, cfg, direction) == point, name + ": envelope mapping");
        require(!message.at("request_id").get<std::string>().empty(), name + ": request id retained");
        require(message.at("timestamp").is_string(), name + ": timestamp retained");
        require(!edgecs::find_point(cfg, name, direction == "command" ? "telemetry" : "command"), name + ": direction isolated");
        if (direction == "command" && point.contains("alias")) {
            message["point"] = point.at("alias");
            require(edgecs::validate_message(message, cfg, direction) == point, name + ": command alias accepted");
        }
        if (point.contains("feedback_point")) {
            const auto feedback = point.at("feedback_point").get<std::string>();
            const auto reply = edgecs::envelope(device, feedback, sample(point), "telemetry");
            require(edgecs::validate_message(reply, cfg, "telemetry").at("name") == feedback, name + ": configured feedback");
        }
        if (type == "AO") {
            edgecs::validate_value(point, point.at("min"));
            edgecs::validate_value(point, point.at("max"));
            rejects([&] { edgecs::validate_value(point, point.at("min").get<double>() - 1); }, name + ": lower limit");
            rejects([&] { edgecs::validate_value(point, point.at("max").get<double>() + 1); }, name + ": upper limit");
        }
        const Json wrong_type = (type == "BI" || type == "BO") ? Json(1) : Json(true);
        rejects([&] { edgecs::validate_value(point, wrong_type); }, name + ": wrong value type");
        rejects([&] { edgecs::validate_value(point, "1"); }, name + ": string value");
        if (type == "AI" || type == "AO") {
            rejects([&] { edgecs::validate_value(point, std::numeric_limits<double>::infinity()); }, name + ": infinity");
            rejects([&] { edgecs::validate_value(point, std::numeric_limits<double>::quiet_NaN()); }, name + ": NaN");
        }
    }
}

void invalid_configs(const Json& cfg) {
    auto invalid = [&](const std::string& label, const std::function<void(Json&)>& edit) {
        auto copy = cfg; edit(copy);
        rejects([&] { edgecs::validate_config(copy); }, label);
    };
    invalid("float schema version", [](Json& c) { c["schema_version"] = 1.0; });
    invalid("missing identity", [](Json& c) { c.erase("device_id"); });
    invalid("invalid device identity", [](Json& c) { c["device_id"] = "bad/+#"; });
    invalid("empty DER type", [](Json& c) { c["der_type"] = ""; });
    invalid("unknown property", [](Json& c) { c["ignored"] = true; });
    invalid("invalid registration host", [](Json& c) { c["master_api_host"] = "invalid"; });
    invalid("DNP3 host type", [](Json& c) { c["dnp3"]["host"] = 10; });
    invalid("zero DNP3 port", [](Json& c) { c["dnp3"]["port"] = 0; });
    invalid("equal DNP3 addresses", [](Json& c) { c["dnp3"]["master_address"] = c["dnp3"]["outstation_address"]; });
    invalid("reserved DNP3 address", [](Json& c) { c["dnp3"]["outstation_address"] = 65520; });
    invalid("overflowing address", [](Json& c) { c["dnp3"]["outstation_address"] = std::numeric_limits<std::uint64_t>::max(); });
    invalid("MQTT port type", [](Json& c) { c["mqtt"]["port"] = true; });
    invalid("empty points", [](Json& c) { c["points"] = Json::array(); });
    invalid("malformed point", [](Json& c) { c["points"][0] = "point"; });
    invalid("missing unit", [](Json& c) { c["points"][0].erase("unit"); });
    invalid("duplicate names", [](Json& c) { c["points"][1]["name"] = c["points"][0]["name"]; });
    invalid("duplicate type/index", [](Json& c) { c["points"].push_back(c["points"][0]); c["points"].back()["name"] = "duplicate_mapping"; c["points"].back().erase("alias"); });
    invalid("ambiguous alias", [](Json& c) { c["points"][0]["alias"] = c["points"][1]["name"]; });
    invalid("alias type", [](Json& c) { c["points"][0]["alias"] = 10; });
    invalid("wrong direction", [](Json& c) { c["points"][0]["direction"] = "telemetry"; });
    invalid("unsupported type", [](Json& c) { c["points"][0]["dnp3_type"] = "COUNTER"; });
    invalid("negative index", [](Json& c) { c["points"][0]["index"] = -1; });
    invalid("overflowing index", [](Json& c) { c["points"][0]["index"] = std::numeric_limits<std::uint64_t>::max(); });
    invalid("fractional index", [](Json& c) { c["points"][0]["index"] = 0.5; });
    invalid("missing AO limits", [](Json& c) { c["points"][0].erase("min"); });
    invalid("reversed AO limits", [](Json& c) { c["points"][0]["max"] = c["points"][0]["min"]; });
    invalid("command initial value", [](Json& c) { c["points"][0]["initial"] = 1; });
    invalid("unknown feedback", [](Json& c) { c["points"][0]["feedback_point"] = "unknown"; });
    invalid("wrong feedback type", [](Json& c) { c["points"][0]["feedback_point"] = "running"; });
    invalid("telemetry initial type", [](Json& c) { c["points"][2]["initial"] = true; });
    invalid("telemetry feedback", [](Json& c) { c["points"][2]["feedback_point"] = "running"; });
}
void invalid_messages(const Json& cfg) {
    const auto& point = cfg.at("points").at(0);
    const auto message = edgecs::envelope(cfg.at("device_id"), point.at("name"), sample(point), "command");
    auto invalid = [&](const std::string& label, const std::function<void(Json&)>& edit) {
        auto copy = message; edit(copy);
        rejects([&] { edgecs::validate_message(copy, cfg, "command"); }, label);
    };
    invalid("message schema float", [](Json& m) { m["schema_version"] = 1.0; });
    invalid("message device isolation", [](Json& m) { m["device_id"] = "other-device"; });
    invalid("message device type", [](Json& m) { m["device_id"] = Json::object(); });
    invalid("message direction", [](Json& m) { m["kind"] = "telemetry"; });
    invalid("message kind type", [](Json& m) { m["kind"] = false; });
    invalid("unknown command", [](Json& m) { m["point"] = "unknown_command"; });
    invalid("message point type", [](Json& m) { m["point"] = false; });
    invalid("missing message value", [](Json& m) { m.erase("value"); });
    invalid("message value type", [](Json& m) { m["value"] = "30"; });
    invalid("missing request id", [](Json& m) { m.erase("request_id"); });
    invalid("empty request id", [](Json& m) { m["request_id"] = ""; });
    invalid("request id type", [](Json& m) { m["request_id"] = 1; });
    invalid("missing timestamp", [](Json& m) { m.erase("timestamp"); });
    invalid("timestamp type", [](Json& m) { m["timestamp"] = 1; });
    invalid("empty timestamp", [](Json& m) { m["timestamp"] = ""; });
    auto telemetry = edgecs::envelope(cfg.at("device_id"), "unknown_measurement", 5, "telemetry");
    rejects([&] { edgecs::validate_message(telemetry, cfg, "telemetry"); }, "unknown measurement");
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("Usage: test_common bess.json generator.json");
        const auto bess = edgecs::load_config(argv[1]);
        const auto generator = edgecs::load_config(argv[2]);
        mapping_roundtrip(bess); mapping_roundtrip(generator);
        require(edgecs::find_cli_point(bess, "power", "command"), "BESS command fixture");
        require(edgecs::find_index(generator, "AO", 3)->at("name") == "frequency_setpoint_hz", "sparse generator command fixture");
        require(edgecs::find_index(generator, "AI", 5)->at("name") == "measured_frequency_hz", "sparse generator telemetry fixture");
        require(edgecs::find_index(generator, "BI", 2)->at("name") == "generator_running", "sparse generator binary fixture");
        require(edgecs::topic(bess.at("device_id"), "edge/command") != edgecs::topic(generator.at("device_id"), "edge/command"), "device MQTT isolation");
        invalid_configs(bess); invalid_messages(bess);

        auto changed = generator;
        changed["device_id"] = "custom-der";
        changed["der_type"] = "NEW_DER_CATEGORY";
        changed["master_api_host"] = "127.0.0.1";
        std::map<std::string, std::string> renamed;
        int sequence = 0;
        for (auto& point : changed["points"]) {
            const auto name = "custom_point_" + std::to_string(++sequence);
            renamed[point.at("name").get<std::string>()] = name;
            point["name"] = name; point["alias"] = "alias_" + std::to_string(sequence);
            point["index"] = sequence * 7;
        }
        for (auto& point : changed["points"])
            if (point.contains("feedback_point")) point["feedback_point"] = renamed.at(point["feedback_point"].get<std::string>());
        edgecs::validate_config(changed); mapping_roundtrip(changed);
        require(!edgecs::find_index(changed, "AO", 3), "old index removed after reload");
        require(!edgecs::find_cli_point(changed, "frequency", "command"), "old alias removed after reload");
        auto maximum_index = changed;
        maximum_index["points"][0]["index"] = 65535;
        edgecs::validate_config(maximum_index);
        require(edgecs::find_index(maximum_index, "AO", 65535), "maximum point index accepted");
        auto legacy = bess; legacy.erase("mqtt"); edgecs::validate_config(legacy);
        require(edgecs::mqtt_host(bess) == "127.0.0.1" && edgecs::mqtt_port(bess) == 1883, "MQTT configuration");
        std::istringstream typed("pas-une-ip\n192.168.0.5\n");
        const auto original = std::cin.rdbuf(typed.rdbuf());
        const auto address = edgecs::prompt_ipv4("Test IP");
        std::cin.rdbuf(original);
        require(address == "192.168.0.5", "legacy prompt validates IPv4");
        std::cout << "PASS: " << checks << " configuration/mapping/envelope checks (active in Release)\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
