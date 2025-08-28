/**
 * @file DisplayManager.h
 * @brief Gestione del display OLED SSD1306 per lo stato della penna.
 *
 * Responsabilità: mostra stato BLE, messaggi e animazioni.
 * Dipendenze: Arduino core, Adafruit_SSD1306, Adafruit_GFX, Wire.
 */

#pragma once
#include <Arduino.h>
#include "UiState.h"
#include "config.h"

class Adafruit_SSD1306;

class DisplayManager {
 public:
  /// Inizializza il display e prepara le risorse grafiche.
  bool begin();
  /// Aggiorna eventuali animazioni del display.
  void loop();

  /// Accende o spegne il display in base allo stato del BLE.
  void setBleEnabled(bool on);
  /// Imposta lo stato dell'interfaccia utente da visualizzare.
  void setUiState(UiState s);

  // indicatore "Pose Exti" (ex computation)
  /// Mostra o nasconde l'indicatore di calcolo posa.
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
