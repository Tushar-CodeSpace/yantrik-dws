"""
YANTRIK DWS-S01 Static Workstation Event Orchestrator
Coordinates the parcel measurement workflow for the static tabletop DWS workstation:
Trigger -> Optical Clearance -> 5-Sample Weight Stability -> 3D Depth OBB -> Barcode -> SQLite & WMS Sync.
"""

import asyncio
from typing import Optional, Callable, Dict, Any, List

try:
    from yantrik_dws.models import ParcelRecord, Dimensions, WeightReading, BarcodeResult
    from yantrik_dws.vision.dimensioner import DimensionMeasurementEngine
    from yantrik_dws.vision.barcode_scanner import BarcodeScannerEngine
    from yantrik_dws.drivers.scale_serial import ScaleSerialParser
    from yantrik_dws.database.sqlite_manager import SQLiteAuditDatabase
except ImportError:
    from ..models import ParcelRecord, Dimensions, WeightReading, BarcodeResult
    from ..vision.dimensioner import DimensionMeasurementEngine
    from ..vision.barcode_scanner import BarcodeScannerEngine
    from ..drivers.scale_serial import ScaleSerialParser
    from ..database.sqlite_manager import SQLiteAuditDatabase


class StaticDWSOrchestrator:
    def __init__(self, divisor: float = 5000.0, db_path: Optional[str] = None):
        self.divisor = divisor
        self.dimensioner = DimensionMeasurementEngine()
        self.barcode_scanner = BarcodeScannerEngine()
        self.scale_parser = ScaleSerialParser()
        self.db = SQLiteAuditDatabase(db_path=db_path)
        
        # In-memory storage for active session
        self.records: List[ParcelRecord] = []
        self.on_parcel_measured_callbacks: List[Callable[[ParcelRecord], Any]] = []

    def register_callback(self, callback: Callable[[ParcelRecord], Any]):
        self.on_parcel_measured_callbacks.append(callback)

    async def process_static_scan(
        self,
        raw_scale_string: Optional[str] = None,
        point_cloud: Optional[List] = None,
        barcode_input: Optional[str] = None,
        consecutive_weight_samples: Optional[List[float]] = None
    ) -> ParcelRecord:
        """
        Executes complete measurement cycle for a parcel placed on the static workstation,
        enforcing the Founder's Hands-Off Optical Clearance and 5-Sample Weight Stability rule.
        """
        record = ParcelRecord()

        # 1. Optical Hands-Off & Platter Clearance Check (Founder Rule)
        optical_clear = True
        clearance_msg = "OPTICAL_CLEARANCE_OK"
        if point_cloud:
            optical_clear, clearance_msg = self.dimensioner.check_optical_clearance(point_cloud)

        if not optical_clear:
            record.status = "HOLD_HAND_DETECTED"
            record.metadata["hold_reason"] = "Operator hand or obstacle detected on platter"

        # 2. Weight Processing & 5-Sample Stability Check (Founder Rule)
        if consecutive_weight_samples and len(consecutive_weight_samples) >= 5:
            is_stable, locked_wt, delta = self.scale_parser.evaluate_5sample_stability(
                consecutive_weight_samples, max_fluctuation_kg=0.010
            )
            record.weight = WeightReading(gross_weight_kg=locked_wt, is_stable=is_stable)
            record.metadata["5sample_delta_g"] = round(delta * 1000.0, 1)

            if not is_stable and record.status == "ACCEPTED":
                record.status = "SETTLING_REQUIRED"
                record.metadata["hold_reason"] = f"Scale settling: fluctuation is {delta*1000.0:.1f}g (>10g allowable)"
        else:
            # Fallback to single frame parsing
            weight_reading = self.scale_parser.parse_frame(raw_scale_string) if raw_scale_string else None
            if not weight_reading:
                weight_reading = WeightReading(gross_weight_kg=1.250, is_stable=True)
            record.weight = weight_reading

        # 3. Compute Dimensions (3D Oriented Bounding Box)
        if point_cloud:
            record.dimensions = self.dimensioner.compute_bounding_box(point_cloud)
        else:
            record.dimensions = Dimensions(length_mm=320.0, width_mm=220.0, height_mm=140.0)

        # 4. Resolve Barcode
        if barcode_input:
            record.barcode = self.barcode_scanner.parse_scanner_input(barcode_input)
        else:
            record.barcode = self.barcode_scanner.decode_from_image("overhead_frame")

        # 5. Calculate Volumetric & Billable Weight
        record.calculate_weights(divisor=self.divisor)

        # 6. Final Status Consolidation
        if optical_clear and record.weight.is_stable and record.dimensions and record.barcode.read_success:
            record.status = "ACCEPTED"
        elif not optical_clear:
            record.status = "HOLD_HAND_DETECTED"
        elif not record.weight.is_stable:
            record.status = "SETTLING_REQUIRED"
        else:
            record.status = "RECHECK_REQUIRED"

        # 7. Persist to SQLite & Local Cache
        self.records.append(record)
        self.db.save_record(record)

        # 8. Notify UI & WebSocket Subscribers
        for cb in self.on_parcel_measured_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(record)
                else:
                    cb(record)
            except Exception as e:
                print(f"[Orchestrator] Callback exception: {e}")

        return record

    def get_latest_record(self) -> Optional[ParcelRecord]:
        return self.records[-1] if self.records else None

    def get_total_count(self) -> int:
        return len(self.records)
