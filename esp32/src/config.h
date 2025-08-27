// =========================
// File: config.h  (aggiornato con pin anche per LED e pulsanti)
// =========================
#pragma once

// ===== I2C OLED (ESP32 DevKit) =====
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define OLED_WIDTH  128
#define OLED_HEIGHT 64
#define OLED_ADDR   0x3C

// ===== LED RGB (COMMON ANODE 5V) =====
#define PIN_LED_R 15
#define PIN_LED_G 5     // <<-- cambiato a 5
#define PIN_LED_B 4

// ===== Buttons (INPUT_PULLUP) =====
#define PIN_BTN_EVENT 16
#define PIN_BTN_BLE   17
#define BLE_LONG_MS   4000

// ===== LEDC (ESP32 core 3.x) =====
#define LED_PWM_FREQ 5000u
#define LED_PWM_RES  12u
#define LED_BRIGHTNESS 0.05f // 10%

// ===== UI =====
#define UI_MAIN_TEXT_SIZE 3