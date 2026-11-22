#pragma once

#include <stdint.h>

enum LightMode : uint8_t { OFF, STEADY_ON, NORMAL_BLINK, SOS_BLINK };
enum DoorState : uint8_t { DOOR_UNKNOWN, DOOR_CLOSED, DOOR_OPEN };

constexpr uint16_t POCKET_LIGHT_MASK = 0x00FF;  // Bits 0-7: P-01..P-08.
constexpr uint16_t MEDIUM_LIGHT_MASK = 0x1E00;  // Bits 9-12: M-01..M-04.
constexpr uint16_t VALID_LIGHT_MASK = POCKET_LIGHT_MASK | MEDIUM_LIGHT_MASK;

constexpr uint8_t lightBit(uint8_t slot) {
  return slot < 8 ? slot : uint8_t(slot + 1);
}

inline bool sosLightOn(uint32_t elapsed) {
  // 3 short, 3 long, 3 short; each pulse has a 150 ms gap.
  const uint16_t widths[9] = {150,150,150,450,450,450,150,150,150};
  uint32_t period = 750;
  for (uint16_t width : widths) period += width + 150;
  uint32_t phase = elapsed % period;
  for (uint16_t width : widths) {
    if (phase < width) return true;
    phase -= width;
    if (phase < 150) return false;
    phase -= 150;
  }
  return false;
}

inline bool lightModeOn(LightMode mode, uint32_t now) {
  return mode == STEADY_ON ||
    (mode == NORMAL_BLINK && now % 1300 < 650) ||
    (mode == SOS_BLINK && sosLightOn(now));
}

inline bool doorAllowsSlot(uint8_t slot, DoorState pocket, DoorState medium) {
  return slot < 8 ? pocket == DOOR_OPEN : medium == DOOR_OPEN;
}

inline uint16_t renderLightMask(const LightMode modes[12], DoorState pocket,
                                DoorState medium, uint32_t now) {
  uint16_t mask = 0;
  for (uint8_t slot = 0; slot < 12; ++slot) {
    if (doorAllowsSlot(slot, pocket, medium) && lightModeOn(modes[slot], now))
      mask |= uint16_t(1) << lightBit(slot);
  }
  return mask & VALID_LIGHT_MASK;
}

static_assert(lightBit(0) == 0 && lightBit(7) == 7,
              "Pocket light mapping must remain bits 0-7");
static_assert(lightBit(8) == 9 && lightBit(11) == 12,
              "Medium light mapping must remain bits 9-12");
static_assert((VALID_LIGHT_MASK & 0xE100) == 0,
              "Unused shift-register bits 8 and 13-15 must remain zero");
