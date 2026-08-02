---
layout: post
title: Implementing a Build-Time Backend Selection System
description: Building the build.py script that injects selected launcher, terminator, sleep, and bypass backends at compile time.
date: 2026-08-01T11:00:00-07:00
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
last_modified_at: 2026-08-01T11:00:00-07:00
---
In the previous post we established the core architecture of [profile-stealer](https://github.com/Drew-Alleman/profile-stealer): a set of interchangeable backends selected at build time so the final binary contains only the code we actually need.

That design only works if we have a reliable way to select and inject the chosen backends before compilation. In this post we implement that piece `build.py`.

The script is responsible for:
1. Parsing the user’s choices
2. Safely backing up the source tree
3. Copying the selected backend implementations into place
4. Writing any tunable parameters (sleep timing / jitter)
5. Driving a clean CMake build
6. Restoring the original source if anything fails

Visually this workflow would look like the following:
![Showcase](/assets/images/Blank diagram - Page 1(5).png)

File structure of our project:
```
profile-stealer/
├── 📄 CMakeLists.txt
├── 📄 build.py
├── 📁 build/
├── 📁 imports/
├── 📁 src/           
│   ├── 📄 main.cpp
│   ├── 📁 app/
│   ├── 📁 browsers/ 
│   ├── 📁 bypass_methods/
│   ├── 📁 common/ 
│   ├── 📁 launchers/
│   ├── 📁 manager/ 
│   ├── 📁 sleep/ 
│   └── 📁 terminators/
│
│   // These are our concrete implementations 
└── 📁 methods/
    ├── 📁 bypass_methods/
    ├── 📁 launchers/
    │   ├── 📁 linux/
    │   └── 📁 windows/
    ├── 📁 sleep/
    │   ├── 📁 linux/
    │   └── 📁 windows/
    └── 📁 terminators/
        ├── 📁 linux/
        └── 📁 windows/
```
## Argument Handling
We can handle user input with the extremely popular [argparse](https://docs.python.org/3/library/argparse.html) library.  The script also detects the current operating system so it only offers valid backends for that platform.
```python
import argparse
import platform

import argparse
import platform

def parse_args():
    """Parse command-line options and only offer backends valid for the current OS."""
    system = platform.system().lower()
    is_linux = system == "linux"

    # Platform-specific choices
    if is_linux:
        term_choices = ["sigkill"]
        default_term = "sigkill"
        launcher_choices = ["posix_spawn"]
        default_launcher = "posix_spawn"
        sleep_choices = ["generic_linux", "timer_linux"]
        default_sleep = "generic_linux"
    else:
        term_choices = ["TerminateProcess"]
        default_term = "TerminateProcess"
        launcher_choices = ["shellexecuteex", "createprocessw"]
        default_launcher = "createprocessw"
        sleep_choices = ["generic_windows", "timer_windows"]
        default_sleep = "generic_windows"

    print(f"[*] Detected OS: {platform.system()} – only native methods available")

    parser = argparse.ArgumentParser(description="Builds and compiles profile-stealer")

    parser.add_argument(
        "-T", "--termination-method",
        choices=term_choices,
        default=default_term,
        help="Method used to terminate processes (default: %(default)s)",
    )
    parser.add_argument(
        "-L", "--launcher-method",
        choices=launcher_choices,
        default=default_launcher,
        help="Method used to launch processes (default: %(default)s)",
    )
    parser.add_argument(
        "-B", "--bypass-method",
        choices=["cdp"],          # extend this list as you add more
        default="cdp",
        help="Bypass method to inject (default: %(default)s)",
    )
    parser.add_argument(
        "-S", "--sleep-method",
        choices=sleep_choices,
        default=default_sleep,
        help="Sleep implementation (default: %(default)s)",
    )
    parser.add_argument(
        "-M", "--sleep-ms",
        type=int,
        default=2000,
        help="Base sleep duration in ms written to sleep_common.h (default: %(default)s)",
    )
    parser.add_argument(
        "-J", "--sleep-jitter",
        type=float,
        default=25.0,
        help="Sleep jitter percentage written to sleep_common.h (default: %(default)s)",
    )

    return parser.parse_args()
```

All of the heavy lifting is handled by a single class called `BuildManager`. It receives the selected backends and configuration options from the command line, then orchestrates the full pipeline: backing up the original source tree, swapping in the chosen backend implementations, writing any tunable parameters (such as sleep timing), compiling the project with CMake, and restoring the source tree if anything fails.

```Python
class BuildManager:
    def __init__(
        self,
        termination_method: str,
        launcher_method: str,
        bypass_method: str,
        sleep_method: str,
        sleep_ms: int = 2000,
        sleep_jitter: float = 25.0,
    ) -> None:
        self.termination_method = termination_method
        self.launcher_method = launcher_method
        self.bypass_method = bypass_method
        self.sleep_method = sleep_method
        self.sleep_ms = sleep_ms
        self.sleep_jitter = sleep_jitter
        self.backup_path = None
	
	# A dictionary of the selected methods
	@property
	def selections(self) -> dict:
	    return {
	        "bypass":     self.bypass_method.lower(),
	        "launcher":   self.launcher_method.lower(),
	        "terminator": self.termination_method.lower(),
	        "sleep":      self.sleep_method.lower(),
	    }
```

We wire everything together in a simple main function:
```Python
def main():
    args = parse_args()

    manager = BuildManager(
        termination_method=args.termination_method,
        launcher_method=args.launcher_method,
        bypass_method=args.bypass_method,
        sleep_method=args.sleep_method,
        sleep_ms=args.sleep_ms,
        sleep_jitter=args.sleep_jitter,
    )

    manager.start()

if __name__ == "__main__":
    main()
```

## Backing up/Restoring the Original Source Code
Because the build process repeatedly overwrites files in the src/ directory, we first create a temporary backup of the original source tree:
```python
import shutil 
import tempfile 
from pathlib import Path

class BuildManager:
    def backup_source(self) -> bool:
        """
        Uses shutil to make a copy of the src folder to a temporary folder
        """
        cwd = Path.cwd()
        src_dir = cwd / "src"
        if not src_dir.is_dir():
            print("[-] src/ directory not found")
            return False

        backup_root = None
        try:
            # Use a real system temporary directory
            backup_root = Path(tempfile.mkdtemp(prefix="backup_"))
            shutil.copytree(src_dir, backup_root / "src")
        except (OSError, shutil.Error) as e:
            print(f"[-] Backup failed: {e}")
            self.backup_path = None
            if backup_root is not None:
                shutil.rmtree(backup_root, ignore_errors=True)
            return False

        self.backup_path = backup_root
        print(f"[+] Source backed up to: {backup_root}")
        return True
```

Below is a function to restore the backup from the temporary directory:
```python
import shutil 
import tempfile 
from pathlib import Path

class BuildManager:
    def restore_source(self) -> bool:
        if self.backup_path is None or not self.backup_path.is_dir():
            print("[-] No backup available to restore")
            return False

        backed_src = self.backup_path / "src"
        if not backed_src.is_dir():
            print("[-] Backed-up src/ is missing")
            return False

        cwd = Path.cwd()
        current_src = cwd / "src"
        displaced_src = None

        try:
            if current_src.exists():
                # Move the live src/ aside instead of deleting it outright,
                # so a failed copytree doesn't leave us with nothing.
                displaced_src = current_src.with_name(current_src.name + ".pre_restore")
                if displaced_src.exists():
                    shutil.rmtree(displaced_src)
                current_src.rename(displaced_src)

            shutil.copytree(backed_src, current_src)

        except (OSError, shutil.Error) as e:
            print(f"[-] Restore failed: {e}")
            # Roll back: put the original src/ back if we moved it and the
            # new copy didn't fully land.
            if displaced_src is not None and displaced_src.exists() and not current_src.exists():
                displaced_src.rename(current_src)
            return False

        # Restore succeeded - safe to drop the displaced copy now.
        if displaced_src is not None and displaced_src.exists():
            shutil.rmtree(displaced_src, ignore_errors=True)

        print(f"[+] Source restored from: {self.backup_path}")
        return True
```

## Managing User Injected Methods
User choices from the CLI (e.g. `--termination-method`, `--launcher-method`) are stored as attributes on the `BuildManager` instance:
- `self.termination_method`
- `self.launcher_method`
- `self.bypass_method`
- `self.sleep_method`

These string values do **not** directly point to files. Instead, two nested structures provide a clean mapping:
```Python
## Concrete Implementations
METHODS = {
    "bypass": {
        "cdp": "methods/bypass_methods/cdp.hpp",
    },
    "launcher": {
        "shellexecuteex": "methods/launchers/windows/ShellExecuteEx.hpp",
        "createprocessw": "methods/launchers/windows/CreateProcessW.hpp",
        "posix_spawn":    "methods/launchers/linux/posix_spawn.hpp",
    },
    "terminator": {
        "terminateprocess": "methods/terminators/windows/TerminateProcess.hpp",
        "sigkill":          "methods/terminators/linux/sigkill.hpp",
    },
    "sleep": {
        "generic_windows": "methods/sleep/windows/generic.hpp",
        "generic_linux":   "methods/sleep/linux/generic.hpp",
        "timer_windows":   "methods/sleep/windows/timer.hpp",
        "timer_linux":     "methods/sleep/linux/timer.hpp",
    },
}
# The file to overwrite
TARGETS = {
    "bypass":     "src/bypass_methods/bypass.hpp",
    "launcher":   "src/launchers/launcher.hpp",
    "terminator": "src/terminators/terminator.hpp",
    "sleep":      "src/sleep/sleep.hpp",
}
```

The actual work of applying the user’s selections is performed by `adjust_source`. This method walks through each category, resolves the concrete implementation from `METHODS`, and overwrites the corresponding file listed in `TARGETS`:
```python

class BuildManager:
    def adjust_source(self) -> bool:
        try:
            cwd = Path.cwd()
            print(f"[*] Working directory: {cwd}")

            for category, method_key in self.selections.items():
                # Check if it is in our dictionary
                if category not in METHODS or method_key not in METHODS[category]:
                    print(f"[-] Unknown {category} method: {method_key}")
                    return False

                # Create the full filename of the method to use
                src_file = cwd / METHODS[category][method_key]

                # Create the full filename of the target file to overwrite
                dst_file = cwd / TARGETS[category]

                print(f"\n[*] Processing {category} ({method_key})")
                print(f" Source : {src_file}")
                print(f" Target : {dst_file}")

                if not src_file.is_file():
                    print(f"[-] Implementation file not found: {src_file}")
                    return False

                # Overwrite the file
                shutil.copy2(src_file, dst_file)

                # Check if the file is actually there
                if dst_file.is_file() and dst_file.stat().st_size == src_file.stat().st_size:
                    print(f"[+] Successfully overwrote → {dst_file}")
                else:
                    print(f"[-] Copy appeared to fail for {dst_file}")
                    return False

            print("\n[+] All method files installed successfully")
            return True

        except (OSError, shutil.Error) as e:
            print(f"[-] Failed to adjust source: {e}")
            return False
```

## Handling Compilation 
Once the selected backends have been copied into the source tree, the project is ready to be built. 

Rather than one long function, the logic is split into three pieces that build on each other. Here's each one, from the ground up.
### Cleaning the build directory
```python
def _clean(self, build_dir: Path) -> None:
    # Always start clean – avoids Windows <-> WSL CMakeCache path mismatches
    if build_dir.exists():
        print(f"[+] Removing previous {build_dir}/ directory...")
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
```

CMake caches absolute paths inside `CMakeCache.txt`, and those paths don't survive a jump between a native Windows toolchain and WSL. Rather than trying to detect and repair a mismatched cache, `_clean` just removes it.  If `build_dir` exists, it's deleted outright, then recreated empty. No partial state carries over between runs.

### Running a single CMake step
```python
def _run_step(self, label: str, cmd: list[str], timeout: int = 1800) -> bool:
    print(f"[+] Running {label}: {' '.join(cmd)}")
    result = subprocess.run(cmd, timeout=timeout)
    if result.returncode != 0:
        print(f"[-] {label} failed with exit code {result.returncode}")
        return False
    return True
```

Both configure and build are, mechanically, the same thing: run a command, check the exit code, report success or failure. `_run_step` captures that pattern once so it isn't duplicated. It takes a human-readable `label` for logging, the full command as an argv list, and a `timeout` so a hung CMake invocation can't stall the build indefinitely. 
### Tying it together
```python
def build(self, source_dir: Path = Path("."), build_dir: Path = Path("build")) -> bool:
    try:
        self._clean(build_dir)
        return self._run_step(
            "configure",
            ["cmake", "-S", str(source_dir), "-B", str(build_dir),
             f"-DCMAKE_BUILD_TYPE={self.build_type}"],
        ) and self._run_step(
            "build",
            ["cmake", "--build", str(build_dir), "--config", self.build_type]
            + (["--parallel", str(self.jobs)] if self.jobs else []),
        )
    except FileNotFoundError:
        print("[-] cmake is not installed or not on PATH")
        return False
```

`build` is the entry point, and by the time you reach it, there's not much left to do. It cleans the build directory, then chains the two `_run_step` calls with `and`, so a failed configure short-circuits and skips the build step entirely rather than trying to build against a broken configuration. The `FileNotFoundError` catch covers the one dependency this whole process assumes: that `cmake` is actually installed and on `PATH`.
## Handling Custom Sleep Arguments 
Like the other backends, the concrete sleep implementation lives under methods/sleep/, while a small shared header holds the tunable values:

```
profile-stealer/
├── 📁 src/           
│   └── 📁 sleep/ 
|		└── 📄 sleep_common.h
└── 📁 methods/
    ├── 📁 sleep/
        ├── 📁 linux/
		│	├── 📄 timer.hpp
    	│	└── 📄 generic_sleep.hpp
        └── 📁 windows/
		    ├── 📄 timer.hpp
		    └── 📄 generic_sleep.hpp
```

`sleep_common.h` contains only the two constants that the build script is allowed to change:
```c++
#pragma once

const int SLEEP_MS = 2;
const float SLEEP_JITTER = 25.0f;
```

Every concrete sleep backend includes this header and uses the constants. Here is the Linux nanosleep implementation as an example:
```c++
#pragma once
#include "sleep_common.h"
#include <time.h>
#include <cerrno>
#include <random>

// by default use the set sleep time
inline void sleepMs(int sleepTime = SLEEP_MS) {
    if (sleepTime <= 0) return;

    double delay = sleepTime;
    if (SLEEP_JITTER > 0.0f) {
        static thread_local std::mt19937 rng{ std::random_device{}() };
        std::uniform_real_distribution<double> dist(-SLEEP_JITTER, SLEEP_JITTER);
        delay += delay * dist(rng);
        if (delay < 0.0) delay = 0.0;
    }

    long total = static_cast<long>(delay);
    struct timespec req;
    req.tv_sec = total / 1000;
    req.tv_nsec = (total % 1000) * 1000000L;   // ms -> ns
    while (nanosleep(&req, &req) == -1 && errno == EINTR) {}
}
```

Two new arguments are added to `parse_args()`:
```python
def parse_args():
	"""
	Defines and parses the user’s command-line options. Will auto detect
	the OS using platform.system() to determine invalid options.
	"""
	# Detect the OS 
    system = platform.system().lower()
    is_linux = system == "linux"
    
    # Truncated 
    
    parser.add_argument(
        "-M", "--sleep-ms",
        type=int,
        default=2,
        help="Base sleep duration in ms written to sleep_common.h (default: %(default)s)",
    )
    parser.add_argument(
        "-J", "--sleep-jitter",
        type=float,
        default=25.0,
        help="Sleep jitter percentage written to sleep_common.h (default: %(default)s)",
    )
    return parser.parse_args()
```

`BuildManager` receives the chosen values and rewrites `sleep_common.h` before compilation:
```python
class BuildManager:

    def write_sleep_common(self) -> bool:
        path = Path("src/sleep/sleep_common.h")
        content = (
            "#pragma once\n"
            "\n"
            f"const int SLEEP_MS = {self.sleep_ms};\n"
            f"const float SLEEP_JITTER = {self.sleep_jitter}f;\n"
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        except OSError as e:
            print(f"[-] Failed to write sleep_common.h: {e}")
            return False
        print(f"[+] Wrote {path} → SLEEP_MS={self.sleep_ms}, SLEEP_JITTER={self.sleep_jitter}")
        return True

```

We can then add a call to `write_sleep_common` in `adjust_source`:

```python
    def adjust_source(self) -> bool:
        try:
            cwd = Path.cwd()
            print(f"[*] Working directory: {cwd}")

            selections = {
                "bypass":     self.bypass_method.lower(),
                "launcher":   self.launcher_method.lower(),
                "terminator": self.termination_method.lower(),
                "sleep":      self.sleep_method.lower(),
            }

            for category, method_key in selections.items():
                if category not in METHODS or method_key not in METHODS[category]:
                    print(f"[-] Unknown {category} method: {method_key}")
                    return False

                src_file = cwd / METHODS[category][method_key]
                dst_file = cwd / TARGETS[category]

                print(f"\n[*] Processing {category} ({method_key})")
                ## <TRUNCATED>

			## our call to overwrite the sleep config
            if not self.write_sleep_common():
                return False

            print("\n[+] All method files installed successfully")
            return True

        except Exception as e:
            print(f"[-] Failed to adjust source: {e}")
            return False

```
## Putting it all Together
All of the individual pieces are orchestrated by a single method: `start()`. This is the entry point that runs the full build pipeline in the correct order and guarantees the source tree is restored no matter what happens.
```python
    def start(self) -> None:
        try:
            if not self.backup_source():
                exit("[-] failed to backup the original source code; exiting")

            if not self.adjust_source():
                print("[-] failed to adjust source code for user specified options")
                return

            print("[*] Compiling source code...")
            if not self.build():          # or self.compile() depending on naming
                print("[-] Failed to compile source code")
                return

            print("[+] Compiled source code")
        finally:
            # Always try to restore (safe even if backup_path is None)
            if not self.restore_source():
                return
            # Always clean up the temporary backup directory
            if self.backup_path is not None and self.backup_path.exists():
                shutil.rmtree(self.backup_path, ignore_errors=True)
                self.backup_path = None
```

When we execute this script it auto determines the appropriate methods to use based on our operating system and compiles the program:
```
PS C:\Users\drew\Desktop\profile-stealer> python .\build.py
[*] Detected OS: Windows – only native methods available
[+] Source backed up to: C:\Users\drew\AppData\Local\Temp\backup_qzb2vxv3
[*] Working directory: C:\Users\drew\Desktop\profile-stealer

[*] Processing bypass (cdp)
 Source : C:\Users\drew\Desktop\profile-stealer\methods\bypass_methods\cdp.hpp
 Target : C:\Users\drew\Desktop\profile-stealer\src\bypass_methods\bypass.hpp
[+] Successfully overwrote → C:\Users\drew\Desktop\profile-stealer\src\bypass_methods\bypass.hpp

[*] Processing launcher (createprocessw)
 Source : C:\Users\drew\Desktop\profile-stealer\methods\launchers\windows\CreateProcessW.hpp
 Target : C:\Users\drew\Desktop\profile-stealer\src\launchers\launcher.hpp
[+] Successfully overwrote → C:\Users\drew\Desktop\profile-stealer\src\launchers\launcher.hpp

[*] Processing terminator (terminateprocess)
 Source : C:\Users\drew\Desktop\profile-stealer\methods\terminators\windows\TerminateProcess.hpp
 Target : C:\Users\drew\Desktop\profile-stealer\src\terminators\terminator.hpp
[+] Successfully overwrote → C:\Users\drew\Desktop\profile-stealer\src\terminators\terminator.hpp

[*] Processing sleep (generic_windows)
 Source : C:\Users\drew\Desktop\profile-stealer\methods\sleep\windows\generic.hpp
 Target : C:\Users\drew\Desktop\profile-stealer\src\sleep\sleep.hpp
[+] Successfully overwrote → C:\Users\drew\Desktop\profile-stealer\src\sleep\sleep.hpp

[+] All method files installed successfully
[*] Compiling source code...
[+] Removing previous build/ directory...
[+] Running configure: cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
[+] Running build: cmake --build build --config Release

MSBuild version 18.9.1+a81b43525 for .NET Framework
.vcxproj -> C:\Users\drew\Desktop\profile-stealer\build\bin\Release\profile-stealer.exe
  Building Custom Rule C:/Users/drew/Desktop/profile-stealer/CMakeLists.txt
[+] Compiled source code
[+] Source restored from: C:\Users\drew\AppData\Local\Temp\backup_qzb2vxv3
```

## Conclusion
With build.py in place, the modular architecture is now fully functional. The script safely selects the desired backends, injects them into the source tree, writes any tunable parameters, drives the CMake build, and always restores the original source. In the next post we will move one level higher and define a consistent structure that every extraction technique (bypass method) will follow.