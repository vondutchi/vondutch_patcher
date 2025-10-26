#include "godmode.hpp"

#include <algorithm>

namespace {
constexpr int kDesiredHealth = 100;
}

GodModeMod::GodModeMod() {
    m_enabled = false;
}

void GodModeMod::onAttach(HANDLE process) {
    m_process = process;
    m_scanner.setProcess(process);
    util::Logger::instance().log(util::Logger::Level::Info, "God Mode attached");
}

void GodModeMod::onDetach() {
    m_scanner.clearFreezes();
    m_lastAddress = 0;
    util::Logger::instance().log(util::Logger::Level::Info, "God Mode detached");
}

bool GodModeMod::isCompatible(const std::string& processName) {
    return !processName.empty();
}

void GodModeMod::onTick() {
    if (!m_enabled || !m_process) {
        return;
    }

    if (m_lastAddress != 0) {
        m_scanner.freezeValue(m_lastAddress, &kDesiredHealth, sizeof(kDesiredHealth));
        return;
    }

    // In a real implementation we would perform heuristic scanning.
    // For the template we simply log guidance for the user.
    util::Logger::instance().log(util::Logger::Level::Info, "God Mode waiting for manual scan (mock mode)");
}

