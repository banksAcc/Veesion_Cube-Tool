// =========================
// File: config.h
// =========================
#pragma once

// ===== I2C OLED =====
#define I2C_SDA_PIN    21    // I2C SDA pin (GPIO 21)
#define I2C_SCL_PIN    22    // I2C SCL pin (GPIO 22)
#define OLED_WIDTH     128   // Display width in pixels
#define OLED_HEIGHT    64    // Display height in pixels
#define OLED_ADDR      0x3C  // I2C address (7-bit)

// ===== RGB LED =====
#define PIN_LED_R      15    // Red LED pin (GPIO 15)
#define PIN_LED_G      5     // Green LED pin (GPIO 5)
#define PIN_LED_B      4     // Blue LED pin (GPIO 4)

// ===== Buttons =====
#define PIN_BTN_EVENT  16    // Event button pin (GPIO 16)
#define PIN_BTN_BLE    17    // BLE button pin (GPIO 17)
#define BLE_LONG_MS    4000  // BLE long-press duration in ms

// ===== PWM =====
#define LED_PWM_FREQ   5000u // PWM frequency in Hz
#define LED_PWM_RES    12u   // PWM resolution in bits
#define LED_BRIGHTNESS 0.05f // LED brightness [0-1]

// ===== UI =====
#define UI_MAIN_TEXT_SIZE 3   // Main text size multiplier

