# YANTRIK DWS-S01 / DWS-D01 INTERFACE CONTRACTS & PROTOCOLS

```yaml
---
document_id: YAN-DOC-0032
title: Inter-Module Interface Contracts, Communication Protocols, and Register Maps — YANTRIK DWS
category: Engineering Specifications / Interface Contracts
repository_path: products/dws/specs/INTERFACE_CONTRACTS.md
version: 1.1.0
status: Approved
approval_level: L3 (Executive Strategy)
author: Central Intelligence / AGT-D07-BCK01 (Backend Lead)
approved_by: Approved by Founder Directive
effective_date: 2026-11-06
dependencies:
  - products/dws/PRD.md
  - products/dws/ARCHITECTURE.md
validation_checklist:
  - "[x] Defines Modbus TCP/IP holding register memory map for PLC-Edge comms"
  - "[x] Defines RS-232/RS-485 serial weighing indicator string protocol"
  - "[x] Defines 3D vision JSON payload schema"
  - "[x] Defines WebSocket HMI and outbound WMS REST dispatch schemas"
---
```

---

## 1. MODBUS TCP/IP PLC REGISTER MAP

Communication between the Siemens/Delta PLC and the Linux Edge IPC occurs via Modbus TCP on standard port `502`.

### Discrete Inputs (Read-Only Status Coils):
| Address | Signal Name | Data Type | Description |
| :---: | :--- | :---: | :--- |
| `10001` | `DI_INFEED_PHOTO_EYE` | Boolean | `1` = Parcel leading edge detected at infeed beam |
| `10002` | `DI_WEIGH_BED_PHOTO_EYE` | Boolean | `1` = Parcel fully positioned on dynamic scale bed |
| `10003` | `DI_OUTFEED_PHOTO_EYE` | Boolean | `1` = Parcel clearing outfeed measurement zone |
| `10004` | `DI_ESTOP_HEALTHY` | Boolean | `1` = E-Stop loop closed and healthy; `0` = Tripped |
| `10005` | `DI_VFD_RUNNING` | Boolean | `1` = Conveyor motor running at setpoint speed |
| `10006` | `DI_VFD_FAULT` | Boolean | `1` = Motor overload / thermal fault active |

### Holding Registers (Read/Write Controls):
| Address | Register Name | Data Type | Units / Scaling | Description |
| :---: | :--- | :---: | :---: | :--- |
| `40001` | `HR_CONVEYOR_SPEED_SET` | UINT16 | $\text{mm/s}$ ($0\text{--}2500$) | Desired conveyor linear belt velocity setpoint |
| `40002` | `HR_SYSTEM_COMMAND` | UINT16 | Bitmask | `0x01`: Run, `0x02`: Stop, `0x04`: Reset Fault |
| `40003` | `HR_REJECT_DIVERT_TRIGGER`| UINT16 | Parcel ID | Triggers downstream pneumatic diverter gate |
| `40004` | `HR_HEARTBEAT_IPC` | UINT16 | Counter ($0\text{--}65535$) | IPC watchdog heartbeat (PLC trips if stagnant $>2\text{s}$) |
| `40005` | `HR_HEARTBEAT_PLC` | UINT16 | Counter ($0\text{--}65535$) | PLC watchdog echo |

---

## 2. SERIAL WEIGHING INDICATOR PROTOCOL (RS-232 / RS-485)

- **Baud Rate:** `115200` bps (or `9600` selectable)
- **Data Bits:** `8`, **Parity:** `None`, **Stop Bits:** `1`
- **Output Mode:** Continuous Streaming ($50\text{ readings/second}$)
- **ASCII String Frame:** `<STX><Status>,<Type>,<Sign><Weight>,<Unit><CR><LF>`

### Example Payload:
```text
ST,GS,+002.450,kg\r\n
```
- `ST`: Stable reading (`US` = Unstable / settling, `OL` = Overload)
- `GS`: Gross Weight (`NT` = Net Weight)
- `+002.450`: Weight value formatted to 3 decimal places (kg)
- `kg`: Measurement unit

---

## 3. VISION 3D BOUNDING BOX JSON SCHEMA

The computer vision engine emits dimension and barcode payloads using the following strict schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ParcelScanResult",
  "type": "object",
  "required": ["timestamp", "dimensions", "weight", "barcode", "status"],
  "properties": {
    "timestamp": { "type": "string", "format": "date-time" },
    "parcel_id": { "type": "string", "format": "uuid" },
    "dimensions": {
      "type": "object",
      "required": ["length_mm", "width_mm", "height_mm", "volume_cm3", "is_irregular"],
      "properties": {
        "length_mm": { "type": "number", "minimum": 10.0 },
        "width_mm": { "type": "number", "minimum": 10.0 },
        "height_mm": { "type": "number", "minimum": 10.0 },
        "volume_cm3": { "type": "number", "minimum": 0.01 },
        "is_irregular": { "type": "boolean" },
        "confidence_score": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
      }
    },
    "weight": {
      "type": "object",
      "required": ["gross_weight_kg", "is_stable"],
      "properties": {
        "gross_weight_kg": { "type": "number", "minimum": 0.01 },
        "is_stable": { "type": "boolean" },
        "tare_weight_kg": { "type": "number" }
      }
    },
    "volumetric_weight_kg": { "type": "number" },
    "billable_weight_kg": { "type": "number" },
    "barcode": {
      "type": "object",
      "required": ["code", "symbology", "read_success"],
      "properties": {
        "code": { "type": "string" },
        "symbology": { "type": "string", "enum": ["CODE128", "QR", "DATAMATRIX", "EAN13", "NONE"] },
        "read_success": { "type": "boolean" }
      }
    },
    "image_paths": {
      "type": "object",
      "properties": {
        "top_rgb": { "type": "string" },
        "depth_map": { "type": "string" }
      }
    },
    "status": { "type": "string", "enum": ["ACCEPTED", "RECHECK_REQUIRED", "REJECTED"] }
  }
}
```

---

## 4. OUTBOUND WMS REST WEBHOOK CONTRACT

When a parcel completes measurement, the edge engine posts an idempotent payload to the client's WMS endpoint:

- **Method:** `POST /api/v1/parcels/intake`
- **Headers:**
  - `Content-Type: application/json`
  - `X-YANTRIK-Signature: sha256=<HMAC>`
  - `Idempotency-Key: <UUID>`

### Expected Response:
- `HTTP 200 OK` or `HTTP 201 Created`
```json
{
  "acknowledged": true,
  "route_bin": "SORT_CHUTE_04",
  "divert_action": "DIVERT_RIGHT"
}
```
