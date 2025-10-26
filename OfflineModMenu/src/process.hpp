#pragma once

#include <windows.h>

#include <string>
#include <vector>
#include <optional>

struct ProcessInfo {
    DWORD pid = 0;
    std::string name;
    bool blocked = false;
};

class ProcessManager {
public:
    ProcessManager();

    //! Enumerates running processes and caches the result.
    std::vector<ProcessInfo> enumerate();

    //! Attempts to attach to a specific process ID.
    bool attach(DWORD pid);

    //! Detaches from the current process and releases handles.
    void detach();

    //! Returns whether the manager currently has an attached handle.
    bool isAttached() const { return m_processHandle != nullptr; }

    //! Provides access to the raw process handle.
    HANDLE handle() const { return m_processHandle; }

    //! Returns the currently attached process name if available.
    std::optional<std::string> currentProcessName() const;

    //! Returns true if the provided process name is known to be disallowed.
    static bool isBlockedProcess(const std::string& name);

private:
    void reset();

    HANDLE m_processHandle = nullptr;
    std::string m_currentProcessName;
};

