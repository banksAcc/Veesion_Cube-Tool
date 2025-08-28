/**
 * @file BleManager.h
 * @brief Gestione del server BLE basato su NimBLE-Arduino.
 *
 * Responsabilità: avvia lo stack BLE, gestisce connessioni e I/O.
 * Dipendenze: Arduino core, NimBLE-Arduino.
 */

#pragma once
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <functional>

// forward per compatibilità
class NimBLEConnInfo;

class BleManager {
 public:
  using OnConnectCB    = std::function<void()>;
  using OnDisconnectCB = std::function<void()>;
  using OnRxCB         = std::function<void(const String&)>;

  /// Inizializza lo stack BLE con il nome del dispositivo.
  void begin(const char* name);
  /// Avvia l'advertising del servizio BLE.
  void startAdvertising();
  /// Ferma l'advertising del servizio BLE.
  void stopAdvertising();
  /// Disconnette il client se connesso (usa lastConnHandle_).
  void disconnect();

  /// Ritorna true se il BLE è abilitato.
  bool isEnabled()   const { return bleEnabled_; }
  /// Ritorna true se esiste una connessione attiva.
  bool isConnected() const { return bleConnected_; }

  /// Invia una riga di testo sulla caratteristica di notifica.
  void sendLine(const char* line);

  /// Imposta il callback invocato alla connessione.
  void onConnect(OnConnectCB cb)       { onConn_ = cb; }
  /// Imposta il callback invocato alla disconnessione.
  void onDisconnect(OnDisconnectCB cb) { onDisc_ = cb; }
  /// Imposta il callback per i messaggi ricevuti.
  void onRx(OnRxCB cb)                 { onRx_ = cb; }

 private:
  class SrvCb : public NimBLEServerCallbacks {
    // Vecchio stile
    void onConnect(NimBLEServer* s);
    void onDisconnect(NimBLEServer* s);
    // Nuovo stile (con conn info)
    void onConnect(NimBLEServer* s, NimBLEConnInfo& info);
    void onDisconnect(NimBLEServer* s, NimBLEConnInfo& info, int reason);
  };
  class RxCb : public NimBLECharacteristicCallbacks {
    // Vecchio stile
    void onWrite(NimBLECharacteristic* c);
    // Nuovo stile
    void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info);
  };

  friend class SrvCb; friend class RxCb;

  bool bleEnabled_   = false;
  bool bleConnected_ = false;

  NimBLEServer*         pServer_ = nullptr;
  NimBLECharacteristic* pTx_     = nullptr;
  NimBLECharacteristic* pRx_     = nullptr;

  // Handle ultima connessione (richiesto da NimBLEServer::disconnect)
  uint16_t lastConnHandle_ = 0xFFFF;

  OnConnectCB    onConn_ = nullptr;
  OnDisconnectCB onDisc_ = nullptr;
  OnRxCB         onRx_   = nullptr;
};

void BleManager_initGlobal(BleManager* inst);
