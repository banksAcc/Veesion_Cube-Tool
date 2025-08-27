#include <Arduino.h>
#include "config.h"
#include "LedManager.h"
#include "Buttons.h"
#include "BleManager.h"
#include "DisplayManager.h"
#include "UiState.h"

LedManager     LEDS;
Buttons        BTNS;
BleManager     BLE;
DisplayManager OLED;

// per gestione long-press immediata
static bool bleLongHandled = false;
static unsigned long displayOffAtMs  = 0;

void setup() {
  Serial.begin(115200);

  OLED.begin();
  LEDS.begin(PIN_LED_R, PIN_LED_G, PIN_LED_B, LED_PWM_FREQ, LED_PWM_RES, LED_BRIGHTNESS, /*commonAnode=*/true);
  BTNS.begin(PIN_BTN_BLE, PIN_BTN_EVENT);

  BleManager_initGlobal(&BLE);
  BLE.begin("ESP32-RGB-BLE");

  BLE.onConnect([&]{
    Serial.println("[BLE] Connected");
    LEDS.setState(LedState::CONNECTED);
    OLED.setBleEnabled(true);
    OLED.setUiState(UiState::CONNECTED);
  });

  BLE.onDisconnect([&]{
    Serial.println("[BLE] Disconnected");
    if (BLE.isEnabled()) {
      LEDS.setState(LedState::ADVERTISING);
      OLED.setBleEnabled(true);
      OLED.setUiState(UiState::BLE_ON);
    } else {
      LEDS.setState(LedState::OFF);
      OLED.setUiState(UiState::DISCONNECTED);
      displayOffAtMs = millis() + 1000; // spegni OLED dopo 1s
    }
  });

  BLE.onRx([&](const String& sRaw){
    String s = sRaw; s.trim(); s.toUpperCase();
    Serial.print("[BLE] RX: "); Serial.println(s);
    if (s == "COMPUTATION START")      OLED.setComputing(true);
    else if (s == "COMPUTATION END")   OLED.setComputing(false);
  });

  BLE.startAdvertising();
  LEDS.setState(LedState::ADVERTISING);
  OLED.setBleEnabled(true);
  OLED.setUiState(UiState::BLE_ON);

  Serial.println("== READY ==");
}

void loop() {
  // Spegnimento differito OLED
  if (displayOffAtMs && millis() >= displayOffAtMs) {
    displayOffAtMs = 0;
    OLED.setBleEnabled(false);
  }

  // ===== BTN BLE (pin 17) =====
  auto bBle = BTNS.pollBle(BLE_LONG_MS);

  if (bBle.fell) {
    bleLongHandled = false;
    LEDS.setState(LedState::ARMING);           // feedback mentre lo tieni
    if (BLE.isEnabled()) OLED.setUiState(UiState::ARMING);
  }

  if (bBle.isDown && !bleLongHandled) {
    // attiva long-press appena supera soglia, senza attendere rilascio
    static unsigned long holdStart = 0;
    if (!holdStart) holdStart = millis();
    if (millis() - holdStart >= BLE_LONG_MS) {
      bleLongHandled = true; holdStart = 0;
      // toggle immediato
      if (BLE.isEnabled()) {
        if (BLE.isConnected()) BLE.disconnect();
        BLE.stopAdvertising();
        LEDS.setState(LedState::OFF);
        OLED.setUiState(UiState::DISCONNECTED);
        displayOffAtMs = millis() + 1000;
      } else {
        BLE.startAdvertising();
        LEDS.setState(LedState::ADVERTISING);
        OLED.setBleEnabled(true);
        OLED.setUiState(UiState::BLE_ON);
      }
    }
  }
  if (!bBle.isDown) {
    // reset hold timer quando rilascia
    static unsigned long holdStart = 0; holdStart = 0;
  }

  if (bBle.rose && !bleLongHandled) {
    // short-press: disconnetti e torna in ADV
    if (BLE.isConnected()) BLE.disconnect();
    if (BLE.isEnabled()) {
      BLE.startAdvertising();
      LEDS.setState(LedState::ADVERTISING);
      OLED.setBleEnabled(true);
      OLED.setUiState(UiState::BLE_ON);
    }
  }

  // ===== BTN EVENT (pin 16) =====
  auto bEvt = BTNS.pollEvt(1500);

  // LED rosso SOLO se connesso
  if (bEvt.isDown && BLE.isConnected()) {
    LEDS.setState(LedState::EVENT_RED);
  }

  if (bEvt.fell) {
    if (BLE.isConnected()) {
      BLE.sendLine("START\n");
      Serial.println("[BLE] TX: START");
      OLED.setUiState(UiState::SENDING);  // anim puntini
    } else {
      Serial.println("[BLE] TX IGNORED: not connected");
    }
  }
  if (bEvt.rose) {
    if (BLE.isConnected()) {
      BLE.sendLine("END\n");
      Serial.println("[BLE] TX: END");
      OLED.setUiState(UiState::CONNECTED);
      LEDS.setState(LedState::CONNECTED);
    }
  }

  // ===== Stato LED “di base” quando non stai forzando con i tasti =====
  if (!bEvt.isDown && !bBle.isDown && !bleLongHandled) {
    if (BLE.isEnabled()) {
      if (BLE.isConnected()) LEDS.setState(LedState::CONNECTED);
      else                   LEDS.setState(LedState::ADVERTISING);
    } else {
      LEDS.setState(LedState::OFF);
    }
  }

  LEDS.loop();
  OLED.loop();
}
