#pragma once

#include "base_mod.hpp"

#include "../memory.hpp"
#include "../utils.hpp"

class InfAmmoMod : public BaseMod {
public:
    InfAmmoMod();

    void onAttach(HANDLE process) override;
    void onDetach() override;
    void onTick() override;
    const char* getName() override { return "Infinity Ammo"; }
    bool isCompatible(const std::string& processName) override;

private:
    MemoryScanner m_scanner;
    uintptr_t m_lastAddress = 0;
    int m_maxAmmo = 0;
};

