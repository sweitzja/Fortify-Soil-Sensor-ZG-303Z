# How the Fortify Soil Sensor (ZG-303Z) works

The part pvvx's docs don't explain: what every entity is, how the soil ADC actually
works, and exactly where the averaging/windowing happens. Line references are to
[pvvx/ZigbeeTLc](https://github.com/pvvx/ZigbeeTLc) source.

---

## 1. Hardware

| Block | Detail |
|---|---|
| MCU / radio | Telink **TLSR825x** (TLSR8250 on the Sonoff "-z"; TLSR8258 elsewhere), Zigbee 3.0 |
| Air temp/humidity | a **digital I²C sensor** (AHT20 / CHT8215 / SHT3x/4x — firmware auto-detects), on `PC0/PC1` |
| Soil moisture | a **capacitive** probe driven by a PWM oscillator + diode/RC network, read by the on-chip ADC |
| Soil drive / sense | `PB4` = PWM excitation, `PB5` = ADC input (RHI). Network ≈ R 7.5 kΩ, C 4.7 nF, BAV99 diode |
| Power | 2×AAA; battery measured on an internal ADC channel |

Two **endpoints** are exposed: **EP1** = air temp/humidity/battery/config, **EP2** = soil.

---

## 2. Entities

| HA entity | Zigbee source | Unit | Notes |
|---|---|---|---|
| **Temperature** | EP1 Temperature Meas. `0x0402` | °C | from the digital T/H chip; not firmware-averaged |
| **Air Humidity** | EP1 Relative Humidity `0x0405` | % | air RH from the digital chip |
| **Soil Moisture** (%) | EP2 Relative Humidity `0x0405` measuredValue | % | pvvx's curve output — **4-sample moving average** |
| **Soil raw ADC** | EP2 `0xF000` *(custom)* | counts | raw capacitive reading, **not** moving-averaged |
| **Soil ADC reference** | EP2 `0xF001` *(custom)* | counts | diode/Vbat reference — divide raw by this |
| **Battery** | EP1 Power Cfg `0x0001` % remaining | % | |
| Battery voltage | EP1 Power Cfg battery_voltage | V | ADC on the Vbat channel |
| **Temperature offset** | EP1 `0x0204` / `0x0100` (rw) | °C | calibration trim, ±327.67, 0.01 step |
| **Humidity offset** | EP1 `0x0204` / `0x0101` (rw) | % | calibration trim |
| **Measurement interval** | EP1 `0x0204` / `0x0107` (rw) | s | **default 20**, range 3–255 |
| RSSI / LQI | diagnostic | dBm / — | link quality |
| Identify | EP1 Identify `0x0003` | — | button |
| Firmware | EP1 OTA `0x0019` | — | Zigbee OTA |
| Soil Moisture **Calibrated** | HA template (this repo) | % | your own curve from raw ADC |

> `Soil raw ADC` and `Soil ADC reference` are the two attributes this repo adds.
> Both are reported with a 10-minute heartbeat + small change-delta (tunable in ZHA).

---

## 3. How the soil ADC works

### 3a. One ADC read = a trimmed mean of 8 samples

`get_adc_mv()` ([patch_zb_sdk/adc_drv.c:113](https://github.com/pvvx/ZigbeeTLc/blob/master/src/patch_zb_sdk/adc_drv.c)):

- ADC is **14-bit**, internal **1.2 V** reference, ⅛ input pre-scaler, ~96 kS/s.
- It grabs **8 samples** (`ADC_BUF_COUNT`) into a FIFO, **insertion-sorts them as they arrive**, then sums the **middle four** (indices 2–5):

  ```c
  adc_average = adc_sample[2] + adc_sample[3] + adc_sample[4] + adc_sample[5];
  ```

  That's a **trimmed mean**: it throws away the 2 lowest and 2 highest samples (outlier rejection) and sums the middle 4. So **every ADC value is already de-noised within a single read.**

- Because it *sums* (not averages) 4 samples, the result is **≈ 4× a single ADC count** — this is the "×4 scale." `raw_adc = 5643` ⇒ underlying count ≈ 1411.
  **You never need to undo the ×4** — calibrate on the *ratio* (next section), which cancels it.

`get_adc_mv(1)` returns this raw sum (used for soil + reference). `get_adc_mv(0)` converts to millivolts (`× 1175 >> 12`) and is used for **battery voltage**.

### 3b. Two-phase read = battery/diode compensation (NOT temperature)

`get_rh()` ([sensor_rh.c:50](https://github.com/pvvx/ZigbeeTLc/blob/master/src/sensor_rh.c)) measures the probe twice:

1. **Excited** — PWM (~1.33 MHz) drives the network; the soil's capacitance sets how the diode/RC charges. ADC → **`adc_rh`** (your *Soil raw ADC*). **Wetter soil ⇒ higher capacitance ⇒ lower `adc_rh`.**
2. **Reference** — PWM pin is held DC-high; the cap charges to ≈ (Vbat − V_diode). ADC → **`adc_d`** (your *Soil ADC reference*).

The reference tracks **battery voltage and the diode drop**, so dividing cancels both:

```
use   ratio = adc_rh / adc_d   as your moisture signal.
```

⚠️ It does **not** cancel **temperature** — the soil/water dielectric, the diode, and the RC all drift with temp and nothing corrects for it. That's why outdoor units benefit from a temp term in HA (the temperature entity is exposed for exactly this).

### 3c. pvvx's built-in curve

```
moisture% = k / (adc_rh · d/adc_d − z) − 100%     // k=3100000, z=820, d=8810
```
clamped to 0–100. It's a reciprocal curve with constants tuned to one reference probe/PCB at ~3.0 V. Good enough out of the box, but **not** matched to your probe and **not** temp-compensated — hence this repo exposes the raw inputs so you can fit your own.

---

## 4. Averaging / windowing — all of it

There are up to **three** layers. Knowing which value has which matters a lot for calibration:

| Layer | Where | Applies to | Effect |
|---|---|---|---|
| **1. Trimmed mean (8→4)** | `get_adc_mv()` per read | **every** ADC value (soil raw, reference, battery) | drops 2 low + 2 high of 8 samples, sums middle 4 — outlier rejection within one measurement |
| **2. Moving average (4-deep)** | `read_rh_sensor()`, `USE_AVERAGE_RH_SHL=2` | **Soil Moisture %** only | smooths the *computed %* over ~4 measurements (running average; exponential after warm-up) |
| **3. (none)** | — | **Temperature, Air Humidity** | the digital T/H chip does its own filtering; firmware adds none |

Key consequence:

- **`Soil raw ADC` / `Soil ADC reference` have layer 1 only** — responsive (updates every measurement), lightly de-noised, **not** smoothed across measurements. Ideal for calibration.
- **`Soil Moisture %` has layers 1 + 2** — it lags the raw value by a few samples. So don't expect raw and % to move in lockstep.
- If you want the raw smoothed, do it in HA (a `filter` or `statistics` sensor) — more flexible than the fixed firmware window.

The layer-2 math (`USE_AVERAGE_RH_SHL = n`, window = 2ⁿ = 4):
```c
summ += new_value;
if (++cnt >= 4) { out = summ >> 2; summ -= out; cnt--; }   // steady state: ~4-deep exponential
else            { out = summ / cnt; }                       // warm-up: simple running mean
```

---

## 5. Sampling & reporting timing

- **Sample interval** — how often *every* sensor (incl. soil) is measured: `measureInterval`, default **20 s** (`READ_SENSOR_TIMER_SEC`), settable 3–255 s via the **Measurement interval** entity ([app_main.c:325](https://github.com/pvvx/ZigbeeTLc/blob/master/src/app_main.c)).
- **Report rate** — standard ZCL attribute reporting (`bdb_defaultReportingCfg`), independent of sampling:
  - *min interval* — never report faster than this (= sample interval)
  - *max interval (heartbeat)* — report at least this often even if unchanged. Defaults: **soil % = 300 s**, **raw ADC / reference = 600 s** (this repo). Use it for liveness/offline detection.
  - *reportable change (delta)* — report early if the value moves by this much. Defaults: soil % = 0.50 %RH, raw/ref = 10 counts.
  - All three are **reconfigurable per-attribute from ZHA** at runtime — no reflash.

So a value reaches HA when **either** it changed by ≥ delta (no sooner than *min*) **or** *max* seconds elapsed.

---

## 6. Calibration recipe

1. Pick the signal: **`ratio = Soil raw ADC / Soil ADC reference`** (battery-compensated, scale-free).
2. **Dry** (in air): record ratio → 0 %. **Wet** (in water/saturated): record ratio → 100 %. (ratio *falls* as it wets.)
3. Map linearly: `% = (dry − ratio)/(dry − wet) × 100`, clamp 0–100. See `homeassistant/soil_moisture_calibrated.yaml`.
4. Optional precision:
   - **Non-linearity** — capacitive probes bow mid-range; add a midpoint and fit a polynomial.
   - **Temperature** — record a dry reading at a very different temp to get a coefficient, then `ratio_corr = ratio − tc·(temp − temp_ref)` before mapping.
   - **Smoothing** — wrap the output in a `statistics`/`filter` sensor if noisy.

---

## Quick reference

```
raw_adc  = 4 × trimmed-mean ADC count, PWM-excited   (wetter → lower)
adc_d    = 4 × trimmed-mean ADC count, DC reference  (≈ tracks Vbat)
ratio    = raw_adc / adc_d           ← calibrate on THIS
soil %   = pvvx curve, then 4-sample moving-averaged
temp/RH  = digital chip, no firmware averaging
sample   = every 20 s (default), 3–255 s
report   = on Δ (≥delta) or heartbeat (≤max), tunable in ZHA
```
