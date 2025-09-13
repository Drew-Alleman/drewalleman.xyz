---
layout: post
title: "Root Shell Access on NETGEAR AC1000 R6080 through UART Debug Interface"
description: "A walkthrough on how I enumerated each of the UART pins and gained a root shell to the router."
date: 2025-09-13 9:35:00 -0700
categories: [hacking, hardware]
tags: [uart, firmware, hacking]
image: /assets/images/uart_preview.png
image_alt: "Root Shell Access on NETGEAR AC1000 R6080 through UART Debug Interface"
author: Drew Alleman
last_modified_at: 2025-09-13 9:35:00 -0700
---
I decided to check out my local Goodwill for old routers that I might be able to get a shell on. By looking at the device’s FCC ID, I was able to review the internal photos and identify exposed UART pins.

https://fcc.report/FCC-ID/PY316400359/3312277.pdf

![Internal](/assets/images/internal_ac1000.png)

With the device set up in the lab, the next step is to enumerate each pin and align it with the corresponding pin on the adapter.

## 1. Find the Ground Pin
Power off the device and use your multimeter to check each pin for ground. Make sure your meter is set to the same configuration as mine.

![multimeter](/assets/images/multimeter_ground.png)

On my device, the ground pin was the furthest left from the power button. If you’ve set everything correctly, you should hear a beep when testing. Ensure the black probe is connected to ground.

![finding ground](/assets/images/finding_ground.png)

## 2. Find the RX Pin
The RX pin is the receive line of the UART interface. It accepts incoming data from the connected device. RX is usually easy to identify because it should remain at 0V.

Set your multimeter to **20V DC mode**.  

![20v DC](/assets/images/20V_DC.png)

With the device powered on, probe each pin while monitoring for a constant value of 0V. On my device, this was the pin marked with an arrow.

![Finding RX](/assets/images/finding_rx.png)

## 3. Identify the Power Pin (VCC)
The VCC pin should hold a steady **3.3V**. This is easy to confirm—on my device, it was labeled **JP1**.

![Finding the Power Pin](/assets/images/finding_vcc.png)

## 4. Identify the TX Pin
The TX pin is very noisy during startup. To locate it, reboot the device while monitoring each pin’s voltage—the one with the most frequent spikes and dips is TX. On my device, it was the second pin from the left, next to the power cable.

![Finding TX](/assets/images/finding_tx.png)

![Finding TX P2](/assets/images/finding_tx_p2.png)

## 5. Connect the Adapter
Once you’ve identified all pins, map them to the USB-to-UART adapter. **Do not connect VCC.**

Connections:
- Board RX → Adapter TX  
- Board TX → Adapter RX  
- Ground → Ground  

For reference, my wiring was:  
- **Orange** = Ground  
- **Yellow** = Router TX  
- **Blue** = Router RX  

![Pin Headers](/assets/images/pin_headers.png)


Then, on the adapter:  

![Adapter](/assets/images/pin_adapter.png)

Adapter TX → Router RX  
Adapter RX → Router TX  
Ground → Ground  

## 6. Open a UART Session
Use the `screen` utility to start a UART session. If successful, you’ll see the boot log and eventually a root shell prompt.

```bash
$ sudo screen -L /dev/ttyUSB0 57600
```

Now reboot the router and you should start to see a bunch of boot logs...
![Boot Log](/assets/images/boot_logs.png)


Once the boot sequence is completed we are given a root shell

![Router Shell](/assets/images/router_root_shell.png)

I’m currently focused on enumerating the filesystem and firmware, and I plan to publish blog posts to share my findings.