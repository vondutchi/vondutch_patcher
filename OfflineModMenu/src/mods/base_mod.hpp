#pragma once

#include <windows.h>

#include <string>

class BaseMod {
public:
    virtual void onAttach(HANDLE process) {}
    virtual void onDetach() {}
    virtual void onTick() {}
    virtual const char* getName() { return "Unnamed"; }
    virtual bool isCompatible(const std::string& processName) { return !processName.empty(); }
    virtual ~BaseMod() = default;

    bool isEnabled() const { return m_enabled; }
    void setEnabled(bool enabled) { m_enabled = enabled; }

protected:
    HANDLE m_process = nullptr;
    bool m_enabled = false;
};

