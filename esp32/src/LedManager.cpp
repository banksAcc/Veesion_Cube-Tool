/**
 * @file LedManager.cpp
 * @brief Implementazione degli effetti LED RGB della penna.
 *
 * Responsabilità: applica colori e animazioni in base allo stato.
 * Dipendenze: Arduino core e API LEDC.
 */

#include <Arduino.h>
#include "LedManager.h"

void LedManager::begin(int pinR, int pinG, int pinB, uint32_t freq, uint8_t res, float brightness, bool commonAnode) {
  pr_ = pinR;
  pg_ = pinG;
  pb_ = pinB;
  freq_ = freq;
  res_ = res;
  br_ = brightness;
  invert_ = commonAnode;
  maxDuty_ = (1u << res_) - 1u;

  bool okR = ledcAttach((uint8_t)pr_, freq_, res_);
  bool okG = ledcAttach((uint8_t)pg_, freq_, res_);
  bool okB = ledcAttach((uint8_t)pb_, freq_, res_);
  if (!okR) pinMode(pr_, OUTPUT);
  if (!okG) pinMode(pg_, OUTPUT);
  if (!okB) pinMode(pb_, OUTPUT);

  setState(LedState::OFF);
}

uint16_t LedManager::scaleByte(uint8_t v) const {
  float f = (float)v / 255.0f;
  uint32_t duty = (uint32_t)(f * (float)maxDuty_ * br_);
  if (duty > maxDuty_) duty = maxDuty_;
  return (uint16_t)duty;
}

uint16_t LedManager::applyInvert(uint16_t duty) const {
  return invert_ ? (maxDuty_ - duty) : duty;
}

void LedManager::setRgb(uint16_t r, uint16_t g, uint16_t b) {
  uint16_t dr = applyInvert(r), dg = applyInvert(g), db = applyInvert(b);
  if (!ledcWrite((uint8_t)pr_, dr)) digitalWrite(pr_, dr ? HIGH : LOW);
  if (!ledcWrite((uint8_t)pg_, dg)) digitalWrite(pg_, dg ? HIGH : LOW);
  if (!ledcWrite((uint8_t)pb_, db)) digitalWrite(pb_, db ? HIGH : LOW);
}

void LedManager::setState(LedState s) {
  st_ = s;
  t0_ = millis();
}

void LedManager::loop() {
  unsigned long t = millis();

  switch (st_) {
    case LedState::OFF:
      setRgb(0, 0, 0);
      break;

    case LedState::CONNECTED:
      {  // verde fisso (tenue per 10%)
        setRgb(0, scaleByte(200), 0);
        break;
      }

    case LedState::SENDING:
      {  // giallo fisso tenue
        uint16_t y = scaleByte(180);
        setRgb(y, y, 0);
        break;
      }

    case LedState::ARMING:
      {                                        // giallo oro lampeggiante ~6Hz
        bool on = ((t / 166) % 2) == 0;        // più veloce
        uint16_t y = on ? scaleByte(200) : 0;  // tenue
        setRgb(y, y, 0);
        break;
      }

    case LedState::ADVERTISING:
      {
        // Fading in/out blu scuro (respiro)
        // ciclo completo ~2s (puoi allungare/accorciare cambiando 2000)
        float phase = (float)((t - t0_) % 2000) / 2000.0f;                    // 0..1
        float tri = (phase < 0.5f) ? (phase * 2.0f) : (2.0f - phase * 2.0f);  // 0..1..0
        float eased = 0.5f - 0.5f * cosf(tri * PI);                           // easing morbido (sin^2)

        // intensità blu max ~150 (su 255) → blu scuro tenue
        uint8_t val = (uint8_t)(eased * 150.0f);

        setRgb(0, 0, scaleByte(val));
        break;
      }


    case LedState::EVENT_RED:
      {  // rosso tenue durante pressione evento (solo se connesso, deciso nel main)
        setRgb(scaleByte(140), 0, 0);
        break;
      }
  }
}
