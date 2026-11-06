# YANTRIK DWS-S01 SECURITY POLICY

## 1. SCOPE & OBJECTIVES

The YANTRIK DWS-S01 is deployed as an on-premise industrial edge appliance in high-throughput parcel sorting hubs and logistics warehouses. Maintaining edge security, data integrity, and network isolation is paramount.

---

## 2. EDGE SECURITY DIRECTIVES

1. **Air-Gapped / Isolated VLAN:** The DWS-S01 edge workstation must reside on an isolated industrial automation VLAN. Direct inbound exposure to public WAN is prohibited.
2. **Local Storage Privacy:** All parcel weight and dimension measurements are stored locally in an embedded SQLite WAL database. No customer shipment data is transmitted off-premise without explicit customer-configured WMS/ERP webhooks.
3. **No Hardcoded Credentials:** Serial ports (`/dev/ttyUSB0`), Modbus endpoints, and WMS webhook tokens must be configured via environment variables or local `/app/config/runtime.json`.

---

## 3. REPORTING SECURITY VULNERABILITIES

To report potential edge vulnerabilities or bugs, contact:
`security@yantrik.internal` / `founder@yantrik.internal`.
