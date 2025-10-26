#include <windows.h>
#include <d3d11.h>
#include <tchar.h>

#include "gui.hpp"
#include "process.hpp"
#include "memory.hpp"
#include "config.hpp"
#include "utils.hpp"
#include "mods/mod_manager.hpp"

#include <imgui.h>
#include <backends/imgui_impl_win32.h>
#include <backends/imgui_impl_dx11.h>

#include <wrl/client.h>
#include <filesystem>

// DirectX objects
static Microsoft::WRL::ComPtr<ID3D11Device>           g_pd3dDevice = nullptr;
static Microsoft::WRL::ComPtr<ID3D11DeviceContext>    g_pd3dDeviceContext = nullptr;
static Microsoft::WRL::ComPtr<IDXGISwapChain>         g_pSwapChain = nullptr;
static Microsoft::WRL::ComPtr<ID3D11RenderTargetView> g_mainRenderTargetView = nullptr;
static WNDCLASSEX                                     g_wcex = {};
static HWND                                           g_hwnd = nullptr;

LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);

bool CreateDeviceD3D(HWND hWnd);
void CleanupDeviceD3D();
void CreateRenderTarget();
void CleanupRenderTarget();

int APIENTRY WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int) {
    util::ensureDirectories({
        std::filesystem::current_path() / "configs",
        std::filesystem::current_path() / "mods",
        std::filesystem::current_path() / "resources"
    });

    util::Logger::instance().log(util::Logger::Level::Info, "Offline Mod Menu starting up");

    g_wcex = { sizeof(WNDCLASSEX), CS_CLASSDC, WndProc, 0L, 0L,
               GetModuleHandle(nullptr), nullptr, nullptr, nullptr, nullptr,
               _T("OfflineModMenu"), nullptr };
    RegisterClassEx(&g_wcex);
    g_hwnd = CreateWindow(g_wcex.lpszClassName, _T("Offline Mod Menu — VonDutch Edition"),
                          WS_OVERLAPPEDWINDOW, 100, 100, 1280, 800, nullptr, nullptr, g_wcex.hInstance, nullptr);

    if (!CreateDeviceD3D(g_hwnd)) {
        CleanupDeviceD3D();
        UnregisterClass(g_wcex.lpszClassName, g_wcex.hInstance);
        return 1;
    }

    ShowWindow(g_hwnd, SW_SHOWDEFAULT);
    UpdateWindow(g_hwnd);

    GUIManager gui;
    ProcessManager processManager;
    MemoryScanner memoryScanner;
    ConfigManager configManager;
    ModManager modManager;
    modManager.discoverMods();

    gui.initialize(g_hwnd, g_pd3dDevice.Get(), g_pd3dDeviceContext.Get());

    MSG msg = {};
    bool done = false;
    while (!done) {
        while (PeekMessage(&msg, nullptr, 0U, 0U, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessage(&msg);
            if (msg.message == WM_QUIT) {
                done = true;
            }
        }

        if (done || gui.shouldClose()) {
            break;
        }

        if (processManager.isAttached()) {
            memoryScanner.setProcess(processManager.handle());
        }

        const float clearColorWithAlpha[4] = { 0.05f, 0.05f, 0.07f, 1.0f };
        g_pd3dDeviceContext->OMSetRenderTargets(1, g_mainRenderTargetView.GetAddressOf(), nullptr);
        g_pd3dDeviceContext->ClearRenderTargetView(g_mainRenderTargetView.Get(), clearColorWithAlpha);

        gui.render(processManager, memoryScanner, configManager, modManager);

        g_pSwapChain->Present(1, 0);
    }

    gui.shutdown();
    CleanupDeviceD3D();
    DestroyWindow(g_hwnd);
    UnregisterClass(g_wcex.lpszClassName, g_wcex.hInstance);
    util::Logger::instance().log(util::Logger::Level::Info, "Offline Mod Menu shutting down");

    return 0;
}

bool CreateDeviceD3D(HWND hWnd) {
    DXGI_SWAP_CHAIN_DESC sd = {};
    sd.BufferCount = 2;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferDesc.RefreshRate.Numerator = 60;
    sd.BufferDesc.RefreshRate.Denominator = 1;
    sd.Flags = DXGI_SWAP_CHAIN_FLAG_ALLOW_MODE_SWITCH;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow = hWnd;
    sd.SampleDesc.Count = 1;
    sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    UINT createDeviceFlags = 0;
#ifdef _DEBUG
    createDeviceFlags |= D3D11_CREATE_DEVICE_DEBUG;
#endif
    const D3D_FEATURE_LEVEL featureLevelArray[2] = { D3D_FEATURE_LEVEL_11_0, D3D_FEATURE_LEVEL_10_0 };
    D3D_FEATURE_LEVEL featureLevel;
    HRESULT result = D3D11CreateDeviceAndSwapChain(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, createDeviceFlags,
                                                   featureLevelArray, 2, D3D11_SDK_VERSION, &sd, g_pSwapChain.GetAddressOf(),
                                                   g_pd3dDevice.GetAddressOf(), &featureLevel, g_pd3dDeviceContext.GetAddressOf());

    if (result == DXGI_ERROR_UNSUPPORTED) {
        result = D3D11CreateDeviceAndSwapChain(nullptr, D3D_DRIVER_TYPE_WARP, nullptr, createDeviceFlags,
                                               featureLevelArray, 2, D3D11_SDK_VERSION, &sd, g_pSwapChain.GetAddressOf(),
                                               g_pd3dDevice.GetAddressOf(), &featureLevel, g_pd3dDeviceContext.GetAddressOf());
    }

    if (FAILED(result)) {
        return false;
    }

    CreateRenderTarget();
    return true;
}

void CleanupDeviceD3D() {
    CleanupRenderTarget();
    if (g_pSwapChain) { g_pSwapChain.Reset(); }
    if (g_pd3dDeviceContext) { g_pd3dDeviceContext.Reset(); }
    if (g_pd3dDevice) { g_pd3dDevice.Reset(); }
}

void CreateRenderTarget() {
    Microsoft::WRL::ComPtr<ID3D11Texture2D> pBackBuffer;
    g_pSwapChain->GetBuffer(0, IID_PPV_ARGS(&pBackBuffer));
    g_pd3dDevice->CreateRenderTargetView(pBackBuffer.Get(), nullptr, g_mainRenderTargetView.GetAddressOf());
}

void CleanupRenderTarget() {
    if (g_mainRenderTargetView) { g_mainRenderTargetView.Reset(); }
}

LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    if (ImGui_ImplWin32_WndProcHandler(hWnd, msg, wParam, lParam)) {
        return true;
    }

    switch (msg) {
    case WM_SIZE:
        if (wParam != SIZE_MINIMIZED && g_pSwapChain) {
            CleanupRenderTarget();
            g_pSwapChain->ResizeBuffers(0, LOWORD(lParam), HIWORD(lParam), DXGI_FORMAT_UNKNOWN, 0);
            CreateRenderTarget();
        }
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    default:
        break;
    }
    return DefWindowProc(hWnd, msg, wParam, lParam);
}

