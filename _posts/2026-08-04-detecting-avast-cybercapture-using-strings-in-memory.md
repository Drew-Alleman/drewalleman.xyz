---
layout: post
title: Detecting Avast CyberCapture Using Strings In Memory
date: 2026-08-04T10:00:00-07:00
image: /assets/images/Pasted image 20260802102319.png
categories:
  - red-teaming
  - malware-development
tags:
  - av-evasion
author: Drew Alleman
last_modified_at: 2026-08-01T13:00:00-07:00
---
## Introduction
In this post I show a simple method to detect Avast’s CyberCapture sandbox. We begin by examining the exports of `snxhk.dll`, the DLL Avast uses to install its user-mode hooks.

## Dumping the Hooking Functions
Loading snxhk.dll into Ghidra shows three exports: `entry`, `SnxHk_InstallHook`, and `SnxHk_UninstallHookEx`.

![Showcase](/assets/images/Pasted%20image%2020260804170007.png)


## Dumping Strings from our Process in Memory
I launched an unknown application, causing CyberCapture to activate. I extracted the strings from the process that had the  `snxhk.dll` loaded.
![Showcase](/assets/images/dump_strings%201.gif)

Using the strings utility we can see both the `SnxHk_InstallHook` and `SnxHk_UninstallHook` string in our process memory. 
```
$ strings enum_sandbox.exe.dmp -n 10 | grep InstallHook
SnxHk_InstallHook
```

```
$ strings enum_sandbox.exe.dmp -n 10 | grep UninstallHook
SnxHk_UninstallHook
```

## Searching for Avast Artifacts in our Current Process
Next, I created a C++ script to search the current process memory for `SnxHk_InstallHook`. While the target string appeared in both sandboxed and non-sandboxed executions, this is because the string literal was stored inside the executable, which accounts for the first result shown below:
![Showcase](/assets/images/Pasted%20image%2020260804172432.png)

A demo showcasing the code being executed in a process inside and outside the sandbox:
![Showcase](/assets/images/first_strings_dump_test.gif)

I then performed additional testing to identify unique properties of the `SnxHk_InstallHook` string references when running inside a sandboxed process. After multiple executions, the most reliable signal proved to be the presence of the string in a `MEM_MAPPED` + read-only region. This artifact does not appear when the process is executed outside the sandbox. A detection can therefore be built by scanning the process for mapped, readable regions that contain the string, while constructing the search pattern at runtime so that the detector’s own binary never contributes a false hit.

A screenshot showcasing the static string being found:
![Showcase](/assets/images/Pasted%20image%2020260804185558.png)

A screenshot showcasing the artifact not being detected:
![Showcase](/assets/images/Pasted%20image%2020260804185712.png)
## Code Explanation
We begin by importing the necessary libraries and defining a small helper that builds the search string at runtime. Constructing the string dynamically prevents our own binary from containing a contiguous copy of `SnxHk_InstallHook`, which would otherwise produce a false positive during the scan.
```C++
// detect-cybercapture-stealth.cpp
// Build: cl /EHsc /O2 /std:c++17 detect-cybercapture-stealth.cpp /link psapi.lib
// Exit code: 1 = CyberCapture present, 0 = clean

#include <cstring>
#include <Windows.h>
#include <Psapi.h>

#pragma comment(lib, "psapi.lib")

static void BuildInstall(char* o)
{
    o[0] = 'S'; o[1] = 'n'; o[2] = 'x'; o[3] = 'H';
    o[4] = 'k'; o[5] = '_'; o[6] = 'I'; o[7] = 'n';
    o[8] = 's'; o[9] = 't'; o[10] = 'a'; o[11] = 'l';
    o[12] = 'l'; o[13] = 'H'; o[14] = 'o'; o[15] = 'o';
    o[16] = 'k'; o[17] = 0;
}
```

Next we define a filter that decides whether a given address belongs to a region worth considering. In our testing the only reliable hits inside CyberCapture lived in `MEM_MAPPED` or `MEM_IMAGE` regions that were readable. All other region types are rejected.

```C++
static bool IsGoodRegion(uintptr_t addr)
{
    MEMORY_BASIC_INFORMATION mbi{};
    if (!VirtualQuery((LPCVOID)addr, &mbi, sizeof(mbi)))
        return false;

    // Only the region types observed in CyberCapture
    if (!(mbi.Type & (MEM_MAPPED | MEM_IMAGE)))
        return false;

    if (mbi.State != MEM_COMMIT)
        return false;
    if (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS))
        return false;

    const DWORD readable = PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY |
        PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
    return (mbi.Protect & readable) != 0;
}
```

The core of the detector is ScanForCyberCapture. It walks the entire address space of the current process looking for the string while carefully excluding any matches that come from our own code.
- GetSystemInfo is used to obtain the usable address range.
- VirtualQuery iterates over every memory region.
- Regions that belong to our own executable image are skipped.
- The live stack buffer that holds the runtime-constructed needle is also skipped.
- Only committed, readable regions are examined.
- As soon as a match is found inside a region that passes IsGoodRegion, the function returns true immediately (early exit).

```C++

static bool ScanForCyberCapture(uintptr_t selfBase, size_t selfSize,
    uintptr_t exclStart, uintptr_t exclEnd,
    const char* needle, size_t len)
{
    SYSTEM_INFO si;
    GetSystemInfo(&si);

    unsigned char* addr = static_cast<unsigned char*>(si.lpMinimumApplicationAddress);
    unsigned char* max = static_cast<unsigned char*>(si.lpMaximumApplicationAddress);
    MEMORY_BASIC_INFORMATION mbi;

    while (addr < max && VirtualQuery(addr, &mbi, sizeof(mbi)) == sizeof(mbi))
    {
        // Skip our own image
        uintptr_t base = reinterpret_cast<uintptr_t>(mbi.BaseAddress);
        uintptr_t end = base + mbi.RegionSize;
        if (base < selfBase + selfSize && end > selfBase)
        {
            addr = reinterpret_cast<unsigned char*>(end);
            continue;
        }

        if ((mbi.State == MEM_COMMIT) &&
            (mbi.Type & (MEM_MAPPED | MEM_IMAGE | MEM_PRIVATE)) &&
            !(mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)) &&
            (mbi.Protect != PAGE_EXECUTE))
        {
            const unsigned char* p = static_cast<const unsigned char*>(mbi.BaseAddress);
            const unsigned char* pend = p + mbi.RegionSize;

            __try
            {
                while (p + len <= pend)
                {
                    if (*p == needle[0])
                    {
                        uintptr_t hit = reinterpret_cast<uintptr_t>(p);

                        // Skip live needle buffer
                        if (hit >= exclStart && hit < exclEnd)
                        {
                            ++p;
                            continue;
                        }

                        if (memcmp(p, needle, len) == 0 && IsGoodRegion(hit))
                            return true;   // early exit
                    }
                    ++p;
                }
            }
            __except (EXCEPTION_EXECUTE_HANDLER) {}
        }

        unsigned char* next = static_cast<unsigned char*>(mbi.BaseAddress) + mbi.RegionSize;
        if (next <= addr) break;
        addr = next;
    }
    return false;
}
```

Finally we wire everything together in main. The needle is built at runtime, the ranges that must be ignored are calculated, and the result is reported with a simple message box.
```C++
int main()
{
    char needle[24]{};
    BuildInstall(needle);

    // Live buffer to ignore
    uintptr_t exclStart = reinterpret_cast<uintptr_t>(needle);
    uintptr_t exclEnd = exclStart + sizeof(needle);

    // Own image
    HMODULE hSelf = GetModuleHandleW(nullptr);
    MODULEINFO mi{};
    GetModuleInformation(GetCurrentProcess(), hSelf, &mi, sizeof(mi));

    bool detected = ScanForCyberCapture(
        reinterpret_cast<uintptr_t>(mi.lpBaseOfDll), mi.SizeOfImage,
        exclStart, exclEnd,
        needle, 17);

    if (detected)
    {
        MessageBoxA(nullptr,
            "CyberCapture detected\n(SnxHk_InstallHook in MAPPED/IMAGE region)",
            "Detection", MB_OK | MB_ICONWARNING);
    }
    else
    {
        MessageBoxA(nullptr,
            "No CyberCapture indicators found",
            "Detection", MB_OK | MB_ICONINFORMATION);
    }

    return detected ? 1 : 0;
}
```

The full source can be found here: https://github.com/Drew-Alleman/detect_cybercapture under `examples/strings.cpp`