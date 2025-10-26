#include "gui.hpp"

#include "utils.hpp"

#include <imgui.h>
#include <imgui_internal.h>
#include <backends/imgui_impl_win32.h>
#include <backends/imgui_impl_dx11.h>

#include <algorithm>

GUIManager::GUIManager() {
    util::Logger::instance().setRealtimeCallback([this](const std::string& line) {
        m_logBuffer.push_back(line);
    });
}

void GUIManager::initialize(HWND hwnd, ID3D11Device* device, ID3D11DeviceContext* context) {
    if (m_initialized) {
        return;
    }

    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO();
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;

    ImGui::StyleColorsDark();
    ImGuiStyle& style = ImGui::GetStyle();
    style.FrameRounding = 6.0f;
    style.Colors[ImGuiCol_TitleBgActive] = ImVec4(0.231f, 0.510f, 0.965f, 1.0f);
    style.Colors[ImGuiCol_CheckMark] = ImVec4(0.231f, 0.510f, 0.965f, 1.0f);

    ImGui_ImplWin32_Init(hwnd);
    ImGui_ImplDX11_Init(device, context);

    m_initialized = true;
}

void GUIManager::shutdown() {
    if (!m_initialized) {
        return;
    }
    ImGui_ImplDX11_Shutdown();
    ImGui_ImplWin32_Shutdown();
    ImGui::DestroyContext();
    m_initialized = false;
}

void GUIManager::render(ProcessManager& processManager,
                        MemoryScanner& memoryScanner,
                        ConfigManager& configManager,
                        ModManager& modManager) {
    if (!m_initialized) {
        return;
    }

    ImGui_ImplDX11_NewFrame();
    ImGui_ImplWin32_NewFrame();
    ImGui::NewFrame();

    showDisclaimerModal();

    ImGui::SetNextWindowSize(ImVec2(900, 600), ImGuiCond_FirstUseEver);
    ImGui::Begin("Offline Mod Menu — VonDutch Edition", nullptr, ImGuiWindowFlags_MenuBar);

    if (ImGui::BeginTabBar("MainTabs")) {
        if (ImGui::BeginTabItem("Home")) {
            drawHomeTab();
            ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Mods")) {
            drawModsTab(modManager);
            ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Process")) {
            drawProcessTab(processManager);
            ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Log")) {
            drawLogTab();
            ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Settings")) {
            drawSettingsTab(configManager, processManager, modManager);
            ImGui::EndTabItem();
        }
        ImGui::EndTabBar();
    }

    drawStatusBar();

    ImGui::End();

    ImGui::Render();
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());

    modManager.tick();
}

void GUIManager::drawHomeTab() {
    ImGui::TextWrapped("Welcome to the Offline Mod Menu — VonDutch Edition. This toolkit keeps your singleplayer experiences fresh while staying fully offline. Use the Process tab to attach to your game, then explore the Mods tab to enable features like God Mode or Infinity Ammo.");
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Text("Scan Guidance");
    ImGui::BulletText("Shoot once when prompted to capture ammo changes.");
    ImGui::BulletText("Take controlled damage to capture health values.");
    ImGui::BulletText("Use the Next Scan button after each action to narrow results.");
    ImGui::BulletText("Freeze values only after confirming 'YES I OWN THIS COPY'.");
}

void GUIManager::drawModsTab(ModManager& modManager) {
    ImGui::Text("Core Mods");
    for (auto& mod : modManager.mods()) {
        if (!mod) {
            continue;
        }
        bool enabled = mod->isEnabled();
        if (ImGui::Checkbox(mod->getName(), &enabled)) {
            mod->setEnabled(enabled);
            util::Logger::instance().log(util::Logger::Level::Info, std::string(mod->getName()) + (enabled ? " enabled" : " disabled"));
        }
    }
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::TextDisabled("Community mods can be dropped into the /mods folder and will appear here automatically.");
}

void GUIManager::drawProcessTab(ProcessManager& processManager) {
    static std::vector<ProcessInfo> cachedProcesses;
    if (ImGui::Button("Refresh Processes")) {
        cachedProcesses = processManager.enumerate();
    }

    ImGui::SameLine();
    if (ImGui::Button("Detach")) {
        processManager.detach();
    }

    ImGui::Separator();
    ImGui::BeginChild("ProcessList", ImVec2(0, 300), true);
    for (const auto& proc : cachedProcesses) {
        ImGui::PushID(static_cast<int>(proc.pid));
        ImGuiSelectableFlags flags = ImGuiSelectableFlags_AllowDoubleClick;
        if (proc.blocked) {
            ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.9f, 0.3f, 0.3f, 1.0f));
        }
        if (ImGui::Selectable(proc.name.c_str(), false, flags)) {
            if (proc.blocked) {
                util::Logger::instance().log(util::Logger::Level::Warning, "Blocked process selection: " + proc.name);
            } else {
                if (!m_confirmOwnership) {
                    util::Logger::instance().log(util::Logger::Level::Warning, "Ownership confirmation required before attaching");
                } else if (!processManager.attach(proc.pid)) {
                    util::Logger::instance().log(util::Logger::Level::Error, "Failed to attach to process");
                }
            }
        }
        if (proc.blocked) {
            ImGui::PopStyleColor();
        }
        ImGui::PopID();
    }
    ImGui::EndChild();

    if (processManager.isAttached()) {
        ImGui::Text("Attached to: %s", processManager.currentProcessName()->c_str());
    } else {
        ImGui::Text("Mock mode active — no process attached.");
    }
}

void GUIManager::drawLogTab() {
    ImGui::BeginChild("LogPane", ImVec2(0, 0), true, ImGuiWindowFlags_HorizontalScrollbar);
    ImGui::PushFont(ImGui::GetIO().Fonts->Fonts[0]);
    for (const auto& line : m_logBuffer) {
        ImGui::TextUnformatted(line.c_str());
    }
    if (ImGui::GetScrollY() >= ImGui::GetScrollMaxY()) {
        ImGui::SetScrollHereY(1.0f);
    }
    ImGui::PopFont();
    ImGui::EndChild();
}

void GUIManager::drawSettingsTab(ConfigManager& configManager, ProcessManager& processManager, ModManager& modManager) {
    if (!processManager.isAttached()) {
        ImGui::TextDisabled("Attach to a process to manage configs.");
        return;
    }

    const std::string processName = *processManager.currentProcessName();

    if (ImGui::Button("Load Config")) {
        if (auto config = configManager.load(processName)) {
            for (auto& mod : modManager.mods()) {
                if (mod) {
                    mod->setEnabled(config->mods[mod->getName()].enabled);
                }
            }
            util::Logger::instance().log(util::Logger::Level::Info, "Config loaded for " + processName);
        }
    }

    ImGui::SameLine();
    if (ImGui::Button("Save Config")) {
        ProcessConfig cfg;
        for (auto& mod : modManager.mods()) {
            if (mod) {
                cfg.mods[mod->getName()] = ModState{ mod->isEnabled() };
            }
        }
        configManager.save(processName, cfg);
    }

    ImGui::Separator();
    ImGui::Checkbox("I confirm YES I OWN THIS COPY", &m_confirmOwnership);
    if (!m_confirmOwnership) {
        ImGui::TextColored(ImVec4(0.9f, 0.3f, 0.3f, 1.0f), "Ownership confirmation required before modifying memory.");
    }
}

void GUIManager::drawStatusBar() {
    ImGui::Separator();
    ImGui::Text("Status: %s", m_statusText.c_str());
    ImGui::SameLine();
    if (m_isScanning) {
        ImGui::ProgressBar(m_scanProgress, ImVec2(200, 0), "Scanning");
    } else {
        ImGui::Text("\t");
    }
}

void GUIManager::showDisclaimerModal() {
    if (!m_disclaimerAccepted) {
        ImGui::OpenPopup("DisclaimerPopup");
    }

    if (ImGui::BeginPopupModal("DisclaimerPopup", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::TextWrapped("This tool is for offline, singleplayer titles you own. Never use it in multiplayer.");
        ImGui::Spacing();
        ImGui::Text("Type YES to proceed:");
        static char buffer[8] = {};
        ImGui::InputText("", buffer, sizeof(buffer));
        if (ImGui::Button("Confirm")) {
            if (std::string(buffer) == "YES") {
                m_disclaimerAccepted = true;
                ImGui::CloseCurrentPopup();
            }
        }
        ImGui::SameLine();
        if (ImGui::Button("Exit")) {
            m_shouldClose = true;
        }
        ImGui::EndPopup();
    }
}

