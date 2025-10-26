#include "infammo.hpp"

namespace {
constexpr int kDefaultAmmo = 999;
}

InfAmmoMod::InfAmmoMod() {
    m_enabled = false;
}

void InfAmmoMod::onAttach(HANDLE process) {
    m_process = process;
    m_scanner.setProcess(process);
    util::Logger::instance().log(util::Logger::Level::Info, "Infinity Ammo attached");
}

void InfAmmoMod::onDetach() {
    m_scanner.clearFreezes();
    m_lastAddress = 0;
    m_maxAmmo = 0;
    util::Logger::instance().log(util::Logger::Level::Info, "Infinity Ammo detached");
}

bool InfAmmoMod::isCompatible(const std::string& processName) {
    return !processName.empty();
}

void InfAmmoMod::onTick() {
    if (!m_enabled || !m_process) {
        return;
    }

    int desiredAmmo = m_maxAmmo > 0 ? m_maxAmmo : kDefaultAmmo;

    if (m_lastAddress != 0) {
        m_scanner.freezeValue(m_lastAddress, &desiredAmmo, sizeof(desiredAmmo));
        return;
    }

    util::Logger::instance().log(util::Logger::Level::Info, "Infinity Ammo waiting for manual scan (mock mode)");
}

