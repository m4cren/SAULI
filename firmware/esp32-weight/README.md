# SAULI ESP32-S3 weight controller

One ESP32-S3 reads the 12 HX711 DOUT pins with a **single shared GPIO47 clock**. `src/main.cpp` lists every DOUT pin and slot. The Arduino/PlatformIO target is an ESP32-S3 N16R8 (16 MB flash, 8 MB octal PSRAM); confirm the board markings and USB port before flashing.

```bash
python3 -m pip install --user platformio
cd firmware/esp32-weight
python3 -m platformio run
python3 -m platformio device list
python3 -m platformio run -t upload --upload-port /dev/ttyACM0
python3 -m platformio device monitor --port /dev/ttyACM0 --baud 115200
```

Change the port to the one actually listed. Native USB CDC is for human debug. `Serial1` is the Pi protocol at 115200 8N1: ESP RX GPIO44 receives Pi BCM14 TX; ESP TX GPIO43 sends to Pi BCM15 RX. Share ground and use 3.3 V TTL.

UART frames are newline-delimited JSON, version `v:1`, max 4096 bytes. The ESP sends `hello` and 1-second `telemetry`; it answers `ping` with `pong` and `status` with telemetry. Pi-to-ESP `command` accepts `tare` or `calibrate` with a slot code and unique ID. Calibration also needs `reference_grams` from a known test weight. A duplicate ID is acknowledged without reapplying it. All sensor channels publish signed 24-bit raw readings, readiness/fault, and grams/presence only after calibration. Missing sensors report `not_ready`; a fault does not count as a removal. The last eight command IDs are retained in RAM only, so **do not replay commands after reboot**. The Pi does not currently forward remote calibration commands.

The supplied raster schematic shows DATA GPIO1, CLOCK GPIO2, LATCH GPIO21, but does not prove the 74HC595 Q-bit-to-slot wiring or its active polarity. `LIGHT_BITS` is deliberately all `-1`; `set_light` returns `light_map_unverified`, and the firmware does not clock a guessed light pattern. Before adding a walking-light test, check the source schematic/netlist or trace each output, record the mapping and polarity, and test with the bank gates disconnected. The same caution applies to Pi output polarity. No physical hardware has been verified by the repository tests.

The shared-clock reader clocks all ready channels in one 25-pulse train (24 data bits plus channel A gain 128). It keeps the clock low between reads and marks unready channels invalid. If modules on the common clock have different conversion phases, an unready channel may need another conversion to synchronize; inspect raw/ready status during bring-up. Start with one HX711, then add all twelve. Do not trust the presence threshold until each load cell has been tared and calibrated with a known weight.
