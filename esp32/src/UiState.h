// =========================
// File: UiState.h
// =========================
#pragma once

enum class UiState {
  OFF,
  BLE_ON,        // advertising
  CONNECTED,     // ble connesso
  SENDING,       // mentre premi EVENT (START/END)
  DISCONNECTED,  // ble spento
  ARMING         // feedback mentre tieni premuto BTN BLE
};
