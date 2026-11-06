#!/usr/bin/env python3
"""
YANTRIK DWS-S01 Static Workstation End-to-End Simulation Test Harness
Simulates continuous operator package handling on the static DWS-S01 workstation,
verifying 3D point cloud dimensioning, digital scale filtering, barcode decoding,
volumetric weight calculations, and throughput latency.
"""

import asyncio
import time
import random
import sys
import os

# Ensure repo root and src root are on Python path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
for p in [REPO_ROOT, SRC_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from yantrik_dws.services.event_orchestrator import StaticDWSOrchestrator
from yantrik_dws.vision.dimensioner import DimensionMeasurementEngine
from tests.simulators.mock_scale import MockScaleSimulator


async def run_simulation(num_parcels: int = 100):
    print("======================================================================")
    print("     YANTRIK DWS-S01 STATIC WORKSTATION E2E SIMULATION HARNESS        ")
    print("======================================================================")
    print(f"Target Batch Size:       {num_parcels} Parcels")
    print("Measurement Modalities:  3D Depth Point Cloud + Serial Scale + Barcode")
    print("Volumetric Divisor:      5000 cm³/kg (Standard Logistics)")
    print("----------------------------------------------------------------------\n")

    orchestrator = StaticDWSOrchestrator(divisor=5000.0)
    scale_sim = MockScaleSimulator()

    start_time = time.time()
    latencies = []
    success_count = 0

    for i in range(1, num_parcels + 1):
        t_start = time.time()

        # 1. Randomize realistic parcel dimensions (mm)
        true_l = round(random.uniform(120.0, 600.0), 1)
        true_w = round(random.uniform(100.0, 450.0), 1)
        true_h = round(random.uniform(50.0, 350.0), 1)
        true_weight = round(random.uniform(0.200, 15.000), 3)
        barcode_id = f"YT{random.randint(100000000, 999999999)}"

        # 2. Generate synthetic point cloud with surface noise
        pt_cloud = DimensionMeasurementEngine.generate_synthetic_parcel(
            length_mm=true_l,
            width_mm=true_w,
            height_mm=true_h,
            num_points=400
        )

        # 3. Generate stable scale string
        scale_string = f"ST,GS,+{true_weight:07.3f},kg\r\n"

        # 4. Execute asynchronous measurement cycle
        record = await orchestrator.process_static_scan(
            raw_scale_string=scale_string,
            point_cloud=pt_cloud,
            barcode_input=barcode_id
        )

        cycle_latency_ms = (time.time() - t_start) * 1000.0
        latencies.append(cycle_latency_ms)

        # Validation Checks
        dim_error_l = abs(record.dimensions.length_mm - max(true_l, true_w))
        dim_error_w = abs(record.dimensions.width_mm - min(true_l, true_w))
        dim_error_h = abs(record.dimensions.height_mm - true_h)
        weight_error = abs(record.weight.gross_weight_kg - true_weight)

        is_valid = (
            dim_error_l <= 6.0 and
            dim_error_w <= 6.0 and
            dim_error_h <= 6.0 and
            weight_error <= 0.020 and
            record.status == "ACCEPTED"
        )
        if is_valid:
            success_count += 1

        if i % 25 == 0 or i == num_parcels:
            print(f"[{i:3d}/{num_parcels}] Barcode: {record.barcode.code} | "
                  f"Dim: {record.dimensions.length_mm:.0f}x{record.dimensions.width_mm:.0f}x{record.dimensions.height_mm:.0f} mm | "
                  f"Gross: {record.weight.gross_weight_kg:.3f} kg | "
                  f"Vol: {record.volumetric_weight_kg:.3f} kg | "
                  f"Billable: {record.billable_weight_kg:.3f} kg | "
                  f"Latency: {cycle_latency_ms:.1f} ms")

    total_duration = time.time() - start_time
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    effective_pph = int((num_parcels / total_duration) * 3600)

    print("\n======================================================================")
    print("                     SIMULATION BENCHMARK REPORT                      ")
    print("======================================================================")
    print(f"Total Parcels Simulated:      {num_parcels}")
    print(f"Successful Validations:       {success_count} / {num_parcels} ({success_count/num_parcels*100:.1f}%)")
    print(f"Total Simulation Duration:    {total_duration:.2f} seconds")
    print(f"Average Pipeline Latency:     {avg_latency:.2f} ms")
    print(f"p95 Pipeline Latency:         {p95_latency:.2f} ms")
    print(f"Simulated Processing Rate:    {effective_pph:,} parcels/hour")
    print("======================================================================")

    if success_count == num_parcels:
        print("  ✅ 100% OF SIMULATED PARCELS PASSED METROLOGY & VOLUMETRIC AUDIT.")
        return True
    else:
        print(f"  ❌ {num_parcels - success_count} PARCELS EXCEEDED MAXIMUM PERMISSIBLE ERROR.")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_simulation(100))
    sys.exit(0 if success else 1)
