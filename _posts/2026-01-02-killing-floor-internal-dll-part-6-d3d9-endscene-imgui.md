---
layout: post
title: "Internal DLL Cheat Development for Killing Floor (Part 6) – Hooking DirectX9 EndScene with MinHook and Creating a UI with ImGUI"
description: "In this post we’ll hook DirectX9’s `EndScene` to render an ImGui overlay. By the end, you’ll have a working menu drawn every frame, with input handled via a Win32 `WndProc` hook.  
**Prereqs:** Visual Studio, DirectX9 headers/libs, MinHook, ImGui, and a **matching architecture** (x86 game → x86 DLL)."
date: 2026-1-2 10:38:22 -0700
categories: [game-hacking, hacking, cheats]
tags: [reverse-engineering, hacking, game-hacking]
image: /assets/images/kf_6.png
image_alt: "Killing Floor Cheats"
author: Drew Alleman
last_modified_at: 2026-1-2 10:38:22 -0700
---
# Introduction
In this post we’ll hook DirectX9’s `EndScene` to render an ImGui overlay. By the end, you’ll have a working menu drawn every frame, with input handled via a Win32 `WndProc` callback.  
**Prereqs:** Visual Studio, DirectX9 headers/libs, MinHook, ImGui, and a **matching architecture** (x86 game → x86 DLL).

Take a look at the following example that displays a texture to the screen. We will be hooking into the `EndScene` function at the end to render our own overlay each frame.
```c++
void RenderScene(IDirect3DDevice9* pDevice)
{
    // 1. Clear the back buffer to a solid color (Black)
    pDevice->Clear(0, NULL, D3DCLEAR_TARGET, D3DCOLOR_XRGB(0, 0, 0), 1.0f, 0);
    // 2. Notify the device that we are starting to draw
    if (SUCCEEDED(pDevice->BeginScene()))
    {
        // Set up sprite drawing (similar to your C# example)
        pSprite->Begin(D3DXSPRITE_ALPHABLEND);
        // This draws a texture to the screen at coordinates (10, 10)
        D3DXVECTOR3 pos = { 10.0f, 10.0f, 0.0f };
        pSprite->Draw(pTexture, NULL, NULL, &pos, 0xFFFFFFFF);
        pSprite->End();
        // ---------------------------------------------------------
        // This is the function we are hijacking! 
        // Our injected code will run right BEFORE this line finishes.
        // ---------------------------------------------------------
        pDevice->EndScene(); 
    }
    // 3. Swap the back buffer to the front (display it to the user)
    pDevice->Present(NULL, NULL, NULL, NULL);
}
```

# Dynamically Fetching the EndScene Address

In order to dynamically hook `EndScene` we will need to develop a reliable way to fetch the address of the function in memory. We can do this by creating a dummy `IDirect3DDevice9` device to then access the DirectX9 [vTable](https://en.wikipedia.org/wiki/Virtual_method_table) 

Virtual Table (vTable) Definition From [Wikipedia](https://en.wikipedia.org/wiki/Virtual_method_table):
*Whenever a [class](https://en.wikipedia.org/wiki/Class_\(programming\) "Class (programming)") defines a [virtual function](https://en.wikipedia.org/wiki/Virtual_function "Virtual function") (or [method](https://en.wikipedia.org/wiki/Method_\(computer_programming\) "Method (computer programming)")), most [compilers](https://en.wikipedia.org/wiki/Compiler "Compiler") add a hidden [member variable](https://en.wikipedia.org/wiki/Member_variable "Member variable") to the class that points to an array of [pointers](https://en.wikipedia.org/wiki/Pointer_\(computer_programming\) "Pointer (computer programming)") to (virtual) functions called the virtual method table.*

I found the following post on [UnknownCheats](https://www.unknowncheats.me/forum/direct3d/66594-d3d9-vtables.html) that mentioned that the `EndScene` function was located at the vTable index of 42. 

We will start this project by developing the code to create our dummy DirectX9 device. I added some private variables and 2 new functions to my `Cheat.h`:
```c++
#include <Windows.h>
#include <iostream>
#include <vector>
#include <d3d9.h>

// You will need to link d3d9.lib and d3dx9.lib in your project settings
#pragma comment(lib, "d3d9.lib")
class Cheats {
private:
    IDirect3DDevice9* pDummyDevice = nullptr; 
    IDirect3D9* pD3D = nullptr; 
    HWND window = NULL;  
    void* endSceneAddress = nullptr;  

public:
    bool FetchEndSceneAddress();  
    void ReleaseDevice(); 
};
```

The `FetchEndSceneAddress` function will create a DirectX9 Device and fetch the address of the End Scene function from the `vTable`.
```c++
bool Cheats::FetchEndSceneAddress() {
	// Create a blank overlapping window
    window = CreateWindowExA(0, "STATIC", "DummyWindow", WS_OVERLAPPEDWINDOW, 0, 0, 100, 100, NULL, NULL, NULL, NULL);
    if (!window) return false;
	
	// Create the IDirect3D9 object 
    pD3D = Direct3DCreate9(D3D_SDK_VERSION);
    if (!pD3D) { DestroyWindow(window); return false; }
	
	
	// Setup some arguments for the device that's going to be created
    D3DPRESENT_PARAMETERS d3dpp = {};
    d3dpp.Windowed = TRUE; // set the window as windowed rather than fullscreen
    d3dpp.SwapEffect = D3DSWAPEFFECT_DISCARD; // Discard the old rendered frames from memory after displaying them 
    d3dpp.hDeviceWindow = window; // What window to attach it to
	// Actually creates a device to represent the display adapter with the settings above
    HRESULT res = pD3D->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, window, D3DCREATE_SOFTWARE_VERTEXPROCESSING, &d3dpp, &pDummyDevice);
    if (FAILED(res) || !pDummyDevice) { ReleaseDevice(); return false; }
	
    void** vTable = *(void***)pDummyDevice;
    endSceneAddress = vTable[42]; // This is the index we found on UnknownCheats

	char buffer[128];
	sprintf_s(buffer, "Success! EndScene Address: 0x%p", endSceneAddress);
	MessageBoxA(NULL, buffer, "DirectX Hook Info", MB_OK);
	pDummyDevice->Release();
	pD3D->Release();
	DestroyWindow(window);
    return (endSceneAddress != nullptr);
}

```

Then when we inject our DLL we can see the address was successfully grabbed: 
![Pasted image 20260101232218](/assets/images/pasted-image-20260101232218.png) <br><br>
# Hooking the EndScene Function
With the code built to dynamically fetch the address of the `EndScene` function built we will now need to design the function that will actually serve as our hook. This is where we will actually render what we want to the screen. In the snippet below I added a section that renders a red rectangle to the screen.

`Cheats.cpp`:
```c++
typedef HRESULT(STDMETHODCALLTYPE* EndScene_t)(IDirect3DDevice9*);
EndScene_t oEndScene = nullptr; // Original EndScene Function 

HRESULT STDMETHODCALLTYPE hkEndScene(IDirect3DDevice9* pDevice) {
    // 1. Save the game's original settings
    IDirect3DStateBlock9* pStateBlock = nullptr;
    pDevice->CreateStateBlock(D3DSBT_ALL, &pStateBlock);
    pStateBlock->Capture();

    // --- YOUR DRAWING GOES HERE ---
    D3DRECT rect = { 100, 100, 200, 200 };
    pDevice->Clear(1, &rect, D3DCLEAR_TARGET, 0xFFFF0000, 0, 0);
	
	// Reapplies the game's original settings
    pStateBlock->Apply();
    pStateBlock->Release();
    return oEndScene(pDevice);
}
```

Once we have the `EndScene` pointer, [Minhook](https://github.com/TsudaKageyu/minhook) can redirect it to our function in a few lines. We just need to define the following function in our `Cheats.cpp`:
```c++
bool Cheats::CreateHook() {
    // 1.  Initialize MinHook
    if (MH_Initialize() != MH_OK) {
        std::cout << "[-] Failed to initialize MinHook" << std::endl;
        return false;
    }

    // 2. Find the address
    if (!FetchEndSceneAddress()) {
        std::cout << "[-] Failed to fetch EndScene address" << std::endl;
        return false;
    }

    // 3. Create the hook
    if (MH_CreateHook(endSceneAddress, &hkEndScene, reinterpret_cast<LPVOID*>(&oEndScene)) != MH_OK) {
        std::cout << "[-] Failed to create hook" << std::endl;
        return false;
    }

    // 4. Enable the hook
    if (MH_EnableHook(endSceneAddress) != MH_OK) {
        std::cout << "[-] Failed to enable hook" << std::endl;
        return false;
    }

    std::cout << "[+] Hook successfully applied!" << std::endl;
    return true;
}
```

We also need to add a function to unhook the `EndScene` function when we unload in `Cheats.cpp`: 
```c++
void Cheats::Cleanup() {

    MH_DisableHook(endSceneAddress);
    MH_RemoveHook(endSceneAddress);
    MH_Uninitialize();
}
```

Ensure you add `libMinHook.x86.lib` and `minhook.h` to your source!
![Pasted image 20260102013546](/assets/images/pasted-image-20260102013546.png)<br><br>

I then modified the `Start` function to create our `EndScene` hook with the function we just created. 
```c++

void Cheats::Start() {
    if (!CreateHook()) {
        std::cout << "[-] Failed to create hook" << std::endl;
    }
    while (!(GetAsyncKeyState(VK_END) & 1)) {
        if (!GetLocalPlayer()) {
            std::cout << "[!] Failed to get APawn waiting 5 seconds" << std::endl;
            Sleep(5000);
            continue;
        }

        if (myPawn->health <= 0) {
            std::cout << "[!] Player is dead; sleeping for 3 seconds" << std::endl;
            Sleep(3000);
            continue;
        }

        if (GetAsyncKeyState(VK_F1) & 1) {
            InstaKill();
        }

        if (GetAsyncKeyState(VK_F2) & 1) {
            ScaleAActorsUp();
        }

        if (GetAsyncKeyState(VK_F3) & 1) {
            ScaleAActorsDown();
        }

        Sleep(50);
    }
    Cleanup();
}
```

Now if we compile and inject our code we see a red box appear! 
![Pasted image 20260102001320](/assets/images/pasted-image-20260102001320.png)<br><br>

# Code Reformat for GUI Interface
We need to modify our code a little in order to reference our Cheat class in our hook. Instead of  the Cheats class being Instantiated  in the `MainThread` function like below:
```c++
DWORD WINAPI MainThread(LPVOID lpParam) {
    HMODULE hModule = (HMODULE)lpParam;
    CreateConsole();
    Cheats c = Cheats();
    if (!c.GetLocalPlayer()) {
        std::cout << "Failed to fetch current player!" << std::endl;
    }
    else {
        c.Start();
    }
    std::cout << "[*] Cleaning up and Detaching..." << std::endl;
    FreeConsole();
    FreeLibraryAndExitThread(hModule, 0);
    return 0;
}
```

We will shift our code to using a global instance of cheats, so it can be referenced in our hook. We will also be adding some Boolean values to serve as a toggle for our cheats. Note the extern line at the bottom! (Extern tells the compiler that the 'cheats' object exists, but it's actual 'home' is in another file,)<br>

`Cheats.h`:
```c++
#pragma once
#include <Windows.h>
#include <iostream>
#include <vector>
#include <d3d9.h>
#include "MinHook/MinHook.h" 
#include "imgui/imgui.h"
#include "imgui/imgui_impl_dx9.h"
#include "imgui/imgui_impl_win32.h"

#pragma comment(lib, "d3d9.lib")
#pragma comment(lib, "libMinHook.x86.lib") 

class AActor;
class APawn;
class ULevel;

class Cheats {

public:
    APawn* myPawn = nullptr;
    bool bMenuOpen = true; // NEW (toggle menu display)
    bool bInstaKill = false; // NEW (toggle setting the enemies health to 1)
    float fZedScaleValue = 1.0f; // NEW (scale modifier for ZED size)
    HWND gameWindow = NULL; // NEW 
    bool bCanUnload = false; // NEW (used to unload the cheats)
    bool bGodMode = true; // NEW (God mode toggle)
};

extern Cheats cheats; // NEW
```

Then at the bottom of `Cheats.cpp` we need to add the following line. This defines the one global `Cheats` instance that `extern Cheats cheats;` refers to across the project.”
```c++
Cheats cheats;
```

Now let's modify our `dllmain.cpp` to use our cheats instance in `cheats.cpp`. 
```c++
DWORD WINAPI MainThread(LPVOID lpParam) {
    HMODULE hModule = (HMODULE)lpParam;
    CreateConsole();
    if (!cheats.GetLocalPlayer()) {
        std::cout << "Failed to fetch current player!" << std::endl;
    }
    cheats.Start(); // NEW
    std::cout << "[*] Cleaning up and Detaching..." << std::endl;
    FreeConsole();
    FreeLibraryAndExitThread(hModule, 0);
    return 0;
}
```

Next, we will be starting to move away from using `GetAsyncKeyState` as it is not a very reliable and efficient way to detect user input we are essentially asking the computer over and over if X key is being pressed down. If we implement a `WndProc` callback we are instead notified when a 
user inputs a key. 

Returning `0` in `WndProc` tells Windows the message was handled, preventing the game’s original `WndProc` from also processing it.
```c++
WNDPROC oWndProc;
typedef HRESULT(STDMETHODCALLTYPE* EndScene_t)(IDirect3DDevice9*);
EndScene_t oEndScene = nullptr;

LRESULT __stdcall WndProc(const HWND hWnd, UINT uMsg, WPARAM wParam, LPARAM lParam) {
	
	// If the event was a keydown
    if (uMsg == WM_KEYDOWN) {
	    // If the key was F1 flip the value of bInstaKill
        if (wParam == VK_F1) { cheats.bInstaKill = !cheats.bInstaKill; return 0; }
        // If the key was F2 flip the value of bGodMode
        if (wParam == VK_F2) { cheats.bGodMode = !cheats.bGodMode; return 0; }
        // If the key was F3 call the function to scale the actors up
        if (wParam == VK_F3) { cheats.ScaleAActorsUp(); return 0; }
        // If the key was F4 call the function to scale the actors down
        if (wParam == VK_F4) { cheats.ScaleAActorsDown(); return 0; }
        
        if (wParam == VK_INSERT) {
            cheats.bMenuOpen = !cheats.bMenuOpen;
            return 0;
        }
    }
    return CallWindowProc(oWndProc, hWnd, uMsg, wParam, lParam); 
}

```

Now in our `Start` function if the corresponding Boolean is enabled we can apply the intended behavior.  For example as long as `bInstaKill` is True, it will call `InstaKill` every 100ms. 
```c++
void Cheats::Start() {
    if (!CreateHook()) return;

    while (!bCanUnload) {
        if (!GetLocalPlayer()) {
            std::cout << "[-] Failed to fetch local player object, sleeping for 5 seconds" << std::endl;
            Sleep(5000);
            continue;
        }
        else if (myPawn->health <= 0) {
            std::cout << "[-] Localplayer is dead sleeping for 3 seconds" << std::endl;
            Sleep(3000);
            continue;
        }

        if (bInstaKill) InstaKill();

        if (bGodMode) {
            myPawn->health = 100;
        }
        Sleep(25);
    }
    Sleep(100);
    Cleanup();
}

```

Now let's edit our `EndScene` hook function to actually set up our created `WndProc` callback to capture user input. We will be utilizing a static variable to ensure the callback is only setup once. 
```c++

HRESULT STDMETHODCALLTYPE hkEndScene(IDirect3DDevice9* pDevice) {
    // If we are currently unloading the DLL, skip drawing and just call the original function
    if (cheats.bCanUnload) return oEndScene(pDevice);

    // 'static' ensures this variable is initialized once and persists across every call to this function
    static bool init = false;
    if (!init) {

        // Retrieve the creation parameters to find the handle (HWND) of the game window
        D3DDEVICE_CREATION_PARAMETERS params;
        pDevice->GetCreationParameters(&params);

        // Store the game's focus window so we can hook its input and handle cleanup later
        cheats.gameWindow = params.hFocusWindow;

        // "Subclass" the window: redirect the game's input messages to our own WndProc function
        oWndProc = (WNDPROC)SetWindowLongPtr(cheats.gameWindow, GWLP_WNDPROC, (LONG_PTR)WndProc);

        init = true; // Ensure this set up block only runs once
    }
    
    // CAPTURE GAME STATE
    IDirect3DStateBlock9* pStateBlock = nullptr;
    if (pDevice->CreateStateBlock(D3DSBT_ALL, &pStateBlock) == D3D_OK) {
        pStateBlock->Capture();
    }
    
    // DRAW HERE
    
    // RESTORE GAME STATE & CLEANUP
    if (pStateBlock) {
        pStateBlock->Apply();
        pStateBlock->Release();
    }
    
    return oEndScene(pDevice); // Return the real EndScene function
}
```


# Creating a GUI with ImGui
Now let's use [ImGui](https://github.com/ocornut/ImGui/) to create a GUI for our cheat. We can render the gui in the `EndScene` hook we created earlier. And use the `WndProc` callback to capture user input to the GUI.

You will need to add the following items to your source:
![Pasted image 20260102012534](/assets/images/pasted-image-20260102012534.png)<br><br>
![Pasted image 20260102150448](/assets/images/pasted-image-20260102150448.png)<br><br>
![Pasted image 20260102150504](/assets/images/pasted-image-20260102150504.png)<br><br>

Then we need to add the imports to our `cheats.h`:
```c++
#include "imgui/imgui.h"
#include "imgui/imgui_impl_dx9.h"
#include "imgui/imgui_impl_win32.h"
```

Now in `cheats.cpp` let's create our menu:
```c++
void Cheats::DrawMenu() {
    if (!bMenuOpen) return; // if the menu is closed don't render anything
    ImGui::Begin("Killing Floor", &bMenuOpen, ImGuiWindowFlags_AlwaysAutoResize);
    ImGui::Text("Player Pointer: %p", myPawn);
    ImGui::Separator();
    ImGui::Text("InstaKill (F1): %s", bInstaKill ? "ON" : "OFF");
    ImGui::Text("GodMode (F2): %s", bGodMode ? "ON" : "OFF");
    ImGui::Text("F3: Double Size | F4: Half Size");
    ImGui::End();
}
```

Now we need to modify our hook to also setup some initialization code for `ImGui` with the DirectX9 device when it's called for the first time:

```c++
HRESULT STDMETHODCALLTYPE hkEndScene(IDirect3DDevice9* pDevice) {
    if (cheats.bCanUnload) return oEndScene(pDevice);

    static bool init = false;
    if (!init) {
        D3DDEVICE_CREATION_PARAMETERS params;
        pDevice->GetCreationParameters(&params);
        cheats.gameWindow = params.hFocusWindow;

        oWndProc = (WNDPROC)SetWindowLongPtr(cheats.gameWindow, GWLP_WNDPROC, (LONG_PTR)WndProc);

        ImGui::CreateContext();
        ImGui_ImplWin32_Init(cheats.gameWindow);
        ImGui_ImplDX9_Init(pDevice);

        init = true;
    }

    // 1. BACKUP GAME STATE
    // This prevents ImGui from messing up the game's textures/lighting
    IDirect3DStateBlock9* pStateBlock = nullptr;
    if (pDevice->CreateStateBlock(D3DSBT_ALL, &pStateBlock) == D3D_OK) {
        pStateBlock->Capture();
    }

    // 2. RENDER ImGui
    ImGui_ImplDX9_NewFrame();
    ImGui_ImplWin32_NewFrame();
    ImGui::NewFrame();

    cheats.DrawMenu();

    ImGui::EndFrame();
    ImGui::Render();
    ImGui_ImplDX9_RenderDrawData(ImGui::GetDrawData());

    // 3. RESTORE GAME STATE & CLEANUP
    if (pStateBlock) {
        pStateBlock->Apply();
        pStateBlock->Release();
    }

    return oEndScene(pDevice);
}

```

I added the following section to allow ImGui to consume any inputs if needed
```c++
LRESULT __stdcall WndProc(HWND hWnd, UINT uMsg, WPARAM wParam, LPARAM lParam)
{
	...
    // Menu is open: feed everything to ImGui first
    if (ImGui::GetCurrentContext())
        ImGui_ImplWin32_WndProcHandler(hWnd, uMsg, wParam, lParam);

    // Handle ImGui input
    ImGuiIO& io = ImGui::GetIO();
    if (io.WantCaptureMouse || io.WantCaptureKeyboard)
        return 0; // swallow input, don't send to game

    // Otherwise, let the game have it
    return CallWindowProc(oWndProc, hWnd, uMsg, wParam, lParam);
}
```

Then let's add some cleanup functions for ImGui to the `Cleanup` function:
```c++
void Cheats::Cleanup() {

    MH_DisableHook(endSceneAddress);
    MH_RemoveHook(endSceneAddress);
    MH_Uninitialize();

    ImGui_ImplDX9_Shutdown(); // NEW
    ImGui_ImplWin32_Shutdown(); // NEW
    if (ImGui::GetCurrentContext()) ImGui::DestroyContext(); // NEW
    if (oWndProc && gameWindow) {
        SetWindowLongPtr(gameWindow, GWLP_WNDPROC, (LONG_PTR)oWndProc);
    }
}
```

I also adding the following block to the `WndProc` callback to draw an ImGui cursor when the menu is shown:
```c++
	case VK_INSERT:
		cheats.bMenuOpen = !cheats.bMenuOpen;
		if (ImGui::GetCurrentContext())
			`// When true, ImGui renders its own mouse cursor`
			ImGui::GetIO().MouseDrawCursor = cheats.bMenuOpen;
		return 0;
```


Now when I compiled and ran my code I was able to see my menu in-game! In the next blog post I will be finding the players view matrix in order to create ZED ESP. 

![pMenu](/assets/images/pmenu.gif)<br><br>

# Full Code
https://github.com/Drew-Alleman/InternalKF
Full `Cheats.cpp`:
```c++
#include "pch.h"
#include "Cheats.h"
#include "ULevel.h"
#include "AActor.h" 
#include "APawn.h"
#include "Enums.h"

extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);

WNDPROC oWndProc;
typedef HRESULT(STDMETHODCALLTYPE* EndScene_t)(IDirect3DDevice9*);
EndScene_t oEndScene = nullptr;

LRESULT __stdcall WndProc(HWND hWnd, UINT uMsg, WPARAM wParam, LPARAM lParam)
{
    // --- Always allow your global hotkeys (even when menu is closed) ---
    if (uMsg == WM_KEYDOWN)
    {
        switch (wParam)
        {
        case VK_F1: cheats.bInstaKill = !cheats.bInstaKill; return 0;
        case VK_F2: cheats.bGodMode = !cheats.bGodMode;   return 0;
        case VK_F3: cheats.ScaleAActorsUp();               return 0;
        case VK_F4: cheats.ScaleAActorsDown();             return 0;

        case VK_INSERT:
            cheats.bMenuOpen = !cheats.bMenuOpen;
            if (ImGui::GetCurrentContext())
                // When true, ImGui renders its own mouse cursor
                ImGui::GetIO().MouseDrawCursor = cheats.bMenuOpen;
            return 0;

        case VK_END:
            cheats.bCanUnload = true;
            return 0;
        }
    }

    // If menu is closed, do NOT feed ImGui. Just pass to the game.
    if (!cheats.bMenuOpen)
        return CallWindowProc(oWndProc, hWnd, uMsg, wParam, lParam);

    // Menu is open: feed everything to ImGui first
    if (ImGui::GetCurrentContext())
        ImGui_ImplWin32_WndProcHandler(hWnd, uMsg, wParam, lParam);

    // Handle ImGui input
    ImGuiIO& io = ImGui::GetIO();
    if (io.WantCaptureMouse || io.WantCaptureKeyboard)
        return 0; // swallow input, don't send to game

    // Otherwise, let the game have it
    return CallWindowProc(oWndProc, hWnd, uMsg, wParam, lParam);
}
HRESULT STDMETHODCALLTYPE hkEndScene(IDirect3DDevice9* pDevice) {
    if (cheats.bCanUnload) return oEndScene(pDevice);

    static bool init = false;
    if (!init) {
        D3DDEVICE_CREATION_PARAMETERS params;
        pDevice->GetCreationParameters(&params);
        cheats.gameWindow = params.hFocusWindow;

        oWndProc = (WNDPROC)SetWindowLongPtr(cheats.gameWindow, GWLP_WNDPROC, (LONG_PTR)WndProc);

        ImGui::CreateContext();
        ImGui_ImplWin32_Init(cheats.gameWindow);
        ImGui_ImplDX9_Init(pDevice);

        init = true;
    }

    // 1. BACKUP GAME STATE
    // This prevents ImGui from messing up the game's textures/lighting
    IDirect3DStateBlock9* pStateBlock = nullptr;
    if (pDevice->CreateStateBlock(D3DSBT_ALL, &pStateBlock) == D3D_OK) {
        pStateBlock->Capture();
    }

    // 2. RENDER IMGUI
    ImGui_ImplDX9_NewFrame();
    ImGui_ImplWin32_NewFrame();
    ImGui::NewFrame();

    cheats.DrawMenu();

    ImGui::EndFrame();
    ImGui::Render();
    ImGui_ImplDX9_RenderDrawData(ImGui::GetDrawData());

    // 3. RESTORE GAME STATE & CLEANUP
    if (pStateBlock) {
        pStateBlock->Apply();
        pStateBlock->Release();
    }

    return oEndScene(pDevice);
}

bool Cheats::GetModules() {
    engineModule = (uintptr_t)GetModuleHandleA("Engine.dll");
    return engineModule != NULL;
}

bool Cheats::GetLocalPlayer() {
    if (!engineModule && !GetModules()) return false;

    static uintptr_t GEngineAddr = engineModule + 0x004C6934;
    uintptr_t GEngine = *(uintptr_t*)GEngineAddr;
    if (!GEngine) return false;

    uintptr_t pawnAddr = *(uintptr_t*)(GEngine + 0x38);
    if (!pawnAddr) return false;

    this->myPawn = (APawn*)pawnAddr;
    return (myPawn != nullptr);
}

std::vector<APawn*> Cheats::GetMovingPawns() {
    std::vector<APawn*> pawns;

    if (!myPawn || !myPawn->Level)
        return pawns;

    ULevel* level = myPawn->Level;

    // sanity clamp (prevents insane loops if currentEntities is wrong/stale)
    if (level->currentEntities <= 0 || level->currentEntities > 50000)
        return pawns;

    for (int i = 0; i < level->currentEntities; i++) {
        AActor* a = level->EntityList[i];
        if (!a || a == (AActor*)myPawn)
            continue;

        // If this field read is sometimes unsafe, you may need more pointer validation.
        if (a->physics != PHYS::Walking && a->physics != PHYS::Falling)
            continue;

        // Treat it as a pawn ONLY after your filters
        APawn* p = (APawn*)a;

        // Extra sanity on health reads
        if (p->health <= 0 || p->health > 10000)
            continue;

        pawns.push_back(p);
    }
    return pawns;
}

void Cheats::ScaleAActorsUp() {
    for (APawn* pawn : GetMovingPawns()) {
        if (!pawn) continue;
        pawn->x3DDrawScale *= 2.0f;
        pawn->y3DDrawScale *= 2.0f;
        pawn->z3DDrawScale *= 2.0f;
        pawn->drawSize *= 2.0f;
    }
}

void Cheats::ScaleAActorsDown() {
    for (APawn* pawn : GetMovingPawns()) {
        if (!pawn) continue;
        pawn->x3DDrawScale /= 2.0f;
        pawn->y3DDrawScale /= 2.0f;
        pawn->z3DDrawScale /= 2.0f;
        pawn->drawSize /= 2.0f;
        if (pawn->drawSize < 0.1f) pawn->drawSize = 0.1f;
    }
}

void Cheats::InstaKill() {
    for (APawn* pawn : GetMovingPawns()) {
        if (!pawn) continue;
        if (pawn->health > 5) pawn->health = 5;
    }
}

void Cheats::DrawMenu() {
    if (!bMenuOpen) return;
    ImGui::Begin("Killing Floor", &bMenuOpen, ImGuiWindowFlags_AlwaysAutoResize);
    ImGui::Text("Player Pointer: %p", myPawn);
    ImGui::Separator();
    ImGui::Text("InstaKill (F1): %s", bInstaKill ? "ON" : "OFF");
    ImGui::Text("GodMode (F2): %s", bGodMode ? "ON" : "OFF");
    ImGui::Text("F3: Double Size | F4: Half Size");
    ImGui::End();
}

void Cheats::Cleanup() {

    MH_DisableHook(endSceneAddress);
    MH_RemoveHook(endSceneAddress);
    MH_Uninitialize();

    ImGui_ImplDX9_Shutdown();
    ImGui_ImplWin32_Shutdown();
    if (ImGui::GetCurrentContext()) ImGui::DestroyContext();
    if (oWndProc && gameWindow) {
        SetWindowLongPtr(gameWindow, GWLP_WNDPROC, (LONG_PTR)oWndProc);
    }
}

void Cheats::Start() {
    if (!CreateHook()) return;

    while (!bCanUnload) {
        if (!GetLocalPlayer()) {
            std::cout << "[-] Failed to fetch local player object, sleeping for 5 seconds" << std::endl;
            Sleep(5000);
            continue;
        }
        else if (myPawn->health <= 0) {
            std::cout << "[-] Localplayer is dead sleeping for 3 seconds" << std::endl;
            Sleep(3000);
            continue;
        }

        if (bInstaKill) InstaKill();

        if (bGodMode) {
            myPawn->health = 100;
        }
        Sleep(25);
    }
    Sleep(100);
    Cleanup();
}

void Cheats::ReleaseDevice() {
    if (pDummyDevice) { pDummyDevice->Release(); pDummyDevice = nullptr; }
    if (pD3D) { pD3D->Release(); pD3D = nullptr; }
    if (window) { DestroyWindow(window); window = nullptr; }
}

bool Cheats::CreateHook() {
    // 1.  Initialize MinHook
    if (MH_Initialize() != MH_OK) {
        std::cout << "[-] Failed to initialize MinHook" << std::endl;
        return false;
    }

    // 2. Find the address
    if (!FetchEndSceneAddress()) {
        std::cout << "[-] Failed to fetch EndScene address" << std::endl;
        return false;
    }

    // 3. Create the hook
    if (MH_CreateHook(endSceneAddress, &hkEndScene, reinterpret_cast<LPVOID*>(&oEndScene)) != MH_OK) {
        std::cout << "[-] Failed to create hook" << std::endl;
        return false;
    }

    // 4. Enable the hook
    if (MH_EnableHook(endSceneAddress) != MH_OK) {
        std::cout << "[-] Failed to enable hook" << std::endl;
        return false;
    }

    std::cout << "[+] Hook successfully applied!" << std::endl;
    return true;
}

bool Cheats::FetchEndSceneAddress() {
    window = CreateWindowExA(0, "STATIC", "DummyWindow", WS_OVERLAPPEDWINDOW, 0, 0, 100, 100, NULL, NULL, NULL, NULL);
    if (!window) return false;

    pD3D = Direct3DCreate9(D3D_SDK_VERSION);
    if (!pD3D) { DestroyWindow(window); return false; }

    D3DPRESENT_PARAMETERS d3dpp = {};
    d3dpp.Windowed = TRUE;
    d3dpp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    d3dpp.hDeviceWindow = window;

    HRESULT res = pD3D->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, window, D3DCREATE_SOFTWARE_VERTEXPROCESSING, &d3dpp, &pDummyDevice);
    if (FAILED(res) || !pDummyDevice) { ReleaseDevice(); return false; }

    void** vTable = *(void***)pDummyDevice;
    endSceneAddress = vTable[42];

    ReleaseDevice();
    return (endSceneAddress != nullptr);
}

Cheats cheats;
```

Full `Cheats.h`:
```c++
#pragma once
#include <Windows.h>
#include <iostream>
#include <vector>
#include <d3d9.h>
#include "MinHook/MinHook.h" 
#include "imgui/imgui.h"
#include "imgui/imgui_impl_dx9.h"
#include "imgui/imgui_impl_win32.h"

#pragma comment(lib, "d3d9.lib")
#pragma comment(lib, "libMinHook.x86.lib") 

class AActor;
class APawn;
class ULevel;

class Cheats {
private:
    uintptr_t engineModule = 0;
    IDirect3DDevice9* pDummyDevice = nullptr;
    IDirect3D9* pD3D = nullptr;
    HWND window = NULL;
    void* endSceneAddress = nullptr;

public:
    APawn* myPawn = nullptr;
    bool bMenuOpen = true;
    bool bInstaKill = false;
    float fZedScaleValue = 1.0f;
    HWND gameWindow = NULL;
    bool bCanUnload = false;
    bool bGodMode = true;

    void DrawMenu();
    bool FetchEndSceneAddress();
    bool CreateHook();
    void ReleaseDevice();
    std::vector<APawn*> GetMovingPawns();
    void InstaKill();
    bool GetModules();
    bool GetLocalPlayer();
    void Start();
    void Cleanup();
    void ScaleAActorsUp();
    void ScaleAActorsDown();
};

extern Cheats cheats;
```

Full `dllmain.cpp`:
```c++
// dllmain.cpp : Defines the entry point for the DLL application.
#include "pch.h"
#include "Cheats.h"
#include <windows.h>
#include <iostream>


void CreateConsole() {
    AllocConsole();
    FILE* f;
    freopen_s(&f, "CONOUT$", "w", stdout);
    freopen_s(&f, "CONOUT$", "w", stderr);
    freopen_s(&f, "CONIN$", "r", stdin);
    std::cout.clear();
    std::cout << "[+] Console Allocated Successfully!" << std::endl;
}

DWORD WINAPI MainThread(LPVOID lpParam) {
    HMODULE hModule = (HMODULE)lpParam;
    CreateConsole();

    if (!cheats.GetLocalPlayer()) {
        std::cout << "Failed to fetch current player!" << std::endl;
    }

    cheats.Start();

    std::cout << "[*] Cleaning up and Detaching..." << std::endl;
    FreeConsole();
    FreeLibraryAndExitThread(hModule, 0);
    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {

    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        CreateThread(nullptr, 0, MainThread, hModule, 0, nullptr);
        return TRUE;
    }
    return FALSE;
}

```
