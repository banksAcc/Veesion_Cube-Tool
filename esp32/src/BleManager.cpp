#include <Arduino.h>
#include "BleManager.h"

// UUID Nordic UART-like
static NimBLEUUID UUID_SERVICE("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
static NimBLEUUID UUID_RX     ("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"); // write
static NimBLEUUID UUID_TX     ("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"); // notify

static BleManager* g_ble = nullptr;
void BleManager_initGlobal(BleManager* inst) { g_ble = inst; }

void BleManager::begin(const char* name) {
  NimBLEDevice::init(name);
  pServer_ = NimBLEDevice::createServer();
  pServer_->setCallbacks(new SrvCb());

  NimBLEService* svc = pServer_->createService(UUID_SERVICE);
  pTx_ = svc->createCharacteristic(UUID_TX, NIMBLE_PROPERTY::NOTIFY);
  pRx_ = svc->createCharacteristic(UUID_RX, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  pRx_->setCallbacks(new RxCb());
  svc->start();

  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  NimBLEAdvertisementData ad, sd;
  ad.setName(name); ad.setCompleteServices(UUID_SERVICE);
  sd.setName(name);
  adv->setAdvertisementData(ad);
  adv->setScanResponseData(sd);
}

void BleManager::startAdvertising() { bleEnabled_ = true;  NimBLEDevice::startAdvertising(); }
void BleManager::stopAdvertising()  { bleEnabled_ = false; NimBLEDevice::stopAdvertising();  }

void BleManager::disconnect() {
  if (!pServer_ || !bleConnected_) return;
  if (lastConnHandle_ != 0xFFFF) {
    // motivo standard: Remote User Terminated Connection
    pServer_->disconnect(lastConnHandle_, BLE_ERR_REM_USER_CONN_TERM);
  }
}

void BleManager::sendLine(const char* line) {
  if (bleConnected_ && pTx_) { pTx_->setValue((const uint8_t*)line, strlen(line)); pTx_->notify(); }
}

// ---- callbacks vecchio stile ----
void BleManager::SrvCb::onConnect(NimBLEServer* s) {
  if (!g_ble) return;
  g_ble->bleConnected_ = true;
  // Se non abbiamo info, lasciamo l'handle invariato; verrà impostato dal callback "nuovo stile" quando disponibile
  Serial.println("[BLE] Connected (legacy CB)");
  if (g_ble->onConn_) g_ble->onConn_();
}

void BleManager::SrvCb::onDisconnect(NimBLEServer* s) {
  if (!g_ble) return;
  g_ble->bleConnected_ = false;
  g_ble->lastConnHandle_ = 0xFFFF; // invalida handle
  Serial.println("[BLE] Disconnected (legacy CB)");
  if (g_ble->isEnabled()) NimBLEDevice::startAdvertising();
  if (g_ble->onDisc_) g_ble->onDisc_();
}

void BleManager::RxCb::onWrite(NimBLECharacteristic* c) {
  if (!g_ble) return;
  std::string v = c->getValue(); if (v.empty()) return;
  String s(v.c_str()); s.trim();
  Serial.print("[BLE] RX: "); Serial.println(s);
  if (g_ble->onRx_) g_ble->onRx_(s);
}

// ---- callbacks nuovo stile (con NimBLEConnInfo) ----
void BleManager::SrvCb::onConnect(NimBLEServer* s, NimBLEConnInfo& info) {
  if (!g_ble) return;
  g_ble->bleConnected_ = true;
  g_ble->lastConnHandle_ = info.getConnHandle();  // salva handle
  Serial.printf("[BLE] Connected (handle=%u)\n", g_ble->lastConnHandle_);
  if (g_ble->onConn_) g_ble->onConn_();
}

void BleManager::SrvCb::onDisconnect(NimBLEServer* s, NimBLEConnInfo& info, int reason) {
  if (!g_ble) return;
  g_ble->bleConnected_ = false;
  g_ble->lastConnHandle_ = 0xFFFF;
  Serial.printf("[BLE] Disconnected (handle=%u, reason=%d)\n", info.getConnHandle(), reason);
  if (g_ble->isEnabled()) NimBLEDevice::startAdvertising();
  if (g_ble->onDisc_) g_ble->onDisc_();
}

void BleManager::RxCb::onWrite(NimBLECharacteristic* c, NimBLEConnInfo& /*info*/) {
  onWrite(c);
}
