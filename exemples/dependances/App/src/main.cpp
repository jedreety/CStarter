#include <fmt/format.h>
#include <spdlog/spdlog.h>

#include <string>

int main()
{
    const std::string fmt_version = fmt::format("{}.{}.{}", FMT_VERSION / 10000, FMT_VERSION / 100 % 100, FMT_VERSION % 100);
    spdlog::info("Bonjour depuis spdlog {}.{}.{}, avec fmt {}.", SPDLOG_VER_MAJOR, SPDLOG_VER_MINOR, SPDLOG_VER_PATCH, fmt_version);
    return 0;
}
