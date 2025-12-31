---
layout: post
title: "Reverse Engineering Unreal Engine and Internal DLL Cheat Development for Killing Floor (Part 5) – Creating an Instakill Cheat, Messing and with DrawScales"
description: "In this post we are manipulating the core AActor class. I’ll be walking you through the logic for a mass health override forcing every Zed in the level to 1 HP. Then diving into the renderer's memory to physically scale enemy models."
date: 2025-12-30 16:38:22 -0700
categories: [game-hacking, hacking, cheats]
tags: [reverse-engineering, hacking, game-hacking]
image: /assets/images/kf_5.png
image_alt: "Killing Floor Cheats"
author: Drew Alleman
last_modified_at: 2025-16-30 12:38:22 -0700
---

# Introduction
In this post we are manipulating the core `AActor` class. I’ll be walking you through the logic for a mass health override forcing every Zed in the level to 1 HP. Then diving into the renderer's memory to physically scale enemy models.
# Creating a Function to Fetch the Moving AActors
To keep our cheats efficient, we don't want to loop through every static chair or lamp in the map. This helper function filters the Entity List for 'Active' Pawns—things that are walking, falling, and most importantly, alive
## Cheats.h
```c++
#include <Windows.h>
#include <iostream>
#include <vector>

class Cheats {
private:
    uintptr_t engineModule = 0;

public:
    APawn* myPawn = nullptr;
    bool GetModules();
    bool GetLocalPlayer();
    std::vector<AActor*> GetMovingAActors(); // NEW
    void Start();
};
```
## Cheats.cpp
Most of this code is the same from earlier we are just placing the moving ones into a `std::vector`. 
```c++
std::vector<AActor*> Cheats::GetMovingAActors() {
    std::vector<AActor*> AActors;
    ULevel* Level = myPawn->Level;
    if (!Level) return AActors;
    for (int i = 0; i < Level->currentEntities; i++) {

        AActor* genericActor = Level->EntityList[i];
        if (!genericActor || genericActor == (AActor*)myPawn) continue;

        if (genericActor->physics != PHYS::Walking && genericActor->physics != PHYS::Falling) continue;

        APawn* ent = (APawn*)genericActor;
        if (ent->health <= 0 || ent->health > 10000) continue;

        AActors.push_back(ent);
    }
    return AActors;
}
```

# Creating an InstaKill Cheat
Next, we’re implementing a InstaKill cheat. This function scans the world’s active entity list and forcibly overrides the health of all hostile actors to 1 (excluding the local player).
## Cheats.h
```c++
class Cheats {
public:
    std::vector<AActor*> GetMovingAActors();
    void InstaKill();
};
```

## Cheats.cpp
```c++
void Cheats::InstaKill() {
    std::vector<AActor*> AActors = GetMovingAActors();
    if (AActors.empty()) {
        std::cout << "[!] No actors to instakill in map!" << std::endl;
        return;
    }

    for (AActor* actor : AActors) {
	    // If the actor is not us!
        if (actor == myPawn) {
            continue;
        }
        if (actor->health != 1) {
            actor->health = 1;
        }
        std::cout << "[!] Set Entity to 1 HP!" << std::endl;
    }

}
```

Now we can modify our cheat loop so every time we press F1 it sets there health to 1 HP!
```c++
void Cheats::Start() {

    while (!GetAsyncKeyState(VK_END) & 1) {
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

        Sleep(50);
    }
}
```
![instakill](/assets/images/instakill.gif)
# AActor::SetDrawScale()
I was looking around the `AActor` methods and I found a function called `SetDrawScale`.
![Pasted image 20251230194819](/assets/images/pasted-image-20251230194819.png)

This is the decompiled function in Ghidra:
```c++
void __thiscall AActor::SetDrawScale(AActor *this,float newDrawScale)

{
  void *local_10;
  undefined *puStack_c;
  undefined4 local_8;
  
                    /* 0xd5250  6089  ?SetDrawScale@AActor@@QAEXM@Z */
  puStack_c = &LAB_1060a290;
  local_10 = ExceptionList;
  local_8 = 0;
  ExceptionList = &local_10;
  if ((((byte)this[0x2c4] & 1) != 0) &&
     (ExceptionList = &local_10, *(int **)(*(int *)(this + 0x9c) + 0xf0) != (int *)0x0)) {
    ExceptionList = &local_10;
    (**(code **)(**(int **)(*(int *)(this + 0x9c) + 0xf0) + 0xc))(this);
  }
  *(float *)(this + 0x260) = newDrawScale;
  if ((((byte)this[0x2c4] & 1) != 0) && (*(int **)(*(int *)(this + 0x9c) + 0xf0) != (int *)0x0)) {
    (**(code **)(**(int **)(*(int *)(this + 0x9c) + 0xf0) + 8))(this);
  }
  *(uint *)(this + 0x70) = *(uint *)(this + 0x70) | 0x40;
  ClearRenderData(this);
  ExceptionList = local_10;
  return;
}
```

Right in the middle of the function we see the following line:
```c++
 *(float *)(this + 0x260) = newDrawScale;

 // We could rewrite the line above as the following
 AActor->drawScale = newDrawScale
```

Now we can add the offset to our `AActor` class:
```c++
class AActor {
public:
    union {
        struct {
            char pad_drawSize[0x260];
            float drawSize;
        };
    };
}
```

Then I added this write call in my `InstaKill` 
```c++
if (actor->health != 1) {
	actor->health = 1;
	actor->drawSize = -5.5;
}
```

![scale](/assets/images/scale.gif)

# AActor::SetDrawScale3D
![Pasted image 20251230202135](/assets/images/pasted-image-20251230202135.png)

```c++
void __thiscall
AActor::SetDrawScale3D(void *this,undefined4 param_11,undefined4 param_12,undefined4 param_13)

{
  int *piVar1;
  void *local_10;
  undefined *puStack_c;
  undefined4 local_8;
  
                    /* 0xd54d0  6088  ?SetDrawScale3D@AActor@@QAEXVFVector@@@Z */
  puStack_c = &LAB_1060a2c0;
  local_10 = ExceptionList;
  local_8 = 0;
  ExceptionList = &local_10;
  if (((*(byte *)((int)this + 0x2c4) & 1) != 0) &&
     (piVar1 = *(int **)(*(int *)((int)this + 0x9c) + 0xf0), ExceptionList = &local_10,
     piVar1 != (int *)0x0)) {
    ExceptionList = &local_10;
    (**(code **)(*piVar1 + 0xc))(this);
  }
  *(undefined4 *)((int)this + 0x264) = param_11; // x ?
  *(undefined4 *)((int)this + 0x268) = param_12; // y ?
  *(undefined4 *)((int)this + 0x26c) = param_13; // z ?
  if (((*(byte *)((int)this + 0x2c4) & 1) != 0) &&
     (piVar1 = *(int **)(*(int *)((int)this + 0x9c) + 0xf0), piVar1 != (int *)0x0)) {
    (**(code **)(*piVar1 + 8))(this);
  }
  *(uint *)((int)this + 0x70) = *(uint *)((int)this + 0x70) | 0x40;
  ClearRenderData((AActor *)this);
  ExceptionList = local_10;
  return;
}
```

This next section jumps out to me as the 3D Draw Scale modifiers:
```c++
  *(undefined4 *)((int)this + 0x264) = param_11; // x ?
  *(undefined4 *)((int)this + 0x268) = param_12; // y ?
  *(undefined4 *)((int)this + 0x26c) = param_13; // z ?
```

```c++
class AActor {
public:
    union {
        struct {
            char pad_drawSize[0x264];
            float x3DDrawScale;
            float y3DDrawScale;
            float z3DDrawScale;
        };
    };
}
```

I then added 2 separate functions to handle the scaling of `AActors` `ScaleAActorsUp()` and `ScaleAActorsDown()`.
```c++
void Cheats::ScaleAActorsUp() {
    std::vector<AActor*> AActors = GetMovingAActors();
    if (AActors.empty()) {
        std::cout << "[!] No actors to scale up in map!" << std::endl;
        return;
    }

    for (AActor* actor : AActors) {
        actor->x3DDrawScale = actor->x3DDrawScale * 2;
        actor->y3DDrawScale = actor->y3DDrawScale * 2;
        actor->z3DDrawScale = actor->z3DDrawScale * 2;
        actor->drawSize = actor->drawSize * 2;
    }
}

void Cheats::ScaleAActorsDown() {
    std::vector<AActor*> AActors = GetMovingAActors();
    if (AActors.empty()) {
        std::cout << "[!] No actors to scale down in map!" << std::endl;
        return;
    }

    for (AActor* actor : AActors) {
        actor->x3DDrawScale /= 2.0f;
        actor->y3DDrawScale /= 2.0f;
        actor->z3DDrawScale /= 2.0f;

        actor->drawSize /= 2.0f;

        if (actor->drawSize < 0.1f) actor->drawSize = 0.1f;
    }
    std::cout << "[+] Scaled " << AActors.size() << " Zeds down to mini-mode!" << std::endl;
}
```

I then bound them to my `F2` and `F3` keys:
```c++
void Cheats::Start() {

    while (!GetAsyncKeyState(VK_END) & 1) {
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

        if (GetAsyncKeyState(VK_F2) & 1) { // NEW
            ScaleAActorsUp();
        }

        if (GetAsyncKeyState(VK_F3) & 1) { // NEW
            ScaleAActorsDown();
        }

        Sleep(50);
    }
}
```

Running the code:
![scaleupdown](/assets/images/scaleupdown.gif)
