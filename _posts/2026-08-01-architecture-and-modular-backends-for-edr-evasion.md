---
layout: post
title: Building an EDR-Evasive Chromium Profile Stealer – Architecture & Modular Backends for EDR Evasion
description: Exploring modular process launching and termination backends designed for EDR/AV evasion in a Chromium profile stealer.
date: 2026-08-01T10:00:00-07:00
image: /assets/images/profile-stealer.png
categories:
  - red-teaming
  - malware-development
tags:
  - edr-evasion
  - av-evasion
  - chromium
  - profile-stealer
author: Drew Alleman
last_modified_at: 2026-08-01T10:00:00-07:00
---

**Disclaimer:** This series is published strictly for educational and research purposes. The author does not condone or encourage the use of any techniques described here for unauthorized access, data theft, or any other illegal activity. Using these methods against systems you do not own or have explicit permission to test is illegal and may result in criminal and civil liability. The author assumes no responsibility or liability for any misuse of the information provided in this series. Readers are solely responsible for ensuring their actions comply with all applicable laws and regulations. By continuing to read, you acknowledge that you understand this disclaimer and agree to use the information responsibly and legally.

In this series I’ll explore practical tactics for designing software that operates in environments with heavy EDR/AV presence.

I’ll be building [profile-stealer](https://github.com/Drew-Alleman/profile-stealer), a cross-platform, EDR/AV-evasive tool that extracts a user’s Chromium profile database files. Instead of having an untrusted process open the profile files directly which is the behavior most EDR/AV products are tuned to detect. It instead routes the read/download through a legitimate, signed Chromium process so the access appears expected.

The tool currently supports three high-level extraction methods:

**CDP Method**
- Launch Chrome with `--remote-debugging-port`, `--allow-file-access-from-files` and `--headless` so it can be controlled remotely.
- Establish a CDP connection to the browser (handled by `cdp_minimal`).
- Download the Chromium profile files, with a short sleep between each request.
- Zip the downloaded files and delete the temporary copies.
- Optionally terminate the spawned process

**Windows Position (Windows Only)**
- Launch multiple Chrome instances using a custom chromium argument to spawn the GUI offscreen using invalid windows position coordinates. (with a short sleep between launches), each pointed at a local Chromium database file.
- The browser automatically downloads the file to the user’s Downloads folder.
- Zip all downloaded files and delete the temporary copies.
- Optionally terminate the spawned process

**Ozone (Linux Only)**
- Launch multiple headless Chrome instances (with a short sleep between launches), each pointed at a local Chromium database file.
- The browser automatically downloads the file to the user’s Downloads folder.
- Zip all downloaded files and delete the temporary copies.
- Optionally terminate the spawned process

In this post I’ll focus on the design of the cross-platform, interchangeable low-level components (process launching and termination). These components are selected at build time so the final binary contains only the chosen implementation; no unused APIs and no dead code.

Both extraction methods depend on starting and stopping processes these are actions that are heavily monitored by EDR/AV. This leads to a set of strict design constraints.
### Design Constraints
To stay resilient against static signatures and EDR detection, every core feature must be fully modular and interchangeable. If one execution path gets flagged, switching to a new method should not require a large refactor.

The architecture therefore supports swappable backends. At build time the developer can choose, for example, between native Windows APIs such as [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw) and [ShellExecuteEx](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecuteexa). When `CreateProcessW` is selected, every reference to `ShellExecuteEx` is completely excluded from the compiled binary, keeping the static footprint minimal.

Isolating each implementation in its own file also keeps the project maintainable: developers never have to dig through a single monolithic source file to make changes.
### Solution
The whole architecture is built around one simple idea: every cross-platform feature is written as a set of interchangeable backends that all share the same interface. Instead of the application code deciding which implementation to use at runtime, a small generation step runs before compilation. This generation step (a Python script called build.py) looks at the options you choose and only copies the selected backend into the source tree. As a result, the final binary contains exactly the implementation you asked for and nothing else.

The end user can specify which options they want using command line arguments:
```
python3 build.py --launcher=CreateProcessW --kill=TerminateProcess --sleep=generic
```

For example, let’s take a look at launching processes. A capability like launching a process is defined in two parts. A base class, `LauncherBase`, holds the data common to every implementation (the executable path and its arguments) and the helpers that format them. A result struct, `LaunchResult`, carries the outcome back to the caller: whether it succeeded, the new process ID, the native error code, and a detail string so a failure is diagnosable rather than a bare false.

The application is written once against this contract:

```c++
Launcher launcher(path, args);
LaunchResult r = launcher.launch();
if (!r) {
    // r.errorCode and r.detail explain exactly what the OS refused
}
```

Behind the Launcher name sits exactly one backend, chosen by the builder. Each lives in its own discrete file and wraps a single native API call - `CreateProcessW`, `ShellExecuteEx`, or `posix_spawn`. The launcher class translates that API's particular demands (UTF-16 conversion on Windows, argv-array construction on POSIX, handle cleanup, GetLastError versus errno) internally, so none of it leaks above the contract.

Figure 1 – Launcher class hierarchy:
![Showcase](/assets/images/Blank diagram - Page 1(1).png)

Terminating a process mirrors that structure exactly: a Terminator family returning a T`erminationResult`, backed by either `TerminateProcess` or `kill(SIGKILL)`. Because the two backends share a name, a constructor, a method signature, and a return type, they're genuinely swappable. So pivoting away from a flagged execution path is a matter of selecting a different backend and not refactoring the callers that depend on it.

Figure 2 – Terminator class hierarchy
![Showcase](/assets/images/Blank diagram - Page 1(3).png)

Here is the shared contract used by every terminator backend:
```c++
struct TerminationResult {
    bool        ok = false;
    int         errorCode = 0;      // GetLastError() on Windows, errno on Linux
    std::string detail;

    explicit operator bool() const { return ok; }
};

class TerminatorBase {
public:
    explicit TerminatorBase(int pid) : m_pid(pid) {}

    bool isValid() const {
        return m_pid > 0;
    }

protected:
    int m_pid = 0;
};
```

And here is one concrete backend. This is the Linux implementation that sends SIGKILL:
```c++
#pragma once

#include <csignal>       // kill, SIGKILL
#include <cerrno>        // errno
#include "terminators/terminator_common.h" // This is where TerminationResult and TerminatorBase are defined!

// ===========================================================================
// POSIX Terminator using kill(pid, SIGKILL)
// ===========================================================================
class Terminator final : public TerminatorBase {
public:
    using TerminatorBase::TerminatorBase;   // reuse base ctor: Terminator(pid)

    const char* backendName() const noexcept { return "posix/kill(SIGKILL)"; }

    TerminationResult kill() const {
        TerminationResult r;

        if (!isValid()) {                    // inherited from base
            r.detail = "invalid pid";
            return r;                        // r.ok stays false
        }

        if (::kill(static_cast<pid_t>(m_pid), SIGKILL) != 0) {
            r.errorCode = errno;             // ESRCH, EPERM, etc.
            r.detail = "kill failed";
            return r;
        }

        r.ok = true;
        r.detail = "terminated";
        return r;
    }
};
```

## Putting it all Together
We’ve now seen the same pattern applied to both process launching and process termination: a shared base class, a rich result object, and a single concrete backend that is selected at build time.

This modular approach is the foundation of the entire project. With the core design principles established, we can now look at the full set of axes the tool will support and the file structure that makes them possible.
### Axes
* Terminator (Process Termination)
* Launcher (Process Execution)
* Bypass Methods (Chromium profile extraction techniques)
* Sleep (Sleep / delay implementations)

We can map all of the concepts we talked about in this blog to the following file structure:
```
profile-stealer/
├── 📄 CMakeLists.txt
├── 📄 build.py
├── 📁 build/
├── 📁 imports/
├── 📁 src/           
│   ├── 📄 main.cpp
│   ├── 📁 app/  # code to handle arguments and console logging/printing
│   │   ├── console.h
│   │   └── context.h
│   ├── 📁 browsers/ # Code to handle finding installed browsers on a system
│   │   ├── browsers.cpp
│   │   └── browsers.h
│   ├── 📁 bypass_methods/ # Base Code for Bypass Methods 
│   │   ├── bypass.hpp
│   │   └── bypass_common.h
│   ├── 📁 common/ # Helpers for the Bypass method
│   │   └── download.hpp
│   ├── 📁 launchers/ # Base Code for launcher Methods 
│   │   ├── launcher.hpp
│   │   └── launcher_common.h
│   ├── 📁 manager/ # Handles downloading the files through the bypass method
│   │   ├── manager.cpp
│   │   └── manager.h
│   ├── 📁 sleep/ # Base code for sleep methods
│   │   ├── sleep.hpp
│   │   └── sleep_common.h
│   └── 📁 terminators/ # Base code for terminator methods
│       ├── terminator.hpp
│       └── terminator_common.h
│
└── 📁 methods/ # These files are dropped in at build time replacing the bypass.hpp, launcher.hpp, sleep.hpp, or terminator.hpp respectively.
    ├── 📁 bypass_methods/
    │   ├── cdp.hpp
    │   └── headless.hpp
    ├── 📁 launchers/
    │   ├── 📁 linux/
    │   │   └── posix_spawn.hpp
    │   └── 📁 windows/
    │       ├── CreateProcessW.hpp
    │       └── ShellExecuteEx.hpp
    ├── 📁 sleep/
    │   ├── 📁 linux/
    │   │   ├── generic.hpp
    │   │   └── timer.hpp
    │   └── 📁 windows/
    │       ├── generic.hpp
    │       └── timer.hpp
    └── 📁 terminators/
        ├── 📁 linux/
        │   └── sigkill.hpp
        └── 📁 windows/
            └── TerminateProcess.hpp
```
