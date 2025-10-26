#pragma once

#include <windows.h>

#include <cstdint>
#include <vector>
#include <atomic>
#include <thread>
#include <mutex>
#include <optional>

struct MemorySnapshot {
    uintptr_t base = 0;
    std::vector<uint8_t> data;
};

//! Helper struct representing a frozen memory address.
struct FreezeEntry {
    uintptr_t address = 0;
    std::vector<uint8_t> value;
    bool active = false;
};

class MemoryScanner {
public:
    explicit MemoryScanner(HANDLE process = nullptr);
    ~MemoryScanner();

    void setProcess(HANDLE process);

    //! Safely reads process memory.
    bool read(uintptr_t address, void* buffer, size_t size) const;

    //! Safely writes process memory.
    bool write(uintptr_t address, const void* buffer, size_t size) const;

    //! Creates a snapshot from a base address and length.
    std::optional<MemorySnapshot> takeSnapshot(uintptr_t base, size_t size);

    //! Compares two snapshots and returns candidate addresses matching the expected delta.
    std::vector<uintptr_t> compareSnapshots(const MemorySnapshot& previous, const MemorySnapshot& current, int expectedDelta);

    //! Filters candidate addresses by scanning for an exact value.
    std::vector<uintptr_t> filterCandidates(const std::vector<uintptr_t>& candidates, int expectedValue);

    //! Adds a freeze entry that will be maintained in the background.
    void freezeValue(uintptr_t address, const void* buffer, size_t size);

    //! Stops all freeze operations.
    void clearFreezes();

private:
    void freezeLoop();

    HANDLE m_process = nullptr;
    std::vector<FreezeEntry> m_freezeEntries;
    std::thread m_freezeThread;
    std::atomic<bool> m_freezeRequested{false};
    mutable std::mutex m_freezeMutex;
};

