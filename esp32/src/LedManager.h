/**
 * @file LedManager.h
 * @brief Controllo del LED RGB con effetti di stato.
 *
 * Responsabilità: gestisce colori/animazioni secondo lo stato della penna.
 * Dipendenze: Arduino core e API LEDC.
 */

#pragma once
#include <Arduino.h>

enum class LedState {
  OFF,
  ADVERTISING,  // ora: verde lampeggiante (più veloce e tenue)
  CONNECTED,    // verde fisso
  SENDING,      // giallo fisso (quando invio)
  ARMING,       // giallo oro lampeggiante (mentre tieni premuto BTN17)
  EVENT_RED     // rosso tenue SOLO se connesso e BTN16 premuto
};

class LedManager {
 public:
  /// Configura pin e PWM per il LED RGB.
  void begin(int pinR, int pinG, int pinB, uint32_t freq, uint8_t res, float brightness, bool commonAnode=true);
  /// Imposta lo stato logico del LED.
  void setState(LedState s);
  /// Aggiorna le animazioni del LED in base allo stato corrente.
  void loop();

 private:
  void setRgb(uint16_t r, uint16_t g, uint16_t b);
  uint16_t scaleByte(uint8_t v) const;
  uint16_t applyInvert(uint16_t duty) const;

  int pr_=-1, pg_=-1, pb_=-1;
  uint32_t freq_=5000; uint8_t res_=12;
  uint16_t maxDuty_=4095;  float br_=0.10f;
  bool invert_ = true;

  LedState st_ = LedState::OFF;
  unsigned long t0_=0;
};
