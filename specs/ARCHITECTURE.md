# YANTRIK DWS-S01 MASTER SYSTEM ARCHITECTURE (STATIC WORKSTATION)

```yaml
---
document_id: YAN-DOC-0031
title: Master System Architecture and Technical Topology — YANTRIK DWS-S01 Static
category: Engineering Architecture / System Design
repository_path: products/dws/ARCHITECTURE.md
version: 1.1.0
status: Approved
approval_level: L3 (Executive Strategy)
author: Central Intelligence / AGT-L1-CTO (Chief Technology Agent)
approved_by: Approved by Founder Directive
effective_date: 2026-11-06
dependencies:
  - company/identity/CONSTITUTION.md
  - products/dws/PRD.md
  - products/dws/METROLOGY_COMPLIANCE.md
validation_checklist:
  - "[x] Maps physical hardware, sensing mast, vision pipeline, and edge software for static machine"
  - "[x] Defines end-to-end parcel processing lifecycle using Mermaid diagrams"
  - "[x] Details serial weigh scale, USB camera, WebSocket HMI, and REST integration layers"
  - "[x] Documents fail-safe states and offline store-and-forward boundaries"
---
```

---

## 1. ARCHITECTURAL OVERVIEW & TOPOLOGY

The **YANTRIK DWS-S01** is a high-speed, compact industrial Static Dimensioning, Weighing, and Scanning workstation. It eliminates mechanical conveyor complexity by integrating an overhead 3D optical gantry, a precision industrial weighing plate, and an industrial Linux edge computer running local computer vision and real-time operator interfaces.

```mermaid
flowchart TD
    subgraph SENSING["1. Sensing & Hardware Layer"]
        CAM["Overhead 3D Depth Camera (RGB-D)"]
        SCALE["Precision Platform Scale (Load Cells)"]
        SCAN["Overhead Barcode Camera / Handheld Gun"]
        PEDAL["Operator Foot Pedal / Trigger"]
    end

    subgraph EDGE["2. Edge Compute Engine (Industrial Linux IPC)"]
        BACKEND["FastAPI Edge Core Microservice"]
        VISION["3D Point Cloud Dimensioning Engine"]
        FILTER["Scale Serial Driver & Median Filter"]
        DB[(Local PostgreSQL Parcel Audit DB)]
    end

    subgraph UI["3. Operator Touchscreen HMI"]
        TOUCH["10.1 / 15.6 Inch Touch Display"]
        WS["WebSocket Real-Time Broadcast Feed"]
    end

    subgraph ENTERPRISE["4. Enterprise Warehouse Integration"]
        WMS["Customer WMS / ERP (SAP, Oracle, NetSuite)"]
        QUEUE["Offline Store-and-Forward Sync Queue"]
    end

    SCALE -->|"RS-232 / USB Serial"| FILTER
    CAM -->|"USB 3.0 Point Cloud"| VISION
    SCAN -->|"USB HID / VCP"| BACKEND
    PEDAL -->|"GPIO / Serial Trigger"| BACKEND

    FILTER -->|"Stable Weight"| BACKEND
    VISION -->|"Bounding Box L x W x H"| BACKEND

    BACKEND --> DB
    BACKEND -->|"JSON Event Stream"| WS
    WS --> TOUCH

    BACKEND --> QUEUE
    QUEUE -->|"REST HTTPS / Webhooks"| WMS
```

---

## 2. HARDWARE CABLING & INTERFACE TOPOLOGY

```mermaid
flowchart LR
    MAINS["230V AC Single Phase Mains"] --> PSU["24VDC Industrial Power Supply"]
    MAINS --> IPC["Industrial Linux Mini-PC (Edge Core)"]
    
    PSU --> SCALE_IND["Digital Weighing Indicator"]
    SCALE_IND --- CELLS["4x C3 Shear Beam Load Cells (Base Bed)"]
    
    SCALE_IND -->|"RS-232 / Serial Stream"| IPC
    
    IPC -->|"USB 3.0"| DEPTH_CAM["Overhead 3D RGB-D Depth Camera"]
    IPC -->|"USB 2.0"| BARCODE_SCAN["Top Barcode Scanner / Gun"]
    IPC -->|"HDMI / USB Touch"| TOUCH_SCREEN["Operator Touchscreen HMI"]
    
    PSU --> LED_BAR["5500K Daylight LED Illumination Shroud"]
```

---

## 3. REAL-TIME STATIC MEASUREMENT SEQUENCE

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Warehouse Operator
    participant Scale as Static Weigh Plate
    participant Camera as Overhead 3D Sensor
    participant Edge as Edge IPC (FastAPI Core)
    participant HMI as Touchscreen HMI
    participant WMS as Customer WMS / ERP

    Operator->>Scale: Places Parcel onto scale bed
    Scale->>Edge: Streams raw weight samples (RS-232)
    Note over Edge: Digital filter locks stable weight (<100ms)
    
    alt Auto-Weight Trigger or Foot Pedal
        Edge->>Camera: Trigger 3D Point Cloud & Image Grab
    else Operator Barcode Gun Scan
        Operator->>Edge: Barcode scan input received
        Edge->>Camera: Trigger 3D Point Cloud Grab
    end
    
    Camera->>Edge: Returns 3D Point Cloud buffer
    Note over Edge: RANSAC Bed Removal & Bounding Box (L × W × H)
    
    Edge->>Edge: Calculate Volumetric Weight (L × W × H / 5000)
    Edge->>Edge: Determine Billable Weight = max(Gross, Volumetric)
    
    Edge->>HMI: Broadcast measurement event (WebSocket)
    HMI-->>Operator: Displays Green confirmation + dimensions
    
    Edge->>Edge: Persist immutable audit record to PostgreSQL
    Edge->>WMS: Push intake manifest (REST Webhook)
    WMS-->>Edge: Returns Sort Chute / Manifest ACK
    HMI-->>Operator: Shows Target Chute / Manifest OK
    Operator->>Scale: Removes Parcel to dispatch cart
```

---

## 4. REAL-TIME LATENCY BUDGET (<800ms STATIC CYCLE)

On the static workstation, the entire automated cycle executes in **under $800\text{ms}$** from parcel placement to visual HMI confirmation:

```mermaid
gantt
    title Static DWS Parcel Measurement Latency Budget
    dateFormat X
    axisFormat %s ms

    section Weighing
    Load Cell Mechanical Settling      :a1, 0, 200
    Digital Noise Filtering           :a2, 200, 250

    section Computer Vision
    RGB-D Frame Capture               :b1, 200, 320
    RANSAC Bed Removal & Bounding Box :b2, 320, 420
    Barcode Decoding                  :b3, 320, 400

    section Consolidation
    Weight Consolidation & Vol Weight :c1, 420, 450
    Local PostgreSQL DB Persist       :c2, 450, 480
    WebSocket HMI Screen Render       :c3, 480, 520
    Outbound WMS HTTP Post Push       :c4, 520, 750
```

---

## 4. SOFTWARE SUBSYSTEM ARCHITECTURE

### 4.1 Asynchronous Event Orchestrator (`services/event_orchestrator.py`)
- Coordinates the asynchronous pipeline using Python's `asyncio` event loop.
- Consumes inputs from independent producer queues:
  - `plc_queue`: State triggers from conveyor optical sensors.
  - `scale_queue`: Streaming digital weight strings with timestamp buffers.
  - `vision_queue`: 3D bounding box dimension structures.
  - `barcode_queue`: Decoded string payloads.
- Emits atomic, validated `ParcelEvent` instances to the database and external API pushers.

### 4.2 Fail-Safe State & Error Isolation
- **Hardware Decoupling:** In the event of an edge PC operating system crash or reboot, the physical PLC continues conveyor motor motion safely under local photoelectric interlocks, automatically diverting unscanned parcels to a manual exception lane.
- **Network Decoupling (Store-and-Forward):** If the warehouse enterprise network or cloud WMS disconnects, local PostgreSQL tables retain up to 5,000,000 un-synced parcel records. An asynchronous worker retries delivery using exponential backoff with jitter once network connectivity is restored.
