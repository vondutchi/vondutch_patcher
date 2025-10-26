#pragma once

#include "process.hpp"
#include "memory.hpp"
#include "config.hpp"
#include "mods/mod_manager.hpp"

#include <d3d11.h>
#include <wrl/client.h>

#include <functional>
#include <string>
#include <vector>

class GUIManager {
public:
    GUIManager();

    void initialize(HWND hwnd, ID3D11Device* device, ID3D11DeviceContext* context);
    void shutdown();

    void render(ProcessManager& processManager,
                MemoryScanner& memoryScanner,
                ConfigManager& configManager,
                ModManager& modManager);

    bool shouldClose() const { return m_shouldClose; }

private:
    void drawHomeTab();
    void drawModsTab(ModManager& modManager);
    void drawProcessTab(ProcessManager& processManager);
    void drawLogTab();
    void drawSettingsTab(ConfigManager& configManager, ProcessManager& processManager, ModManager& modManager);
    void drawStatusBar();

    void showDisclaimerModal();

    bool m_initialized = false;
    bool m_shouldClose = false;
    bool m_disclaimerAccepted = false;
    bool m_confirmOwnership = false;

    std::string m_statusText = "Ready";
    float m_scanProgress = 0.0f;
    bool m_isScanning = false;

    std::vector<std::string> m_logBuffer;
};

