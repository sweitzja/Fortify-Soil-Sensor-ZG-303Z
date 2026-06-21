# OTA update channel

This repo doubles as a **self-hosted OTA index** — the same mechanism Sonoff/IKEA/etc.
use, but pointed at your firmware. Once set up, new releases reach your devices
**over Zigbee** (no more serial flashing), and HA's `update.<device>_firmware`
entity tells you when one is available.

## How it works (recap)

Zigbee OTA matches on three numbers from the device's OTA cluster (`0x0019`):
**`manufacturerCode` + `imageType` + `fileVersion`**. ZHA offers an image when a
configured **provider** has one with the same `manufacturerCode/imageType` and a
**higher** `fileVersion`.

This channel uses:

| Field | Value | Why |
|---|---|---|
| `manufacturerCode` | `0x1141` (Telink) | unchanged from the stock SDK |
| `imageType` | **`0xF32C`** | **private** — isolates Fortify from pvvx's generic `1141-022c`, so a community/pvvx ZG-303Z image can never overwrite your custom firmware (and vice-versa) |
| `fileVersion` | `0x01393001` | bump this for every release |

The `imageType` is set in `firmware/src/version_cfg.h` (special-cased for `BOARD_ZG303Z`).

> ⚠️ **One-time adoption flash.** Firmware built *before* this isolation reports
> `imageType 0x022c`; OTA matches on the *running* firmware's imageType, so the
> `0xF32C` channel can't reach a `0x022c` device. **Serial-flash this build once**
> (`ZG303Z_fortify.bin`) to move the device onto the `0xF32C` channel. After that,
> every future release goes out by OTA.

## Enable it in Home Assistant (ZHA)

Two options — pick one. **Either way, treat the restart carefully on a network/PoE
coordinator (be ready to power-cycle it).**

### A. Self-updating, remote (most "Sonoff-like")
ZHA fetches this repo's `index.json` over the internet, so pushing a new release is
all it takes:
```yaml
zha:
  zigpy_config:
    ota:
      extra_providers:
        - type: z2m
          url: https://raw.githubusercontent.com/sweitzja/Fortify-Soil-Sensor-ZG-303Z/main/ota/index.json
```

### B. Local, no internet fetch (gentler on a flaky coordinator)
Drop the `.zigbee` into a local folder; ZHA reads its header directly — no index needed:
```yaml
zha:
  zigpy_config:
    ota:
      extra_providers:
        - type: advanced
          warning: "I understand I can *destroy* my devices by enabling OTA updates from files. I am consciously using this at my own risk."
          path: /config/zigpy_ota
```
…then copy `ota/*.zigbee` into `/config/zigpy_ota/`.

After a restart, the device's **Firmware** entity shows the update → **Install** →
~10 min over Zigbee. Automate a notification off `update.<device>_firmware` being `on`.

## Cutting a new release

1. Bump the version in `firmware/src/version_cfg.h` (raise `APP_BUILD` / `APP_RELEASE`
   so `fileVersion` increases).
2. Rebuild (`make … PROJECT_NAME=ZG303Z POJECT_DEF="-DBOARD=BOARD_ZG303Z"`).
3. Copy the new `bin/1141-f32c-*-ZG303Z.zigbee` into `ota/` (replace the old one).
4. Regenerate `ota/index.json` with the new `fileVersion`, `fileSize`, `sha512`
   (parse them from the `.zigbee` ZCL OTA header — magic `0x0BEEF11E`, then
   manufacturerCode@+10, imageType@+12, fileVersion@+14).
5. Commit + push.

Provider **A** picks it up automatically on ZHA's next index refresh; provider **B**
needs the new `.zigbee` copied into `/config/zigpy_ota/`.

## Notes

- The `.zigbee` IS a standard ZCL OTA image — usable by ZHA *and* Zigbee2MQTT.
- Keep only the **latest** image in `ota/` (or list all versions in `index.json`);
  ZHA always offers the highest `fileVersion` that matches.
- Serial flashing still works as a fallback / for first-time conversion.
