#pragma once
#include <Arduino.h>
#include "UiState.h"
#include "config.h"

class Adafruit_SSD1306;

class DisplayManager {
 public:
  bool begin();
  void loop();

  void setBleEnabled(bool on);
  void setUiState(UiState s);

  // indicatore "Pose Exti" (ex computation)
  void setComputing(bool on);

 private:
  void applyPower();
  void render();
  void drawSpinner(uint8_t frame);     // animazione in stato BLE_ON
  void drawBatteryIcon();              // batteria fissa (sempre piena)
  void drawSendingDots();              // animazione invio in SENDING

  Adafruit_SSD1306* d_ = nullptr;
  bool inited_ = false;
  bool bleOn_  = false;
  UiState ui_  = UiState::OFF;
  bool computing_ = false;

  // blink/anim
  unsigned long lastAnimMs_ = 0;
  bool blinkOn_ = true;
  uint8_t spinnerFrame_ = 0;
  uint8_t sendingDots_  = 0;
};
