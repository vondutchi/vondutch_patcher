#pragma once

#include <string>
#include <vector>
#include <mutex>
#include <filesystem>
#include <functional>

namespace util {

//! Simple RAII helper for ensuring required directories exist on launch.
void ensureDirectories(const std::vector<std::filesystem::path>& directories);

//! Converts a wide string to UTF-8.
std::string wideToUtf8(const std::wstring& value);

//! Converts a UTF-8 string to wide.
std::wstring utf8ToWide(const std::string& value);

//! Converts a string to lowercase for safe comparisons.
std::string toLower(const std::string& value);

//! Returns the current time formatted as HH:MM:SS.
std::string timeString();

//! Thread-safe logger implementation used by the entire application.
class Logger {
public:
    enum class Level {
        Info,
        Warning,
        Error
    };

    //! Returns the global logger instance.
    static Logger& instance();

    //! Appends a log entry to the log file and GUI buffer.
    void log(Level level, const std::string& message);

    //! Retrieves a copy of the internal log buffer.
    std::vector<std::string> fetchEntries();

    //! Allows the GUI to register a callback to receive real-time log entries.
    void setRealtimeCallback(std::function<void(const std::string&)> callback);

private:
    Logger();
    void appendToFile(const std::string& line);

    std::mutex m_mutex;
    std::vector<std::string> m_entries;
    std::function<void(const std::string&)> m_callback;
    std::filesystem::path m_logPath;
};

} // namespace util
