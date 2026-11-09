# SAULI cabinet hardware map

The active cabinet has 12 positions: P-01–P-08 for pocket-size items and M-01–M-04 for medium-size items. P-09, P-10, and M-05 remain for history or unresolved items and are not assigned to new deposits.

The ESP32-S3 defaults to maintained 3.3 V presence switches (HIGH=present, LOW=absent). Switch GPIOs: P-01=40, P-02=18, P-03=17, P-04=15, P-05=7, P-06=6, P-07=5, P-08=9, M-01=14, M-02=13, M-03=12, M-04=11. The 74HC595 DATA/CLOCK/LATCH GPIOs are 1/2/21. IC1 B1–B8 map to P-01–P-08 (bits 0–7); IC2 B2–B5 map to M-01–M-04 (bits 9–12). IC2 B1/bit 8 is unused. HX711 code is retained as a separate compile-time mode and must not run on the same pins as switches.

The Pi BCM map is main light 24, buzzer 17, medium solenoid 23, pocket solenoid 27, medium door reed 8, pocket door reed 7, pocket light bank gate 16, medium light bank gate 20, and UART TX/RX 14/15. GPIO3 is reserved for the OS power-button shutdown overlay. Earlier wiring plans used BCM24 for the medium solenoid and BCM17 for the main light; check and correct real wiring before enabling outputs. No two consumers may own one GPIO. The default `hardware.example.json` disables all output actuation.

See [the installation guide](../instruction.md) for wiring checks, migration order, Pi installation, ESP flashing, and supervised tests. A switch reports physical presence, not object identity or proof that a door is locked. Restart snapshots are reconciliation data, not transaction completion evidence. Physical door-closed compartment-light cutoff and HX711 calibration are not yet integrated.
