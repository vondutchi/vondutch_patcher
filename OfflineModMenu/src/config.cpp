#include "config.hpp"

#include "utils.hpp"

#include <algorithm>
#include <fstream>

using nlohmann::json;

ConfigManager::ConfigManager() {
    util::ensureDirectories({ std::filesystem::current_path() / "configs" });
}

std::optional<ProcessConfig> ConfigManager::load(const std::string& processName) {
    const auto path = resolvePath(processName);
    if (!std::filesystem::exists(path)) {
        util::Logger::instance().log(util::Logger::Level::Warning, "No config found for " + processName);
        return std::nullopt;
    }

    std::ifstream file(path);
    if (!file.is_open()) {
        util::Logger::instance().log(util::Logger::Level::Error, "Failed to open config for " + processName);
        return std::nullopt;
    }

    json j;
    file >> j;

    ProcessConfig config;
    if (j.contains("addresses")) {
        for (auto& [key, value] : j["addresses"].items()) {
            config.addresses[key] = value.get<uintptr_t>();
        }
    }

    if (j.contains("mods")) {
        for (auto& [key, value] : j["mods"].items()) {
            config.mods[key] = ModState{ value.value("enabled", false) };
        }
    }

    util::Logger::instance().log(util::Logger::Level::Info, "Loaded config for " + processName);
    return config;
}

void ConfigManager::save(const std::string& processName, const ProcessConfig& config) {
    json j;
    for (const auto& [name, address] : config.addresses) {
        j["addresses"][name] = address;
    }

    for (const auto& [name, state] : config.mods) {
        j["mods"][name]["enabled"] = state.enabled;
    }

    const auto path = resolvePath(processName);
    std::ofstream file(path);
    if (!file.is_open()) {
        util::Logger::instance().log(util::Logger::Level::Error, "Unable to save config for " + processName);
        return;
    }

    file << std::setw(4) << j;
    util::Logger::instance().log(util::Logger::Level::Info, "Saved config for " + processName);
}

std::filesystem::path ConfigManager::resolvePath(const std::string& processName) const {
    auto sanitized = processName;
    std::replace_if(sanitized.begin(), sanitized.end(), [](char c) { return c == ' ' || c == ':'; }, '_');
    return std::filesystem::current_path() / "configs" / (sanitized + ".json");
}

