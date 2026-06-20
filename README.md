# Fortify Soil Sensor (ZG-303Z)

Custom Zigbee firmware + Home Assistant integration for the **ZG-303Z** soil-moisture / temperature / humidity sensor (sold as **Sonoff ZG-303Z-z** and **HOBEIAN ZG-303Z**, a Telink TLSR825x device).

This is a thin set of modifications on top of **[pvvx/ZigbeeTLc](https://github.com/pvvx/ZigbeeTLc)** that:

1. **Exposes the raw soil-moisture ADC** (and the diode/battery reference) as Zigbee attributes, so you can build your **own calibration curve** in Home Assistant instead of relying on the firmware's fixed curve.
2. **Rebrands the device** to manufacturer **`Fortify`**, model **`Soil-Moisture`** — so a flashed unit is instantly distinguishable from stock (stock reports `HOBEIAN ZG-303Z`; pvvx's default keeps `Sonoff ZG-303Z-z`, which is easy to mistake for stock).
3. Ships a **ZHA quirk** that surfaces the raw values plus pvvx's config controls (temperature/humidity offset, measurement interval).
4. Ships a **Home Assistant template sensor** that turns the raw ADC into a calibrated, battery-compensated moisture %.

> Everything here is licensed MIT, same as pvvx/ZigbeeTLc. All firmware credit goes to **pvvx**; this repo only adds the soil-ADC exposure, the identity change, and the HA glue.

---

## Why expose raw ADC?

pvvx's firmware converts the capacitive reading to a moisture % with a fixed reciprocal curve calibrated to one probe/PCB at ~3.0 V:

```
moisture% = k / (adc_rh · d/adc_d − z)      // k=3100000, z=820, d=8810
```

`adc_d` is a diode/Vbat reference that cancels **battery-voltage** drift — but the curve is **not** calibrated to your probe and does **not** temperature-compensate. Exposing the raw inputs lets you fit your own curve (and optional temp correction) in HA.

- `raw_adc` (attr **0xF000**) — raw soil ADC, pre-curve (median-filtered per sample, ×4 scale)
- `adc_diode` (attr **0xF001**) — diode/Vbat reference (×4 scale)
- Use the **ratio `raw_adc / adc_diode`** as your calibration input — the ×4 scale and battery drift both cancel.

Direction: **wetter → lower `raw_adc`** (ratio falls as moisture rises).

---

## Repo layout

```
firmware/
  fortify_zg303z.patch     # the changes vs pvvx/ZigbeeTLc (git apply)
  src/                     # the 5 modified source files (drop-in replacements)
  CHANGES.md               # human-readable description of every change
quirk/
  zigbeetlc_zg303z.py      # ZHA v2 quirk (Fortify/Soil-Moisture)
homeassistant/
  soil_moisture_calibrated.yaml   # calibrated template sensor + notes
```

---

## 1. Build the firmware

Built against pvvx/ZigbeeTLc with the bundled Telink `tc32` toolchain. On a Linux box (or WSL — no root needed):

```bash
git clone --depth 1 https://github.com/pvvx/ZigbeeTLc.git
cd ZigbeeTLc
# unpack the bundled toolchain + SDK without `unzip`:
tar -xjf tools/linux/tc32_gcc_v2.0.tar.bz2 -C tools/linux/
python3 -m zipfile -e tools/SDK_z.zip  SDK_z
python3 -m zipfile -e tools/SDK_bz.zip SDK_bz

# apply this repo's changes:
git apply /path/to/firmware/fortify_zg303z.patch
#   ...or just copy firmware/src/*.{c,h} over src/

make -j PYTHON=python3 PROJECT_NAME=ZG303Z POJECT_DEF="-DBOARD=BOARD_ZG303Z" ZNAME="Fortify:Soil-Moisture"
# -> bin/ZG303Z.bin
```

## 2. Flash it

Serial (single-wire SWS) via pvvx's [USB-COM flasher](https://pvvx.github.io/ATC_MiThermometer/USBCOMFlashTx.html) — GND→GND, 3V3→Vbat, TX→SWS (pin 3 on the 5-pin header). Write `bin/ZG303Z.bin`. After flashing, the device joins as **Fortify Soil-Moisture**.

> The ZG-303Z-z uses a TLSR8250; pvvx's UART-bootloader tool (`TlsrComProg825x`) doesn't support it, but the raw-SWS `USBCOMFlashTx` web flasher does.

## 3. Install the ZHA quirk

```yaml
# configuration.yaml
zha:
  custom_quirks_path: /config/zha_quirks
```

Drop `quirk/zigbeetlc_zg303z.py` into `/config/zha_quirks/`, restart HA, then **Reconfigure** the device. You'll get: `Soil raw ADC`, `Soil ADC reference`, `Temperature offset`, `Humidity offset`, `Measurement interval`, plus temp / air-humidity / soil-moisture / battery.

## 4. Calibrate in Home Assistant

See `homeassistant/soil_moisture_calibrated.yaml`. In short:

1. **Dry (in air):** note `raw_adc / adc_diode` → that's your 0% ratio.
2. **Wet (in water / saturated soil):** note the ratio → 100%.
3. The template does a 2-point linear fit on the ratio. Add a midpoint for a polynomial fit, and/or a temperature term, if you need precision (the device's temperature sensor is exposed for this).

---

## Reporting / sampling knobs

- **Sample interval** — how often the device measures (incl. soil): the `Measurement interval` number entity (3–255 s).
- **Report rate / heartbeat / delta** — standard ZCL reporting config, tunable per-attribute from ZHA. The raw values default to a **10-minute heartbeat** (report at least every 10 min even if unchanged, for liveness) plus a small change-delta.
- pvvx's moisture-% output is smoothed by a 4-sample moving average; the **raw ADC is not** (responsive — smooth it yourself in HA if desired).

## Credits

- **[pvvx/ZigbeeTLc](https://github.com/pvvx/ZigbeeTLc)** — the firmware this builds on (MIT).
- Telink TLSR825x SDK.

## License

MIT — see [LICENSE](LICENSE).
