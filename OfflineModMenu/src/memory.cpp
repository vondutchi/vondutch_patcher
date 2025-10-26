#include "memory.hpp"

#include "utils.hpp"

#include <algorithm>
#include <chrono>

MemoryScanner::MemoryScanner(HANDLE process)
    : m_process(process) {
}

MemoryScanner::~MemoryScanner() {
    clearFreezes();
}

void MemoryScanner::setProcess(HANDLE process) {
    m_process = process;
}

bool MemoryScanner::read(uintptr_t address, void* buffer, size_t size) const {
    if (!m_process) {
        return false;
    }
    SIZE_T bytesRead = 0;
    if (!ReadProcessMemory(m_process, reinterpret_cast<LPCVOID>(address), buffer, size, &bytesRead)) {
        return false;
    }
    return bytesRead == size;
}

bool MemoryScanner::write(uintptr_t address, const void* buffer, size_t size) const {
    if (!m_process) {
        return false;
    }
    SIZE_T bytesWritten = 0;
    if (!WriteProcessMemory(m_process, reinterpret_cast<LPVOID>(address), buffer, size, &bytesWritten)) {
        return false;
    }
    return bytesWritten == size;
}

std::optional<MemorySnapshot> MemoryScanner::takeSnapshot(uintptr_t base, size_t size) {
    if (!m_process || base == 0 || size == 0) {
        return std::nullopt;
    }

    MemorySnapshot snapshot;
    snapshot.base = base;
    snapshot.data.resize(size);

    SIZE_T bytesRead = 0;
    if (!ReadProcessMemory(m_process, reinterpret_cast<LPCVOID>(base), snapshot.data.data(), size, &bytesRead)) {
        util::Logger::instance().log(util::Logger::Level::Error, "Snapshot read failed");
        return std::nullopt;
    }

    snapshot.data.resize(bytesRead);
    return snapshot;
}

std::vector<uintptr_t> MemoryScanner::compareSnapshots(const MemorySnapshot& previous, const MemorySnapshot& current, int expectedDelta) {
    std::vector<uintptr_t> results;

    size_t count = std::min(previous.data.size(), current.data.size());
    for (size_t i = 0; i + sizeof(int) <= count; i += sizeof(int)) {
        int prevValue = *reinterpret_cast<const int*>(&previous.data[i]);
        int currValue = *reinterpret_cast<const int*>(&current.data[i]);
        if (currValue - prevValue == expectedDelta) {
            results.push_back(previous.base + static_cast<uintptr_t>(i));
        }
    }

    util::Logger::instance().log(util::Logger::Level::Info, "compareSnapshots narrowed to " + std::to_string(results.size()) + " candidates");
    return results;
}

std::vector<uintptr_t> MemoryScanner::filterCandidates(const std::vector<uintptr_t>& candidates, int expectedValue) {
    std::vector<uintptr_t> filtered;
    filtered.reserve(candidates.size());

    for (uintptr_t address : candidates) {
        int value = 0;
        if (read(address, &value, sizeof(value)) && value == expectedValue) {
            filtered.push_back(address);
        }
    }

    util::Logger::instance().log(util::Logger::Level::Info, "filterCandidates resulted in " + std::to_string(filtered.size()) + " matches");
    return filtered;
}

void MemoryScanner::freezeValue(uintptr_t address, const void* buffer, size_t size) {
    std::lock_guard<std::mutex> lock(m_freezeMutex);
    auto it = std::find_if(m_freezeEntries.begin(), m_freezeEntries.end(), [address](const FreezeEntry& entry) {
        return entry.address == address;
    });

    if (it == m_freezeEntries.end()) {
        FreezeEntry entry;
        entry.address = address;
        entry.value.assign(reinterpret_cast<const uint8_t*>(buffer), reinterpret_cast<const uint8_t*>(buffer) + size);
        entry.active = true;
        m_freezeEntries.push_back(std::move(entry));
    } else {
        it->value.assign(reinterpret_cast<const uint8_t*>(buffer), reinterpret_cast<const uint8_t*>(buffer) + size);
        it->active = true;
    }

    if (!m_freezeRequested.load()) {
        m_freezeRequested = true;
        m_freezeThread = std::thread(&MemoryScanner::freezeLoop, this);
    }
}

void MemoryScanner::clearFreezes() {
    {
        std::lock_guard<std::mutex> lock(m_freezeMutex);
        m_freezeEntries.clear();
    }

    m_freezeRequested = false;
    if (m_freezeThread.joinable()) {
        m_freezeThread.join();
    }
}

void MemoryScanner::freezeLoop() {
    util::Logger::instance().log(util::Logger::Level::Info, "Freeze loop started");

    while (m_freezeRequested.load()) {
        {
            std::lock_guard<std::mutex> lock(m_freezeMutex);
            for (auto& entry : m_freezeEntries) {
                if (!entry.active) {
                    continue;
                }
                if (!write(entry.address, entry.value.data(), entry.value.size())) {
                    util::Logger::instance().log(util::Logger::Level::Warning, "Failed to maintain frozen value");
                }
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(30));
    }

    util::Logger::instance().log(util::Logger::Level::Info, "Freeze loop exited");
}

