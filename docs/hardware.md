# SAULI cabinet hardware map

The finalized cabinet has 12 positions: P-01 through P-08 for pocket-size items and M-01 through M-04 for medium-size items. The web kiosk and API use those codes for new assignments. Three older database rows (P-09, P-10, M-05) are retained only for historical or unresolved items.

The Raspberry Pi controller and ESP32 weight-sensor directories currently contain no per-position pin or channel map. Before connecting physical hardware, confirm each active position's HX711 channel, ESP32-S3 input, 74HC595 output or indicator, and door/lock association against the wiring plan. No GPIO or channel assignments are implied by a position code.
