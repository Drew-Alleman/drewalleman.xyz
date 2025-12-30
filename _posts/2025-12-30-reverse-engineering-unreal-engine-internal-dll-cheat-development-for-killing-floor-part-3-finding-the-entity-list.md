---
layout: post
title: "Reverse Engineering Unreal Engine and Internal DLL Cheat Development for Killing Floor (Part 3) – Finding the Entity List"
description: "In this post, I made several structural changes to the codebase to better reflect Unreal Engine’s internal object hierarchy.  By the end of this post, we will have a complete list of all entities currently loaded into the map."
date: 2025-12-30 10:38:22 -0700
categories: [game-hacking, hacking, cheats]
tags: [reverse-engineering, hacking, game-hacking]
image: /assets/images/kf_3.png
image_alt: "Killing Floor Cheats"
author: Drew Alleman
last_modified_at: 2025-12-30 10:38:22 -0700
---
# Introduction
In this post, I made several structural changes to the codebase to better reflect Unreal Engine’s internal object hierarchy.  By the end of this post, we will have a complete list of all entities currently loaded into the map.
# Changing the Pointer
I updated the `LocalPlayer` pointer to use the following address, which has proven to be significantly more reliable during testing. It now always returns the correct `LocalPlayer` pointer either in Killing Floor more or Objective. 
```
"Engine.dll"+004C6934 + 0x38
```

The player offsets will remain the same (e.g: health is still located at `0x480`). 
![Pasted image 20251230122521](/assets/images/pasted-image-20251230122521.png)

# Explaining Objects in Unreal Game Engine
Killing Floor 1 was released in 2009 and uses Unreal Engine 2. Let’s take a look at a couple of different classes defined in their documentation that represent valid entities.
## AActor
Actor is the base class for an Object that can be placed or spawned in a level. Actors may contain a collection of ActorComponents, which can be used to control how actors move, how they are rendered, etc. The other main function of an Actor is the replication of properties and function calls across the network during play. -- [Docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/AActor)
## APawn
"Pawn is the base class of all actors that can be possessed by players or AI." -- [Docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/APawn)
## APlayerController
"PlayerControllers are used by human players to control Pawns." -- [Docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/APlayerController)

## Mapping the Objects to Code
If we mapped  this logic out to C++ code it would look like the following:
```c++
// Base of all engine classes
class UObject;

// Base of all objects that can exist in the world
class AActor : public UObject;

// Base of all actors that can be controlled (Pawns)
class APawn : public AActor;

// The "Mind" that controls a Pawn
class AController : public AActor;

// Specific controller for human players
class APlayerController : public AController;
```

Let's create a  new DLL project and start creating files for these new objects.
## AActor.h
```c++
#pragma once
class AActor {
public:
    union {

        struct {
            char pad_008[0x480];
            int health;
        };

        struct {
            char pad_level[0x9c];  // New padding to reach 0x9c
            class ULevel* Level;
        };

        struct {
            char pad_003[0x14C];
            float y;                     // 0x14C (Based on your CE table)
            float x;                     // 0x150
            float z;                     // 0x154
        };
    };
};
```
## APawn.h
```c++
#pragma once
class AController;
class AActor;

class APawn : public AActor {
public:
    union {};
};
```

## APlayerController.h
```c++
#pragma once
class AActor;
class AController : public AActor {

public:
    union {};
};
```

# Creating Code to Map our APawn with Localpointer
The `LocalPlayer` object we found earlier is a `APawn`. Let's start by mapping this entity to the custom class defined in `APawn.h`. I then created 2 functions:
- `GetModules()` - - Used to load the base address of `Engine.dll`
- `GetLocalPlayer()` fetches the `LocalPlayer` pointer and loads it into an `APawn` object.
## Cheats.h

```c++
#pragma once

#include <Windows.h>
#include <iostream>
#include <vector>

// Forward Declarations: Tells the compiler these exist without loading the files yet
class AActor;
class APlayerController;
class APawn;
class ULevel;

class Cheats {
private:
    bool keepRunning = true;
    uintptr_t engineModule = 0;

public:
    APawn* myPawn = nullptr;

    bool GetModules();
    bool GetLocalPlayer();
    void Start();
    }
};
```

## Cheats.cpp
```c++
#include "pch.h"
#include "Cheats.h"
#include "AActor.h" 
#include "APawn.h"

bool Cheats::GetModules() {
    /* Loads Engine.dll Base*/
    engineModule = (uintptr_t)GetModuleHandleA("Engine.dll");
    return engineModule != NULL;
}

bool Cheats::GetLocalPlayer() {
    /*
    Loads the Currently Controlled APawn as myPawn

    Returns False if the APawn fails to load from memory

    */
    if (!engineModule && !GetModules()) {
        std::cout << "[!] Failed to fetch module handles." << std::endl;
    }
    static uintptr_t GEngineAddr = engineModule + 0x004C6934;
    uintptr_t GEngine = *(uintptr_t*)GEngineAddr;
    if (!GEngine) {
        std::cout << "[!] Failed to fetch Game Engine pointer." << std::endl;
        return false;
    };

    uintptr_t pawnAddr = *(uintptr_t*)(GEngine + 0x38);
    if (!pawnAddr) return false; 
    this->myPawn = (APawn*)pawnAddr;
    return (myPawn != nullptr);
}
```

In `Cheats.cpp` I then added the following code to set the current users health to 1337 and display the XYZ coords.
```c++
void Cheats::Start() {
    std::cout << myPawn->health << std::endl;
    std::cout << myPawn->x << std::endl;
    std::cout << myPawn->y << std::endl;
    std::cout << myPawn->z << std::endl;
    myPawn->health = 1337;
}
```

I then updated my `dllmain.cpp` to call the `Start()` function:
```c++
#include "pch.h"
#include "Cheats.h"
#include <windows.h>
#include <iostream>

void CreateConsole();
...

DWORD WINAPI MainThread(LPVOID lpParam) {
    HMODULE hModule = (HMODULE)lpParam;
    CreateConsole();
    Cheats c = Cheats();
    c.GetLocalPlayer();
    c.Start();
    std::cout << "[*] Cleaning up and Detaching..." << std::endl;
    FreeConsole();
    FreeLibraryAndExitThread(hModule, 0);
    return 0;
}
```

Then after running it we can see it set my health to 1337 and my XYZ coords are briefly displayed. <br>
![testInject](/assets/images/testinject.gif)<br>
# Finding AActor::GetLevel()  In Ghidra
In Unreal Engine 2, memory isn't just a flat list of variables; it’s a family tree. Since `APawn` inherits from `AActor`, it automatically "receives" all the properties of an Actor, such as location and level data. By mirroring this hierarchy in our C++ code, we ensure that our offsets stay perfectly aligned with the game's internal memory layout. We can browse functions that are associated to the `AActor` class by using Ghidra's function search tool at `Window` -> `Functions`.

![Pasted image 20251229172819](/assets/images/pasted-image-20251229172819.png)<br><br>

While digging through the `Engine.dll` functions in Ghidra, I stumbled upon a vital "Getter" function: `AActor::GetLevel`. By decompiling this function, we can see that it simply returns a pointer stored at `this + 0x9c`.
![Pasted image 20251230143116](/assets/images/pasted-image-20251230143116.png)<br><br>
![Pasted image 20251230143627](/assets/images/pasted-image-20251230143627.png)<br><br>
This confirms that our manual offset for the `ULevel` pointer is 100% engine-accurate. Let's update our `AActor.h`
```c++

class AActor {
public:
    union {
        struct {
            char pad_level[0x9c];  // New padding to reach 0x9c
            class ULevel* Level;
        };
    };
}
```

## Reversing GetActorIndex to get the EntityList
The level object is very important, it contains the entity list of all entities loaded into the map. Let's try to find it. I started by searching for the string "ULevel" in the functions window.<br>
![Pasted image 20251230143815](/assets/images/pasted-image-20251230143815.png)<br><br>

I found the following function:
```c++
int __thiscall ULevel::GetActorIndex(ULevel *this,AActor *param_1)

{
  int iVar1;
  void *local_10;
  undefined *puStack_c;
  undefined4 local_8;

  puStack_c = &LAB_105fba30;
  local_10 = ExceptionList;
  local_8 = 0;
  iVar1 = 0;
  while( true ) {
    if (*(int *)(this + 0x34) <= iVar1) {
      ExceptionList = &local_10;
      UObject::GetFullName((UObject *)param_1,(ushort *)0x0);
      FOutputDevice::Logf(*(FOutputDevice **)GError_exref,(ushort *)*(FOutputDevice **)GError_exref)
      ;
      ExceptionList = local_10;
      return -1;
    }
    if (*(AActor **)(*(int *)(this + 0x30) + iVar1 * 4) == param_1) break;
    iVar1 = iVar1 + 1;
  }
  return iVar1;
}

```
Look at the  lines below. `this` is in reference to the Current Level and `0x34` is the current amount of entities. This function is looking through all entities and checking if the requested AActor (param_1) matches any of the entities in the list (Level + `0x30`). 
```c++
  while( true ) {
    if (*(int *)(this + 0x34) <= iVar1) {
      ExceptionList = &local_10;
      UObject::GetFullName((UObject *)param_1,(ushort *)0x0);
      FOutputDevice::Logf(*(FOutputDevice **)GError_exref,(ushort *)*(FOutputDevice **)GError_exref)
      ;
      ExceptionList = local_10;
      return -1;
    }
    if (*(AActor **)(*(int *)(this + 0x30) + iVar1 * 4) == param_1) break;
    iVar1 = iVar1 + 1;
}	
```
We could rewrite this as the following:
```c++
  while( true ) {
    if (level->currentEntites <= i) {
      ExceptionList = &local_10;
      UObject::GetFullName((UObject *)requestedActor, 0);
      FOutputDevice::Logf(*(FOutputDevice **)GError_exref,(ushort *)*(FOutputDevice **)GError_exref);
      ExceptionList = local_10;
      return -1;
    }
    // This is accessing the entity list
    if (level->EntityList + i * 4) == requestedActor) break;
    i++;
}
```
And even more rewritten version would look like this: 
```c++
int ULevel::GetActorIndex(AActor* requestedActor) {
    int i = 0;
    
    while (true) {

        if (this->currentEntities <= i) {
            return -1; 
        }
        if (this->EntityList[i] == requestedActor) {
            break; 
        }
        i++; 
    }
    return i;
}
```

# Creating ULevel.h and Looping Through the Entity List
Let's create our new `ULevel` object with the offsets we found:
```c++
#pragma once
class ULevel {
public:
    union {
        struct {
            char pad_entityList[0x30];
            class AActor** EntityList; // Offset 0x30: Pointer to a list of Actor Pointers
            int currentEntities;       // Offset 0x34: The count of entities
            int maxEntities;           // Offset 0x38: The allocated size
        };
    };
};
```

Now we can loop through it with the following code:
```c++
#include "ULevel.h"

void Cheats::Start() {
    ULevel* Level = myPawn->Level;

    for (int i = 0; i < Level->currentEntities; i++) {
        APawn* ent = (APawn*)Level->EntityList[i];
        // If the ents not valid or me skip
        if (ent == nullptr || ent == myPawn) continue;
        
        // I don't care if they are dead
        if (ent->health <= 0) continue;
        
        std::cout << "[+] Ent: " << i << " has " << ent->health << " health.";
    }
}
```

As shown below, the level contains **4,967 entities**. In the next post, we will filter this list and enumerate additional `AActor` and `APawn` offsets.
<br><br>
![too_many_entities](/assets/images/too-many-entities.gif)
