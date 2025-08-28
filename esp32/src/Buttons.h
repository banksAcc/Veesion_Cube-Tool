/**
 * @file Buttons.h
 * @brief Gestione di due pulsanti con debounce e long-press.
 *
 * Responsabilità: fornisce eventi di pressione breve/lunga.
 * Dipendenze: Arduino core.
 */

#pragma once
#include <Arduino.h>

/*
 * Modello eventi pulsante
 *
 *  time (ms) : 0    50   550   800
 *  livello   : HIGH \____LOW____/ HIGH
 *                fell  longPress  rose
 *
 *  fell      -> transizione da rilasciato (HIGH) a premuto (LOW)
 *  rose      -> transizione da premuto (LOW) a rilasciato (HIGH)
 *  longPress -> il pulsante resta LOW per `longMs` millisecondi
 *  isDown    -> stato corrente del pulsante (LOW quando premuto)
 */

struct Button {
  int pin;
  bool lastStable = true;  // pull-up -> HIGH = rilasciato
  bool lastRead   = true;
  unsigned long lastChangeMs = 0;
  unsigned long pressedStartMs = 0;
  bool longHandled = false;
};

struct ButtonEvents { bool fell=false; bool rose=false; bool longPress=false; bool isDown=false; };

class Buttons {
 public:
  /// Configura i pin dei pulsanti (pull-up).
  void begin(int pinBle, int pinEvt){
    bBle_.pin = pinBle;  bEvt_.pin = pinEvt;
    pinMode(pinBle, INPUT_PULLUP); pinMode(pinEvt, INPUT_PULLUP);
  }
  /// Rileva eventi dal pulsante BLE.
  ButtonEvents pollBle(unsigned long longMs){ return poll_(bBle_, longMs); }
  /// Rileva eventi dal pulsante evento.
  ButtonEvents pollEvt(unsigned long longMs){ return poll_(bEvt_, longMs); }

 private:
  static ButtonEvents poll_(Button& b, unsigned long longMs){
    ButtonEvents ev; unsigned long now = millis(); bool raw = digitalRead(b.pin);
    if (raw != b.lastRead) { b.lastRead = raw; b.lastChangeMs = now; }
    if (now - b.lastChangeMs > 30) {
      if (raw != b.lastStable) {
        b.lastStable = raw;
        if (raw == LOW) { ev.fell = true; b.pressedStartMs = now; b.longHandled=false; }
        else { ev.rose = true; }
      }
    }
    if (b.lastStable == LOW && !b.longHandled && (now - b.pressedStartMs >= longMs)){
      ev.longPress = true; b.longHandled = true;
    }
    ev.isDown = (b.lastStable == LOW);
    return ev;
  }
  Button bBle_; Button bEvt_;
};
