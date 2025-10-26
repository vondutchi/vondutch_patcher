@echo off
setlocal ENABLEDELAYEDEXPANSION
if "%VCPKG_ROOT%"=="" (
    echo VCPKG_ROOT environment variable is not set. Please install vcpkg and set VCPKG_ROOT.
    pause
    exit /b 1
)

if not exist build mkdir build
cd build
cmake .. -DCMAKE_TOOLCHAIN_FILE=%VCPKG_ROOT%\scripts\buildsystems\vcpkg.cmake -A x64
if errorlevel 1 goto :end
cmake --build . --config Release
:end
pause
