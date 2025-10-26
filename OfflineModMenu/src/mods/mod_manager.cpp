#include "mod_manager.hpp"

#include "godmode.hpp"
#include "infammo.hpp"

#include "../utils.hpp"

#include <filesystem>
#include <memory>

namespace {
std::shared_ptr<BaseMod> createModInstance(const std::filesystem::path& path) {
    // Placeholder for future dynamic mod loading (DLL or script).
    // Currently the project only ships with static mods compiled in.
    util::Logger::instance().log(util::Logger::Level::Info, "Discovered placeholder mod file: " + path.string());
    return nullptr;
}
}

ModManager::ModManager() {
    m_modDirectory = std::filesystem::current_path() / "mods";
}

void ModManager::discoverMods() {
    m_mods.clear();

    // Built-in mods compiled directly into the application.
    m_mods.push_back(std::make_shared<GodModeMod>());
    m_mods.push_back(std::make_shared<InfAmmoMod>());

    util::ensureDirectories({ m_modDirectory });

    for (const auto& entry : std::filesystem::directory_iterator(m_modDirectory)) {
        if (!entry.is_regular_file()) {
            continue;
        }

        if (auto mod = createModInstance(entry.path())) {
            m_mods.push_back(std::move(mod));
        }
    }
}

void ModManager::attachAll(HANDLE process, const std::string& processName) {
    for (auto& mod : m_mods) {
        if (mod && mod->isCompatible(processName)) {
            mod->onAttach(process);
        }
    }
}

void ModManager::detachAll() {
    for (auto& mod : m_mods) {
        if (mod) {
            mod->onDetach();
        }
    }
}

void ModManager::tick() {
    for (auto& mod : m_mods) {
        if (mod && mod->isEnabled()) {
            mod->onTick();
        }
    }
}

