#include "utils.hpp"

#include <windows.h>

#include <algorithm>
#include <codecvt>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <cctype>

namespace util {

namespace {
constexpr const char* LEVEL_TAGS[] = {"INFO", "WARN", "ERR"};
}

void ensureDirectories(const std::vector<std::filesystem::path>& directories) {
    for (const auto& dir : directories) {
        std::error_code ec;
        if (!std::filesystem::exists(dir, ec)) {
            std::filesystem::create_directories(dir, ec);
        }
    }
}

std::string wideToUtf8(const std::wstring& value) {
    if (value.empty()) {
        return {};
    }
    int sizeNeeded = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string result(sizeNeeded, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), result.data(), sizeNeeded, nullptr, nullptr);
    return result;
}

std::wstring utf8ToWide(const std::string& value) {
    if (value.empty()) {
        return {};
    }
    int sizeNeeded = MultiByteToWideChar(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), nullptr, 0);
    std::wstring result(sizeNeeded, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), result.data(), sizeNeeded);
    return result;
}

std::string toLower(const std::string& value) {
    std::string result = value;
    std::transform(result.begin(), result.end(), result.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return result;
}

std::string timeString() {
    SYSTEMTIME st{};
    GetLocalTime(&st);
    std::ostringstream oss;
    oss << std::setfill('0') << std::setw(2) << st.wHour << ':' << std::setw(2) << st.wMinute << ':' << std::setw(2) << st.wSecond;
    return oss.str();
}

Logger& Logger::instance() {
    static Logger inst;
    return inst;
}

Logger::Logger() {
    m_logPath = std::filesystem::current_path() / "log.txt";
    appendToFile("==== Offline Mod Menu Log (OFFLINE USE ONLY) ====");
}

void Logger::log(Level level, const std::string& message) {
    const std::string line = '[' + timeString() + "] [" + LEVEL_TAGS[static_cast<int>(level)] + "] " + message + " | OFFLINE USE ONLY";

    std::lock_guard<std::mutex> lock(m_mutex);
    m_entries.push_back(line);
    appendToFile(line);

    if (m_callback) {
        m_callback(line);
    }
}

std::vector<std::string> Logger::fetchEntries() {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_entries;
}

void Logger::setRealtimeCallback(std::function<void(const std::string&)> callback) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_callback = std::move(callback);
}

void Logger::appendToFile(const std::string& line) {
    std::ofstream file(m_logPath, std::ios::app);
    if (file.is_open()) {
        file << line << '\n';
    }
}

} // namespace util
