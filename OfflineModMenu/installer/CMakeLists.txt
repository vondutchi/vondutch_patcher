cmake_minimum_required(VERSION 3.20)
project(OfflineModMenuInstaller)

# This secondary CMake project demonstrates how the installer bundle could be generated.
# It reuses the main executable and packages supporting assets.

install(DIRECTORY ../resources DESTINATION .)
install(DIRECTORY ../configs DESTINATION .)
install(DIRECTORY ../mods DESTINATION . OPTIONAL)
install(PROGRAMS ../build/Release/OfflineModMenu.exe DESTINATION .)

