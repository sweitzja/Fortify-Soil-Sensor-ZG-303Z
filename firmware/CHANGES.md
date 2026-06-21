# Firmware changes vs pvvx/ZigbeeTLc

All changes are in the `BOARD_ZG303Z` build, across 6 files
(see `fortify_zg303z.patch`). Summary:

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
