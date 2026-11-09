#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <math.h>

#ifndef SAULI_VERBOSE_DIAGNOSTICS
#define SAULI_VERBOSE_DIAGNOSTICS 1
#endif

// ESP32-S3 GPIO numbers. This board is one controller for 8 pocket and 4 medium slots.
constexpr uint8_t DATA_PIN = 1, CLOCK_PIN = 2, LATCH_PIN = 21, HX_CLOCK_PIN = 47;
constexpr uint8_t UART_RX = 44, UART_TX = 43;
constexpr uint32_t BAUD = 115200, TELEMETRY_MS = 1000, SENSOR_TIMEOUT_MS = 3000;
constexpr uint16_t MAX_LINE = 4096;
constexpr float PRESENCE_ON_G = 30.0f, PRESENCE_OFF_G = 15.0f;
constexpr uint8_t STABLE_SAMPLES = 3;
constexpr int8_t LIGHT_BITS[12] = {0,1,2,3,4,5,6,7,9,10,11,12};
constexpr uint32_t DEBOUNCE_MS = 60;
constexpr uint32_t GUIDANCE_TIMEOUT_MS = 15000;
#ifdef SAULI_SENSOR_MODE_HX711
constexpr bool SWITCH_MODE = false;
#else
constexpr bool SWITCH_MODE = true;
#endif
enum LightMode : uint8_t { OFF, STEADY_ON, NORMAL_BLINK, SOS_BLINK };
const char *const MODE_NAMES[] = {"OFF", "STEADY_ON", "NORMAL_BLINK", "SOS_BLINK"};
const char *const CODES[12] = {"P-01","P-02","P-03","P-04","P-05","P-06","P-07","P-08",
                               "M-01","M-02","M-03","M-04"};
const uint8_t DOUT_PINS[12] = {40,18,17,15,7,6,5,9,14,13,12,11};
const bool ENABLED[12] = {true,true,true,true,true,true,true,true,true,true,true,true};

struct Sensor {
  bool ready = false, calibrated = false, present = false;
  bool hasRaw = false;
  int32_t raw = 0, tare = 0;
  float countsPerGram = NAN, filtered = NAN;
  uint8_t pending = 0;
  uint32_t lastReady = 0;
  const char *fault = "waiting";
};
Sensor sensors[12];
Preferences prefs;
bool lightCommands[12] = {};
LightMode lightModes[12] = {};
bool rawSwitch[12] = {}, stableSwitch[12] = {};
uint32_t rawChangedAt[12] = {};
uint16_t lastLightMask = 0xffff;
uint32_t lastMaskLogAt = 0;
uint32_t lastGuidanceAt = 0;
bool guidanceArmed = false;
uint32_t bootId = 0, eventSeq = 0;
char lineBuffer[MAX_LINE + 1];
uint16_t lineLength = 0;
bool discardLine = false;
uint32_t seqNo = 0, lastTelemetry = 0;
String recentIds[8];
uint8_t recentIndex = 0;
struct PendingEvent {
  bool active = false, present = false;
  uint8_t slot = 0;
  uint32_t sequence = 0, lastSent = 0;
  String id, kind;
};
PendingEvent pendingEvents[48];

void sendDoc(JsonDocument &doc) {
  serializeJson(doc, Serial1);
  Serial1.write('\n');
}

void sendReply(const char *type, const String &id, const char *code) {
  JsonDocument doc;
  doc["v"] = 1;
  doc["type"] = type;
  doc["id"] = id;
  doc["code"] = code;
  doc["seq"] = ++seqNo;
  doc["uptime_ms"] = millis();
  sendDoc(doc);
}

void shiftAllOff() {
  digitalWrite(LATCH_PIN, LOW);
  shiftOut(DATA_PIN, CLOCK_PIN, MSBFIRST, 0); // IC2 (far register) first.
  shiftOut(DATA_PIN, CLOCK_PIN, MSBFIRST, 0); // IC1 second.
  digitalWrite(LATCH_PIN, HIGH);
  lastLightMask = 0;
}

LightMode parseMode(const char *name) {
  if (!name) return OFF;
  for (int i = 0; i < 4; ++i) if (strcmp(name, MODE_NAMES[i]) == 0) return LightMode(i);
  return OFF;
}

bool sosOn(uint32_t elapsed) {
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

void updateLights() {
  uint32_t now = millis();
  uint16_t mask = 0;
  for (int i = 0; i < 12; ++i) {
    bool on = lightModes[i] == STEADY_ON ||
      (lightModes[i] == NORMAL_BLINK && now % 1300 < 650) ||
      (lightModes[i] == SOS_BLINK && sosOn(now));
    if (on) mask |= uint16_t(1) << LIGHT_BITS[i];
  }
  if (mask == lastLightMask) return;
  digitalWrite(LATCH_PIN, LOW);
  shiftOut(DATA_PIN, CLOCK_PIN, MSBFIRST, uint8_t(mask >> 8));
  shiftOut(DATA_PIN, CLOCK_PIN, MSBFIRST, uint8_t(mask));
  digitalWrite(LATCH_PIN, HIGH);
  lastLightMask = mask;
#if SAULI_VERBOSE_DIAGNOSTICS
  // Limit animation logging so Serial Monitor cannot slow the sensor loop.
  if (now - lastMaskLogAt >= 1000) {
    Serial.printf("[LED] output mask: 0x%04X\n", mask);
    lastMaskLogAt = now;
  }
#endif
}

void publishPresence(int i, const char *kind) {
  int freeIndex = -1;
  for (int n = 0; n < 48; ++n) if (!pendingEvents[n].active) { freeIndex = n; break; }
  if (freeIndex < 0) {
    Serial.println("SAULI presence queue full; event not sent");
    return;
  }
  PendingEvent &event = pendingEvents[freeIndex];
  event.active = true; event.slot = i; event.present = sensors[i].present;
  event.sequence = ++eventSeq; event.id = String(bootId, HEX) + "-" + String(eventSeq);
  event.kind = kind; event.lastSent = 0;
#if SAULI_VERBOSE_DIAGNOSTICS
  Serial.printf("[UART] queued %s %s present=%u seq=%lu\n", kind, CODES[i],
                event.present, static_cast<unsigned long>(event.sequence));
#endif
}

void sendPendingPresence() {
  uint32_t now = millis();
  PendingEvent *next = nullptr;
  for (PendingEvent &event : pendingEvents)
    if (event.active && (!next || event.sequence < next->sequence)) next = &event;
  if (!next || (next->lastSent && now - next->lastSent < 500)) return;
  PendingEvent &event = *next;
  JsonDocument doc;
  doc["v"] = 1; doc["type"] = "event"; doc["kind"] = event.kind;
  doc["event_id"] = event.id;
  doc["boot_id"] = String(bootId, HEX); doc["seq"] = event.sequence;
  doc["slot"] = CODES[event.slot]; doc["present"] = event.present;
  doc["source"] = SWITCH_MODE ? "switch" : "hx711";
  doc["uptime_ms"] = millis(); sendDoc(doc);
  event.lastSent = now;
}

void scanSwitches() {
  uint32_t now = millis();
  for (int i = 0; i < 12; ++i) {
    bool raw = digitalRead(DOUT_PINS[i]) == HIGH;
    if (raw != rawSwitch[i]) {
#if SAULI_VERBOSE_DIAGNOSTICS
      Serial.printf("[SENSOR] %s GPIO%u: %s -> %s\n", CODES[i], DOUT_PINS[i],
                    rawSwitch[i] ? "HIGH" : "LOW", raw ? "HIGH" : "LOW");
#endif
      rawSwitch[i] = raw; rawChangedAt[i] = now;
    }
    if (raw != stableSwitch[i] && now - rawChangedAt[i] >= DEBOUNCE_MS) {
      stableSwitch[i] = raw; sensors[i].present = raw;
#if SAULI_VERBOSE_DIAGNOSTICS
      Serial.printf("[SENSOR] %s debounced: %s\n", CODES[i], raw ? "PRESENT" : "EMPTY");
#endif
      publishPresence(i, raw ? "ITEM_PRESENT" : "ITEM_REMOVED");
    }
  }
}

void loadCalibration() {
  prefs.begin("sauli-hx711", false);
  for (int i = 0; i < 12; ++i) {
    String t = "t" + String(i), s = "s" + String(i);
    sensors[i].tare = prefs.getInt(t.c_str(), 0);
    sensors[i].countsPerGram = prefs.getFloat(s.c_str(), NAN);
    sensors[i].calibrated = isfinite(sensors[i].countsPerGram) && fabsf(sensors[i].countsPerGram) >= 1.0f;
  }
}

void sampleSharedClock() {
  uint16_t participating = 0;
  uint32_t values[12] = {};
  for (int i = 0; i < 12; ++i) {
    if (ENABLED[i] && digitalRead(DOUT_PINS[i]) == LOW) participating |= uint16_t(1) << i;
  }
  if (!participating) return;

  // One 25-pulse train for every ready HX711: 24 data bits plus gain-128 select.
  // Interrupts stay disabled to keep PD_SCK HIGH far below the 60us power-down
  // threshold. Channels not ready at the start are invalid for this train.
  noInterrupts();
  for (int bit = 0; bit < 24; ++bit) {
    digitalWrite(HX_CLOCK_PIN, HIGH);
    delayMicroseconds(1);
    for (int i = 0; i < 12; ++i) {
      if (participating & (uint16_t(1) << i))
        values[i] = (values[i] << 1) | uint32_t(digitalRead(DOUT_PINS[i]));
    }
    digitalWrite(HX_CLOCK_PIN, LOW);
    delayMicroseconds(1);
  }
  digitalWrite(HX_CLOCK_PIN, HIGH);
  delayMicroseconds(1);
  digitalWrite(HX_CLOCK_PIN, LOW);
  interrupts();

  for (int i = 0; i < 12; ++i) {
    if (!(participating & (uint16_t(1) << i))) continue;
    Sensor &s = sensors[i];
    s.raw = (values[i] & 0x800000UL) ? int32_t(values[i] | 0xFF000000UL) : int32_t(values[i]);
    s.hasRaw = s.ready = true;
    s.lastReady = millis();
    s.fault = "";
    if (!s.calibrated) continue;
    float grams = float(s.raw - s.tare) / s.countsPerGram;
    s.filtered = isfinite(s.filtered) ? 0.7f * s.filtered + 0.3f * grams : grams;
    bool desired = s.present ? s.filtered > PRESENCE_OFF_G : s.filtered > PRESENCE_ON_G;
    if (desired != s.present) {
      if (++s.pending >= STABLE_SAMPLES) {
        s.present = desired; s.pending = 0;
        publishPresence(i, desired ? "ITEM_PRESENT" : "ITEM_REMOVED");
      }
    } else s.pending = 0;
  }
}

void updateFaults() {
  for (int i = 0; i < 12; ++i) {
    Sensor &s = sensors[i];
    if (!ENABLED[i]) { s.ready = false; s.fault = "disabled"; continue; }
    if (millis() - s.lastReady > SENSOR_TIMEOUT_MS) {
      s.ready = false;
      s.fault = "not_ready";
      s.filtered = NAN;
      s.pending = 0;
      // Preserve the last presence decision; an unplugged sensor is not a removal.
    }
  }
}

void telemetry() {
  JsonDocument doc;
  doc["v"] = 1; doc["type"] = "telemetry";
  doc["seq"] = ++seqNo; doc["uptime_ms"] = millis();
  JsonArray slots = doc["slots"].to<JsonArray>();
  for (int i = 0; i < 12; ++i) {
    Sensor &s = sensors[i];
    JsonObject slot = slots.add<JsonObject>();
    slot["code"] = CODES[i]; slot["ready"] = s.ready;
    if (s.hasRaw) slot["raw"] = s.raw; else slot["raw"] = nullptr;
    slot["calibrated"] = s.calibrated;
    if (s.ready && s.calibrated && isfinite(s.filtered)) slot["grams"] = s.filtered;
    else slot["grams"] = nullptr;
    if (s.ready && (SWITCH_MODE || s.calibrated)) slot["present"] = s.present;
    else slot["present"] = nullptr;
    slot["light_command"] = lightCommands[i];
    slot["light_mode"] = MODE_NAMES[lightModes[i]];
    slot["fault"] = s.fault;
  }
  sendDoc(doc);
}

int slotIndex(const char *code) {
  if (!code) return -1;
  for (int i = 0; i < 12; ++i) if (strcmp(code, CODES[i]) == 0) return i;
  return -1;
}

bool duplicate(const String &id) {
  for (const String &previous : recentIds) if (previous.length() && previous == id) return true;
  recentIds[recentIndex++ % 8] = id;
  return false;
}

void handleLine(const char *line) {
  JsonDocument doc;
  if (deserializeJson(doc, line) || doc["v"].as<int>() != 1 || !doc["type"].is<const char *>()) {
#if SAULI_VERBOSE_DIAGNOSTICS
    Serial.println("[UART] Invalid frame received");
#endif
    return;
  }
  const char *type = doc["type"];
  if (strcmp(type, "ping") == 0) {
    JsonDocument pong; pong["v"] = 1; pong["type"] = "pong";
    pong["seq"] = doc["seq"] | 0; pong["uptime_ms"] = millis(); sendDoc(pong);
    return;
  }
  if (strcmp(type, "status") == 0) { telemetry(); return; }
  if (strcmp(type, "event_ack") == 0) {
    const char *eventId = doc["event_id"] | "";
    for (PendingEvent &event : pendingEvents) if (event.active && event.id == eventId) {
#if SAULI_VERBOSE_DIAGNOSTICS
      Serial.printf("[UART] acknowledged %s %s\n", event.kind.c_str(), CODES[event.slot]);
#endif
      event.active = false; event.id = ""; event.kind = ""; break;
    }
    return;
  }
  if (strcmp(type, "snapshot") == 0) {
    for (int i = 0; i < 12; ++i) publishPresence(i, "SENSOR_SNAPSHOT");
    return;
  }
  if (strcmp(type, "command") != 0) {
#if SAULI_VERBOSE_DIAGNOSTICS
    Serial.printf("[UART] Unsupported frame type: %s\n", type);
#endif
    return;
  }
  String id = doc["id"] | "";
  if (!id.length() || id.length() > 80) return;
  if (duplicate(id)) { sendReply("ack", id, "duplicate_ignored"); return; }
  const char *action = doc["action"] | "";
#if SAULI_VERBOSE_DIAGNOSTICS
  Serial.printf("[LED] received command: %s\n", action);
#endif
  int i = slotIndex(doc["slot"] | "");
  if (strcmp(action, "set_all_lights") == 0) {
    JsonObjectConst modes = doc["modes"].as<JsonObjectConst>();
    if (modes.isNull()) { sendReply("error", id, "invalid_modes"); return; }
    for (int slot = 0; slot < 12; ++slot) {
      const char *name = modes[CODES[slot]] | "OFF";
      bool valid = false;
      for (const char *mode : MODE_NAMES) if (strcmp(name, mode) == 0) valid = true;
      if (!valid) { sendReply("error", id, "invalid_modes"); return; }
    }
    for (int slot = 0; slot < 12; ++slot) {
      LightMode next = parseMode(modes[CODES[slot]] | "OFF");
#if SAULI_VERBOSE_DIAGNOSTICS
      if (lightModes[slot] != next)
        Serial.printf("[LED] %s: %s -> %s\n", CODES[slot], MODE_NAMES[lightModes[slot]], MODE_NAMES[next]);
#endif
      lightModes[slot] = next;
    }
    lastGuidanceAt = millis(); guidanceArmed = true;
    updateLights(); sendReply("ack", id, "lights_updated"); return;
  }
  if (i < 0) { sendReply("error", id, "unknown_slot"); return; }
  Sensor &s = sensors[i];
  if (strcmp(action, "tare") == 0) {
    if (SWITCH_MODE) { sendReply("error", id, "switch_mode"); return; }
    if (!s.ready || !s.hasRaw) { sendReply("error", id, "sensor_not_ready"); return; }
    s.tare = s.raw; s.filtered = NAN; s.present = false; s.pending = 0;
    String key = "t" + String(i); prefs.putInt(key.c_str(), s.tare);
    sendReply("ack", id, "tared"); return;
  }
  if (strcmp(action, "calibrate") == 0) {
    if (SWITCH_MODE) { sendReply("error", id, "switch_mode"); return; }
    float reference = doc["reference_grams"] | 0.0f;
    if (!s.ready || !s.hasRaw || reference <= 0 || reference > 10000) {
      sendReply("error", id, "invalid_calibration"); return;
    }
    float scale = float(s.raw - s.tare) / reference;
    if (!isfinite(scale) || fabsf(scale) < 1.0f) {
      sendReply("error", id, "invalid_calibration"); return;
    }
    s.countsPerGram = scale; s.calibrated = true; s.filtered = NAN;
    String key = "s" + String(i); prefs.putFloat(key.c_str(), scale);
    sendReply("ack", id, "calibrated"); return;
  }
  if (strcmp(action, "set_light") == 0) {
    const char *name = doc["mode"] | "";
    for (int mode = 0; mode < 4; ++mode) if (strcmp(name, MODE_NAMES[mode]) == 0) {
#if SAULI_VERBOSE_DIAGNOSTICS
      if (lightModes[i] != LightMode(mode))
        Serial.printf("[LED] %s: %s -> %s\n", CODES[i], MODE_NAMES[lightModes[i]], name);
#endif
      lightModes[i] = LightMode(mode); updateLights();
      sendReply("ack", id, "light_updated"); return;
    }
    sendReply("error", id, "invalid_mode"); return;
  }
#if SAULI_VERBOSE_DIAGNOSTICS
  Serial.printf("[UART] Unsupported command: %s\n", action);
#endif
  sendReply("error", id, "unsupported_action");
}

void pollSerial() {
  while (Serial1.available()) {
    int c = Serial1.read();
    if (c == '\n') {
      if (!discardLine && lineLength) { lineBuffer[lineLength] = 0; handleLine(lineBuffer); }
      lineLength = 0; discardLine = false;
    } else if (!discardLine && c != '\r') {
      if (lineLength >= MAX_LINE) {
#if SAULI_VERBOSE_DIAGNOSTICS
        Serial.println("[UART] Oversized frame discarded");
#endif
        discardLine = true; lineLength = 0;
      }
      else lineBuffer[lineLength++] = char(c);
    }
  }
}

void setup() {
  pinMode(DATA_PIN, OUTPUT); pinMode(CLOCK_PIN, OUTPUT); pinMode(LATCH_PIN, OUTPUT);
  if (!SWITCH_MODE) { pinMode(HX_CLOCK_PIN, OUTPUT); digitalWrite(HX_CLOCK_PIN, LOW); }
  shiftAllOff();
  for (int i = 0; i < 12; ++i) {
    pinMode(DOUT_PINS[i], SWITCH_MODE ? INPUT_PULLDOWN : INPUT);
    if (SWITCH_MODE) {
      rawSwitch[i] = stableSwitch[i] = digitalRead(DOUT_PINS[i]) == HIGH;
      sensors[i].ready = true; sensors[i].present = stableSwitch[i]; sensors[i].fault = "";
    }
  }
  if (!SWITCH_MODE) loadCalibration();
  bootId = esp_random();
  Serial.begin(115200);  // Native USB CDC debug, separate from the Pi protocol.
  Serial1.begin(BAUD, SERIAL_8N1, UART_RX, UART_TX);
#if SAULI_VERBOSE_DIAGNOSTICS
  Serial.printf("[BOOT] SAULI ESP32-S3 initialized; sensor mode=%s, UART=%lu baud\n",
                SWITCH_MODE ? "switch" : "hx711", static_cast<unsigned long>(BAUD));
#endif
  JsonDocument hello; hello["v"] = 1; hello["type"] = "hello";
  hello["seq"] = ++seqNo; hello["uptime_ms"] = millis();
  hello["firmware"] = "sauli-esp-s3-0.2";
  hello["boot_id"] = String(bootId, HEX);
  hello["sensor_mode"] = SWITCH_MODE ? "switch" : "hx711"; sendDoc(hello);
  if (SWITCH_MODE) for (int i = 0; i < 12; ++i) publishPresence(i, "SENSOR_SNAPSHOT");
}

void loop() {
  pollSerial();
  if (guidanceArmed && millis() - lastGuidanceAt > GUIDANCE_TIMEOUT_MS) {
    for (LightMode &mode : lightModes) mode = OFF;
    guidanceArmed = false;
    Serial.println("[LED] Guidance expired; all outputs off");
  }
  if (SWITCH_MODE) scanSwitches();
  else { sampleSharedClock(); updateFaults(); }
  sendPendingPresence();
  updateLights();
  if (millis() - lastTelemetry >= TELEMETRY_MS) { lastTelemetry = millis(); telemetry(); }
  delay(2);
}
