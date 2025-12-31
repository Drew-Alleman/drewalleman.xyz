---
layout: post
title: "Killing Floor Reversing Part 4 - Cleaning the Entity List with AActor Physics"
description: "In the previous post, our entity list contained nearly 5,000 objects. In this post, we’ll build a filter to remove non-player actors and narrow the list down to likely enemy entities.."
date: 2025-12-30 12:38:22 -0700
categories: [game-hacking, hacking, cheats]
tags: [reverse-engineering, hacking, game-hacking]
image: /assets/images/kf_4.png
image_alt: "Killing Floor Cheats"
author: Drew Alleman
last_modified_at: 2025-12-30 12:38:22 -0700
---
# Introduction
In the previous post, our entity list contained nearly 5,000 objects. In this post, we’ll build a filter to remove non-player actors and narrow the list down to likely enemy entities.
# Reversing AActor::SetPhysics
A common concept in video games is an actor’s physics state.
```c++
enum PHYS {
	NONE,
	WALKING,
	RUNNING,
	FALLING,
	SWIMMING,
	FLYING,
	FROZEN,
}
```
If we were able to detect the entity as walking/falling we could easily enumerate if its a valid player entity and not some brush or prop. 

I went to Ghidra and searched for Physics in `Engine.dll` and found the function `SetPhysics`.
![Pasted image 20251230162342](/assets/images/pasted-image-20251230162342.png)

In this function I found the following offset

```c++

void __thiscall
AActor::setPhysics(AActor *this,AActor newPhysics,int param_3,undefined4 param_4,undefined4 param_5,
                  undefined4 param_6)

pPhysics = this[0x74];
this[0x74] = newPhysics;
```

I added it to Cheat Engine, watch the number change from `1`-`2` while im falling.
![physics](/assets/images/physics.gif) <br>

Then when I changed it to `4`, I started flying.
![flying](/assets/images/flying.gif)<br><br>


This definitely is our `Physics` state, lets create an `enum` for it in `enums.h`.
## Enums.h
```c++
#pragma once
enum class PHYS : uint8_t {
    None = 0,
    Walking = 1,
    Falling = 2,
    Unknown = 3,
    Flying = 4,
    Freeze = 5,
};

inline const char* GetPhysicsName(unsigned char physics) {
    switch (physics) {
    case 0: return "PHYS_None";
    case 1: return "PHYS_Walking";
    case 2: return "PHYS_Falling";
    case 3: return "PHYS_UNKNOWN";
    case 4: return "PHYS_FLYING";
    default: return "PHYS_Unknown";
    }
}
```

Now lets add the `Physics` offset to our `AActor` class.
```c++
#pragma once
#include "Enums.h"

class AActor {
public:
    union {

        struct {
            char pad_physics[0x74];
            PHYS physics;
        };

        struct {
            char pad_008[0x480];
            int health;
        };

        struct {
            char pad_level[0x9c];  
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

# Checking if the Entity is Walking or Falling
Lets add some validation to our function to see if that helps reduce the amount of entities we load.

The code below will skip them if they are not walking or falling.
```c++
if (genericActor->physics != PHYS::Walking && genericActor->physics != PHYS::Falling)
```

I also made a mistake in my previous blogpost the entities list is a list of `AActor` objects not a list of `APawns`. We can treat them as `APawn` _only after_ filtering for pawn-like behavior (physics state).

```c++
AActor* genericActor = Level->EntityList[i];
if (!genericActor || genericActor == (AActor*)myPawn) continue;
```
The complete code would be:
```c++
void Cheats::Start() {
    ULevel* Level = myPawn->Level;
    if (!Level) return;

    for (int i = 0; i < Level->currentEntities; i++) {

        AActor* genericActor = Level->EntityList[i];
        if (!genericActor || genericActor == (AActor*)myPawn) continue;

        if (genericActor->physics != PHYS::Walking && genericActor->physics != PHYS::Falling) continue;


        APawn* ent = (APawn*)genericActor;

        if (ent->health <= 0 || ent->health > 10000) continue;

        std::cout << "[+] Found Entity [" << i << "] Health: " << ent->health << std::endl;
    }
}
```
This output is perfect, it returns 20 entries! 
![health](/assets/images/health.gif)

# Enumerating Further
I started writing different values to our physics states and noticed the following behavior:
- Writing a `3` with Cheat Engine (even with the lock mechanic) is immediately written back to `1`.

Writing a `5` or `0` freezes the model, until 1/2 is written back.
![freeze](/assets/images/freeze.gif)
I added a line to print out any physics state that I didn't have in my `enum`, but it was just garbage data.
```
[+] Ent: 6767 has 1056964608 health.
♠
[+] Ent: 6768 has 1056964608 health.
♠
[+] Ent: 6770 has 1056964608 health.
♠
[+] Ent: 6771 has 1056964608 health.
♠
```

Updated `Enum.h`
```c++
enum PHYS {
    NONE,
    WALKING,
    FALLING,
    UNKNOWN,
    FLYING,
    FREEZE,
};

inline const char* GetPhysicsName(unsigned char physics) {
    switch (physics) {
    case 0: return "PHYS_None";
    case 1: return "PHYS_Walking";
    case 2: return "PHYS_Falling";
    case 3: return "PHYS_UNKNOWN";
    case 4: return "PHYS_FLYING";
    case 5: return "PHYS_FREEZE";
    default: return "PHYS_Unknown";
    }
}

```
