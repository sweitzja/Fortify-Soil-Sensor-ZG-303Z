# Firmware changes vs pvvx/ZigbeeTLc

All changes are in the `BOARD_ZG303Z` build (see `fortify_zg303z.patch`). Summary:

### 0x01443001 — hold a router as parent (End-Device-Timeout / keepalive)
Symptom: the device was only ever observed holding the **coordinator** as parent,
never a router — so anywhere the coordinator is out of range it had no usable
parent, while stock-firmware neighbors happily used a nearby router. On every join
(`BDB_COMMISSION_STA_SUCCESS`) we now explicitly send an **End-Device-Timeout
Request** advertising **both** keepalive methods (`MAC_DATA_POLL_KEEPALIVE_BIT |
END_DEV_TIMEOUT_REQ_KEEPALIVE_BIT`) with the default 256-min timeout, so a router —
especially a finicky Third Reality — registers and keeps us as a child instead of
aging us out. (The NWK layer is a precompiled lib; this is the one exposed lever.)
Field-test fix, not bench-proven.

### 0x01433001 — faster re-homing to a closer repeater
A moved sensor was taking ~an hour (or never) to leave a far parent and rejoin a
nearby repeater. Three knobs:
- `ZDO_NWK_SCAN_ATTEMPTS` 1 → **3** (`zb_config.h`): each rejoin scans 3× so a
  distant repeater's beacon is actually heard, not missed on a single pass.
- `ZDO_MAX_PARENT_THRESHOLD_RETRY` 5 → **3** (`zb_config.h`): declare the parent
  lost after fewer failed polls, so it commits to rejoining sooner.
- Rejoin-failure backoff 10 min → **2 min** (`zb_appCb.c`): retry the rejoin scan
  every 2 minutes instead of every 10 while disconnected.

Trades a little extra radio-on time *while disconnected* for much faster recovery.
Pairs with the adaptive TX power (it boosts to max on parent-loss, then these get
it onto a new parent quickly).


### 0x01423001 — TX-power-current reporting
Added a default reporting config for the current-TX-power attribute (`0x0204`/`0x0124`):
report on any change (≥1 dBm), **3-hour heartbeat** otherwise. So `sensor.*_tx_power_current`
updates on its own (no manual read), mirroring the raw-ADC heartbeat pattern.


### 0x01413001 — adaptive transmit power control (TPC)
pvvx transmits Zigbee at only **+3 dBm** on this board (`USE_BATTERY = BATTERY_2AAA`
→ `RF_POWER_INDEX_P3p01dBm`), ~6–8 dB quieter than stock firmware — which makes the
unit drop off marginal routers that a stock sensor holds. Added a closed-ish loop:

- **Output:** writes `g_zb_txPowerSet`, which the MAC re-applies on every radio
  power-up (`rf_reset`), so the level survives sleep/wake.
- **Input:** the EP1 APS data-confirm status (`MAC_STA_NO_ACK` = parent didn't hear
  us) plus parent-loss / rejoin events.
- **Logic (Stage 1, boost-on-failure):** climb one rung after 2 consecutive missed
  reports; jump straight to max on parent-loss. Ladder ≈ +3/+5/+6/+8/+9/+10 dBm.
- **Configurable** via manufacturer attributes on cluster `0x0204` (exposed by the
  quirk): TX power **mode** (Fixed/Adaptive), **min**/**max**/**fixed** dBm, and a
  read-only **current** dBm sensor (doubles as a placement-quality meter).
  Defaults: Adaptive, min +3, max +10. Persisted to NV.

Files: `app_main.c` (TPC module + confirm cb), `app_main.h` / `app_EpCfg.c`
(config attrs), `zb_appCb.c` (join/parent-loss hooks), `zcl_appCb.c` (write hook).

### Earlier changes (0x01403001)

### `src/version_cfg.h` — private OTA image type
Special-cased the OTA `IMAGE_TYPE` for this board to **`0xF32C`** (instead of the
default `(CHIP_TYPE<<8)|BOARD` = `0x022c`). This isolates the Fortify OTA channel
from pvvx's generic `1141-022c` images, so neither can ever overwrite the other.
See `docs/OTA.md`. (Requires one serial re-flash to adopt — OTA matches on the
*running* firmware's imageType.)

### `src/board_zg303z.h` — device identity
Renamed the ZCL Basic manufacturer/model (and BLE strings) so a flashed unit is
unmistakably custom:

| | Before (pvvx default) | After |
|---|---|---|
| Manufacturer (`0x0004`) | `Sonoff` | **`Fortify`** |
| Model (`0x0005`) | `ZG-303Z-z` | **`Soil-Moisture`** |

### `src/app_main.h` — moisture attribute struct
Added two fields to `zcl_MoistureAttr_t`:
- `u16 raw_adc;`   — raw soil ADC (×4), pre-curve
- `u16 adc_diode;` — diode/Vbat reference ADC (×4)

### `src/app_EpCfg.c` — EP2 cluster table
Initialized the two new fields and registered them on the endpoint-2
Relative Humidity cluster (`0x0405`) as read + reportable:
- `0xF000` → `raw_adc`
- `0xF001` → `adc_diode`

### `src/sensor_rh.c` — publish raw values
In `read_rh_sensor()`, after the moisture % is computed, copy the latest
measurement's raw values into the new attributes:
```c
g_zcl_MoistureAttrs.raw_adc   = sensor_rh.adc_rh;
g_zcl_MoistureAttrs.adc_diode = sensor_rh.adc_d;
```
(`raw_adc` is the un-windowed per-measurement value; pvvx's moisture % keeps its
4-sample moving average.)

### `src/app_main.c` — default reporting
Added default ZCL reporting config for `0xF000`/`0xF001` on EP2:
min = sample interval, **max = 600 s (10-minute heartbeat)**, reportable change = 10 counts.
Tunable per-attribute from ZHA afterward.
