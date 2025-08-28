/**
 * @file DisplayManager.cpp
 * @brief Implementazione della gestione del display OLED SSD1306.
 *
 * Responsabilità: rende lo stato del sistema su schermo e gestisce animazioni.
 * Dipendenze: Arduino core, Wire, Adafruit_SSD1306, Adafruit_GFX.
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "DisplayManager.h"

static const int kBlinkMs   = 500;
static const int kAnimMs    = 120;  // velocità spinner e invio

bool DisplayManager::begin() {
  if (inited_) return true;
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  d_ = new Adafruit_SSD1306(OLED_WIDTH, OLED_HEIGHT, &Wire);
  if (!d_->begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    delete d_; d_ = nullptr; inited_ = false; return false;
  }
  d_->clearDisplay(); d_->display();
  d_->setTextWrap(false);
  inited_ = true;
  render();
  return true;
}

void DisplayManager::setBleEnabled(bool on) {
  bleOn_ = on;
  applyPower();
  if (!on) { ui_ = UiState::OFF; computing_ = false; }
  else if (ui_ == UiState::OFF) ui_ = UiState::BLE_ON;
  render();
}

void DisplayManager::setUiState(UiState s) { ui_ = s; render(); }
void DisplayManager::setComputing(bool on) { computing_ = on; render(); }

void DisplayManager::applyPower() {
  if (!inited_) return;
  if (bleOn_) d_->ssd1306_command(SSD1306_DISPLAYON);
  else { d_->ssd1306_command(SSD1306_DISPLAYOFF); d_->clearDisplay(); d_->display(); }
}

void DisplayManager::drawBatteryIcon() {
  // Icona batteria piena in alto a sx (18x8 px)
  int x=2, y=2, w=16, h=8;
  d_->drawRect(x, y, w, h, SSD1306_WHITE);
  d_->fillRect(x+2, y+2, w-4, h-4, SSD1306_WHITE); // sempre piena
  d_->fillRect(x+w, y+2, 2, h-4, SSD1306_WHITE);   // pin
}

void DisplayManager::drawSpinner(uint8_t f) {
  // piccolo cerchio con 8 tacche; mostra una tacca per frame (animazione)
  int cx = OLED_WIDTH - 12; // in alto a dx
  int cy = 10;
  int r  = 7;
  for (uint8_t i=0;i<8;i++){
    float ang = (i * (PI/4));
    int x = cx + (int)(cosf(ang) * r);
    int y = cy + (int)(sinf(ang) * r);
    // solo la tacca corrente
    if (i == f) d_->fillCircle(x,y,2,SSD1306_WHITE);
    else d_->drawPixel(x,y,SSD1306_WHITE);
  }
}

void DisplayManager::drawSendingDots() {
  // “Invio” con puntini animati . .. ...
  const char* base = "Invio";
  d_->setTextSize(UI_MAIN_TEXT_SIZE);
  d_->setTextColor(SSD1306_WHITE);
  d_->setCursor(0, OLED_HEIGHT - (8*UI_MAIN_TEXT_SIZE) - 2);
  d_->print(base);
  d_->print((sendingDots_%3==0)?".":(sendingDots_%3==1)?"..":"...");
}

void DisplayManager::render() {
  if (!inited_ || !bleOn_) return;

  d_->clearDisplay();

  // Batteria (se NON in computing)
  if (!computing_) drawBatteryIcon();

  // Indicatore di calcolo POSA (override in alto a dx)
  if (computing_) {
    const char* msg = "Pose Exti";  // testo richiesto
    d_->setTextSize(2);
    int16_t w = 6 * 2 * strlen(msg);
    int16_t x = (int16_t)OLED_WIDTH - w - 4; if (x < 0) x = 0;
    d_->fillRect(x-2, 0, w+4, 8*2+2, SSD1306_WHITE);
    d_->setTextColor(SSD1306_BLACK);
    d_->setCursor(x, 2);
    d_->print(msg);
    d_->setTextColor(SSD1306_WHITE);
  }

  // Stato principale grande
  d_->setTextSize(UI_MAIN_TEXT_SIZE);
  d_->setTextColor(SSD1306_WHITE);
  d_->setCursor(0, OLED_HEIGHT - (8*UI_MAIN_TEXT_SIZE) - 2);

  switch (ui_) {
    case UiState::OFF:          d_->print(" "); break;
    case UiState::BLE_ON:       d_->print("FREE"); break;
    case UiState::CONNECTED:    d_->print("OK"); break;
    case UiState::SENDING:      /*d_->print("Invio...");*/ drawSendingDots(); break;
    case UiState::DISCONNECTED: d_->print("BLE OFF"); break;
    case UiState::ARMING:       d_->print("Load..."); break;
  }

  // Spinner in advertising
  if (ui_ == UiState::BLE_ON && !computing_) {
    drawSpinner(spinnerFrame_);
  }

  d_->display();
}

void DisplayManager::loop() {
  if (!inited_ || !bleOn_) return;
  unsigned long now = millis();
  if (now - lastAnimMs_ >= (unsigned long)kAnimMs) {
    lastAnimMs_ = now;
    spinnerFrame_ = (spinnerFrame_ + 1) & 7;
    sendingDots_  = (sendingDots_ + 1) % 3;
    blinkOn_ = !blinkOn_;
    render();
  }
}
