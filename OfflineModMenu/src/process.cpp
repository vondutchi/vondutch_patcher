#include "process.hpp"

#include "utils.hpp"

#include <psapi.h>

#include <algorithm>
#include <array>
#include <unordered_set>

namespace {
const std::unordered_set<std::string> kBlockedNames = {
    "cs2.exe",
    "valorant.exe",
    "fortnite.exe",
    "apex.exe",
    "overwatch.exe"
};
}

ProcessManager::ProcessManager() = default;

std::vector<ProcessInfo> ProcessManager::enumerate() {
    std::vector<ProcessInfo> processes;
    DWORD processIds[1024] = {};
    DWORD bytesReturned = 0;

    if (!EnumProcesses(processIds, sizeof(processIds), &bytesReturned)) {
        util::Logger::instance().log(util::Logger::Level::Error, "Failed to enumerate processes");
        return processes;
    }

    const DWORD processCount = bytesReturned / sizeof(DWORD);
    processes.reserve(processCount);

    for (DWORD i = 0; i < processCount; ++i) {
        DWORD pid = processIds[i];
        if (pid == 0) {
            continue;
        }

        HANDLE handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid);
        if (!handle) {
            continue;
        }

        std::array<wchar_t, MAX_PATH> nameBuffer{};
        if (GetModuleBaseNameW(handle, nullptr, nameBuffer.data(), static_cast<DWORD>(nameBuffer.size()))) {
            std::string utf8Name = util::wideToUtf8(nameBuffer.data());
            ProcessInfo info;
            info.pid = pid;
            info.name = utf8Name;
            info.blocked = isBlockedProcess(utf8Name);
            processes.emplace_back(std::move(info));
        }

        CloseHandle(handle);
    }

    std::sort(processes.begin(), processes.end(), [](const ProcessInfo& a, const ProcessInfo& b) {
        return util::toLower(a.name) < util::toLower(b.name);
    });

    return processes;
}

bool ProcessManager::attach(DWORD pid) {
    reset();

    HANDLE handle = OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!handle) {
        util::Logger::instance().log(util::Logger::Level::Error, "Unable to open target process handle");
        return false;
    }

    std::array<wchar_t, MAX_PATH> nameBuffer{};
    if (!GetModuleBaseNameW(handle, nullptr, nameBuffer.data(), static_cast<DWORD>(nameBuffer.size()))) {
        CloseHandle(handle);
        util::Logger::instance().log(util::Logger::Level::Error, "Failed to resolve process name");
        return false;
    }

    std::string utf8Name = util::wideToUtf8(nameBuffer.data());
    if (isBlockedProcess(utf8Name)) {
        CloseHandle(handle);
        util::Logger::instance().log(util::Logger::Level::Warning, "Refused to attach to blocked process: " + utf8Name);
        return false;
    }

    m_processHandle = handle;
    m_currentProcessName = utf8Name;
    util::Logger::instance().log(util::Logger::Level::Info, "Attached to process: " + utf8Name);
    return true;
}

void ProcessManager::detach() {
    if (m_processHandle) {
        CloseHandle(m_processHandle);
        m_processHandle = nullptr;
        util::Logger::instance().log(util::Logger::Level::Info, "Detached from process");
    }
    m_currentProcessName.clear();
}

std::optional<std::string> ProcessManager::currentProcessName() const {
    if (!m_currentProcessName.empty()) {
        return m_currentProcessName;
    }
    return std::nullopt;
}

bool ProcessManager::isBlockedProcess(const std::string& name) {
    return kBlockedNames.count(util::toLower(name)) > 0;
}

void ProcessManager::reset() {
    if (m_processHandle) {
        CloseHandle(m_processHandle);
        m_processHandle = nullptr;
    }
    m_currentProcessName.clear();
}

