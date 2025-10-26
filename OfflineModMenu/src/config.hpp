#pragma once

#include <windows.h>

#include <nlohmann/json.hpp>

#include <optional>
#include <string>
#include <unordered_map>
#include <filesystem>

struct ModState {
    bool enabled = false;
};

struct ProcessConfig {
    std::unordered_map<std::string, uintptr_t> addresses;
    std::unordered_map<std::string, ModState> mods;
};

class ConfigManager {
public:
    ConfigManager();

    //! Loads configuration for the specified process name.
    std::optional<ProcessConfig> load(const std::string& processName);

    //! Saves configuration for the specified process name.
    void save(const std::string& processName, const ProcessConfig& config);

private:
    std::filesystem::path resolvePath(const std::string& processName) const;
};

