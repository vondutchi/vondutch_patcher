#pragma once

#include "base_mod.hpp"

#include <windows.h>

#include <filesystem>
#include <memory>
#include <vector>
#include <string>

class ModManager {
public:
    ModManager();

    //! Loads built-in and future mods from the mods directory.
    void discoverMods();

    //! Invoked when attaching to a process.
    void attachAll(HANDLE process, const std::string& processName);

    //! Invoked when detaching from a process.
    void detachAll();

    //! Runs per-frame updates for enabled mods.
    void tick();

    //! Returns the loaded mods.
    std::vector<std::shared_ptr<BaseMod>>& mods() { return m_mods; }

private:
    std::filesystem::path m_modDirectory;
    std::vector<std::shared_ptr<BaseMod>> m_mods;
};

