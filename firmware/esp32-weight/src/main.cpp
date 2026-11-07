#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <math.h>

// ESP32-S3 GPIO numbers. This board is one controller for 8 pocket and 4 medium slots.
constexpr uint8_t DATA_PIN = 1, CLOCK_PIN = 2, LATCH_PIN = 21, HX_CLOCK_PIN = 47;
constexpr uint8_t UART_RX = 44, UART_TX = 43;
constexpr uint32_t BAUD = 115200, TELEMETRY_MS = 1000, SENSOR_TIMEOUT_MS = 3000;
constexpr uint16_t MAX_LINE = 4096;
constexpr float PRESENCE_ON_G = 30.0f, PRESENCE_OFF_G = 15.0f;
constexpr uint8_t STABLE_SAMPLES = 3;
constexpr int8_t LIGHT_BITS[12] = {-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1};
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
char lineBuffer[MAX_LINE + 1];
uint16_t lineLength = 0;
bool discardLine = false;
uint32_t seqNo = 0, lastTelemetry = 0;
String recentIds[8];
uint8_t recentIndex = 0;

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
  // With the output-enable wiring still unverified, leave the 74HC595 data pins
  // inert. No guessed bit ordering or high/low LED polarity is safe to drive.
  digitalWrite(DATA_PIN, LOW);
  digitalWrite(CLOCK_PIN, LOW);
  digitalWrite(LATCH_PIN, LOW);
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
      if (++s.pending >= STABLE_SAMPLES) { s.present = desired; s.pending = 0; }
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
    if (s.ready && s.calibrated) slot["present"] = s.present;
    else slot["present"] = nullptr;
    slot["light_command"] = lightCommands[i];
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
  if (deserializeJson(doc, line) || doc["v"].as<int>() != 1 || !doc["type"].is<const char *>()) return;
  const char *type = doc["type"];
  if (strcmp(type, "ping") == 0) {
    JsonDocument pong; pong["v"] = 1; pong["type"] = "pong";
    pong["seq"] = doc["seq"] | 0; pong["uptime_ms"] = millis(); sendDoc(pong);
    return;
  }
  if (strcmp(type, "status") == 0) { telemetry(); return; }
  if (strcmp(type, "command") != 0) return;
  String id = doc["id"] | "";
  if (!id.length() || id.length() > 80) return;
  if (duplicate(id)) { sendReply("ack", id, "duplicate_ignored"); return; }
  const char *action = doc["action"] | "";
  int i = slotIndex(doc["slot"] | "");
  if (i < 0) { sendReply("error", id, "unknown_slot"); return; }
  Sensor &s = sensors[i];
  if (strcmp(action, "tare") == 0) {
    if (!s.ready || !s.hasRaw) { sendReply("error", id, "sensor_not_ready"); return; }
    s.tare = s.raw; s.filtered = NAN; s.present = false; s.pending = 0;
    String key = "t" + String(i); prefs.putInt(key.c_str(), s.tare);
    sendReply("ack", id, "tared"); return;
  }
  if (strcmp(action, "calibrate") == 0) {
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
    // Source schematic has no verified Q-bit mapping or polarity. Never energize.
    sendReply("error", id, "light_map_unverified"); return;
  }
  sendReply("error", id, "unsupported_action");
}

void pollSerial() {
  while (Serial1.available()) {
    int c = Serial1.read();
    if (c == '\n') {
      if (!discardLine && lineLength) { lineBuffer[lineLength] = 0; handleLine(lineBuffer); }
      lineLength = 0; discardLine = false;
    } else if (!discardLine && c != '\r') {
      if (lineLength >= MAX_LINE) { discardLine = true; lineLength = 0; }
      else lineBuffer[lineLength++] = char(c);
    }
  }
}

void setup() {
  pinMode(DATA_PIN, OUTPUT); pinMode(CLOCK_PIN, OUTPUT); pinMode(LATCH_PIN, OUTPUT);
  pinMode(HX_CLOCK_PIN, OUTPUT); digitalWrite(HX_CLOCK_PIN, LOW);
  shiftAllOff();
  for (int i = 0; i < 12; ++i) pinMode(DOUT_PINS[i], INPUT);
  loadCalibration();
  Serial.begin(115200);  // Native USB CDC debug, separate from the Pi protocol.
  Serial1.begin(BAUD, SERIAL_8N1, UART_RX, UART_TX);
  JsonDocument hello; hello["v"] = 1; hello["type"] = "hello";
  hello["seq"] = ++seqNo; hello["uptime_ms"] = millis();
  hello["firmware"] = "sauli-esp-s3-0.1"; sendDoc(hello);
}

void loop() {
  pollSerial();
  sampleSharedClock();
  updateFaults();
  if (millis() - lastTelemetry >= TELEMETRY_MS) { lastTelemetry = millis(); telemetry(); }
  delay(2);
}
