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

  void begin(const char* name);
  void startAdvertising();
  void stopAdvertising();
  void disconnect();  // disconnette se connesso (usa lastConnHandle_)

  bool isEnabled()   const { return bleEnabled_; }
  bool isConnected() const { return bleConnected_; }

  void sendLine(const char* line);

  void onConnect(OnConnectCB cb)       { onConn_ = cb; }
  void onDisconnect(OnDisconnectCB cb) { onDisc_ = cb; }
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
