cmake_minimum_required(VERSION 3.20)
project(OfflineModMenu LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(imgui CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(d3d11 REQUIRED)

file(GLOB_RECURSE OFFLINE_MOD_MENU_SOURCES
    CONFIGURE_DEPENDS
    src/*.cpp
)

add_executable(OfflineModMenu ${OFFLINE_MOD_MENU_SOURCES})

set(GENERATED_RESOURCE_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated_resources)
set(ICON_B64_SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/resources/icon.ico.b64)
set(GENERATED_ICON ${GENERATED_RESOURCE_DIR}/icon.ico)
set(ICON_OUTPUT ${GENERATED_ICON})
file(READ ${ICON_B64_SOURCE} ICON_B64_CONTENT)
string(REGEX REPLACE "[\r\n]" "" ICON_BASE64 "${ICON_B64_CONTENT}")
file(TO_NATIVE_PATH ${ICON_OUTPUT} ICON_OUTPUT_NATIVE)
string(REPLACE "\\" "\\\\" ICON_PATH "${ICON_OUTPUT_NATIVE}")

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/resources/generate_icon.ps1.in
               ${GENERATED_RESOURCE_DIR}/generate_icon.ps1 @ONLY)
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/resources/offlinemodmenu.rc.in
               ${GENERATED_RESOURCE_DIR}/offlinemodmenu.rc @ONLY)

add_custom_command(
    OUTPUT ${GENERATED_ICON}
    COMMAND ${CMAKE_COMMAND} -E make_directory ${GENERATED_RESOURCE_DIR}
    COMMAND powershell -NoProfile -ExecutionPolicy Bypass -File "${GENERATED_RESOURCE_DIR}/generate_icon.ps1"
    DEPENDS ${GENERATED_RESOURCE_DIR}/generate_icon.ps1 ${ICON_B64_SOURCE}
    COMMENT "Generating application icon from embedded base64"
    BYPRODUCTS ${GENERATED_ICON}
    VERBATIM
)

add_custom_target(OfflineModMenuIcon ALL DEPENDS ${GENERATED_ICON})
add_dependencies(OfflineModMenu OfflineModMenuIcon)

target_sources(OfflineModMenu PRIVATE ${GENERATED_RESOURCE_DIR}/offlinemodmenu.rc)

target_include_directories(OfflineModMenu PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(OfflineModMenu PRIVATE
    imgui::imgui
    nlohmann_json::nlohmann_json
    d3d11
    dxgi
    dxguid
)

target_compile_definitions(OfflineModMenu PRIVATE UNICODE _UNICODE)

if (MSVC)
    target_compile_options(OfflineModMenu PRIVATE /W4 /permissive- /MP)
else()
    target_compile_options(OfflineModMenu PRIVATE -Wall -Wextra -Wpedantic)
endif()

install(TARGETS OfflineModMenu RUNTIME DESTINATION bin)
install(DIRECTORY resources DESTINATION .
        PATTERN "icon.ico.b64" EXCLUDE
        PATTERN "*.in" EXCLUDE)
install(FILES ${GENERATED_ICON} DESTINATION resources RENAME icon.ico)
install(DIRECTORY configs DESTINATION .)
install(DIRECTORY mods DESTINATION . OPTIONAL)

