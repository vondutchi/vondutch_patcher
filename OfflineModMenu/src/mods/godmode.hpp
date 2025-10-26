#pragma once

#include "base_mod.hpp"

#include "../memory.hpp"
#include "../utils.hpp"

class GodModeMod : public BaseMod {
public:
    GodModeMod();

    void onAttach(HANDLE process) override;
    void onDetach() override;
    void onTick() override;
    const char* getName() override { return "God Mode"; }
    bool isCompatible(const std::string& processName) override;

private:
    MemoryScanner m_scanner;
    uintptr_t m_lastAddress = 0;
};

