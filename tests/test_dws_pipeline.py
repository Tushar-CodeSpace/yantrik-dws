#!/usr/bin/env python3
"""
Unit and Integration Test Suite for YANTRIK DWS-S01 Core Pipeline
Tests scale serial parsing, 5-sample weight stability filter, optical hand clearance,
3D point cloud dimensioning, barcode processing, volumetric calculations, SQLite persistence,
and asynchronous orchestrator sequencing.
"""

import unittest
import asyncio
import sys
import os
import tempfile

# Ensure repository root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from yantrik_dws.models import (
    Dimensions, WeightReading, BarcodeResult, ParcelRecord
)
from yantrik_dws.drivers.scale_serial import ScaleSerialParser
from yantrik_dws.vision.dimensioner import DimensionMeasurementEngine
from yantrik_dws.vision.barcode_scanner import BarcodeScannerEngine
from yantrik_dws.database.sqlite_manager import SQLiteAuditDatabase
from yantrik_dws.services.event_orchestrator import StaticDWSOrchestrator


class TestScaleSerialParser(unittest.TestCase):
    def setUp(self):
        self.parser = ScaleSerialParser(window_size=5)

    def test_parse_valid_stable_frame(self):
        line = "ST,GS,+004.250,kg\r\n"
        res = self.parser.parse_frame(line)
        self.assertIsNotNone(res)
        self.assertEqual(res.gross_weight_kg, 4.250)
        self.assertTrue(res.is_stable)

    def test_parse_gram_conversion(self):
        line = "ST,GS,+02500,g\r\n"
        res = self.parser.parse_frame(line)
        self.assertIsNotNone(res)
        self.assertEqual(res.gross_weight_kg, 2.500)

    def test_parse_unstable_frame(self):
        line = "US,GS,+001.200,kg\r\n"
        res = self.parser.parse_frame(line)
        self.assertIsNotNone(res)
        self.assertFalse(res.is_stable)

    def test_parse_invalid_format(self):
        line = "GARBAGE_SERIAL_DATA\r\n"
        res = self.parser.parse_frame(line)
        self.assertIsNone(res)

    def test_filter_reset_between_parcels(self):
        self.parser.parse_frame("ST,GS,+010.000,kg\r\n")
        self.parser.reset_filter()
        res = self.parser.parse_frame("ST,GS,+002.000,kg\r\n")
        self.assertEqual(res.gross_weight_kg, 2.000)

    def test_5sample_stability_pass(self):
        # 5 samples within 6g fluctuation (<= 10g threshold)
        samples = [2.450, 2.452, 2.448, 2.451, 2.450]
        is_stable, locked_wt, delta = ScaleSerialParser.evaluate_5sample_stability(samples, max_fluctuation_kg=0.010)
        self.assertTrue(is_stable)
        self.assertAlmostEqual(locked_wt, 2.450, delta=0.005)
        self.assertLessEqual(delta, 0.010)

    def test_5sample_stability_fail_jitter(self):
        # 5 samples with 40g fluctuation (> 10g threshold)
        samples = [2.450, 2.485, 2.445, 2.470, 2.460]
        is_stable, locked_wt, delta = ScaleSerialParser.evaluate_5sample_stability(samples, max_fluctuation_kg=0.010)
        self.assertFalse(is_stable)
        self.assertGreater(delta, 0.010)


class TestDimensionerEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DimensionMeasurementEngine(bed_height_mm=0.0)

    def test_cuboid_bounding_box(self):
        true_l, true_w, true_h = 350.0, 250.0, 150.0
        pts = DimensionMeasurementEngine.generate_synthetic_parcel(
            length_mm=true_l, width_mm=true_w, height_mm=true_h, num_points=300
        )
        res = self.engine.compute_bounding_box(pts)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res.length_mm, true_l, delta=4.0)
        self.assertAlmostEqual(res.width_mm, true_w, delta=4.0)
        self.assertAlmostEqual(res.height_mm, true_h, delta=4.0)
        self.assertFalse(res.is_irregular)

    def test_empty_point_cloud(self):
        res = self.engine.compute_bounding_box([])
        self.assertIsNone(res)

    def test_below_bed_noise_filtering(self):
        noise_pts = [(10.0, 10.0, 2.0), (20.0, 20.0, 3.5), (30.0, 30.0, 1.0)]
        res = self.engine.compute_bounding_box(noise_pts)
        self.assertIsNone(res)

    def test_optical_hand_interference_detection(self):
        # Generate parcel with injected hand points extending outside platter
        pts_with_hand = DimensionMeasurementEngine.generate_synthetic_parcel(
            length_mm=300.0, width_mm=200.0, height_mm=100.0, inject_hand=True
        )
        is_clear, reason = self.engine.check_optical_clearance(pts_with_hand)
        self.assertFalse(is_clear)
        self.assertEqual(reason, "HOLD_HAND_DETECTED")

    def test_optical_clearance_success(self):
        # Isolated parcel on platter
        pts_clean = DimensionMeasurementEngine.generate_synthetic_parcel(
            length_mm=300.0, width_mm=200.0, height_mm=100.0, inject_hand=False
        )
        is_clear, reason = self.engine.check_optical_clearance(pts_clean)
        self.assertTrue(is_clear)
        self.assertEqual(reason, "OPTICAL_CLEARANCE_OK")


class TestSQLiteAuditDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.db = SQLiteAuditDatabase(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_save_and_retrieve_record(self):
        record = ParcelRecord()
        record.dimensions = Dimensions(length_mm=400.0, width_mm=300.0, height_mm=200.0)
        record.weight = WeightReading(gross_weight_kg=5.000, is_stable=True)
        record.barcode = BarcodeResult(code="YT998877665")
        record.calculate_weights(divisor=5000.0)
        record.status = "ACCEPTED"

        saved = self.db.save_record(record)
        self.assertTrue(saved)
        self.assertEqual(self.db.get_total_count(), 1)

        recent = self.db.get_recent_records(limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["barcode"], "YT998877665")
        self.assertEqual(recent[0]["billable_weight_kg"], 5.0)

    def test_daily_summary_calculation(self):
        record = ParcelRecord()
        record.dimensions = Dimensions(length_mm=500.0, width_mm=400.0, height_mm=300.0)
        record.weight = WeightReading(gross_weight_kg=8.000, is_stable=True)
        record.calculate_weights(divisor=5000.0)  # Vol weight = 12.0 kg, delta = 4.0 kg
        record.status = "ACCEPTED"
        self.db.save_record(record)

        summary = self.db.get_daily_summary()
        self.assertEqual(summary["total_scans"], 1)
        self.assertEqual(summary["recovered_vol_kg"], 4.0)
        self.assertEqual(summary["recovered_revenue_inr"], 320.0)  # 4.0 * ₹80


class TestStaticDWSOrchestrator(unittest.IsolatedAsyncioTestCase):
    async def test_complete_auto_scan_cycle_accepted(self):
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = temp_db.name
        temp_db.close()
        orchestrator = StaticDWSOrchestrator(divisor=5000.0, db_path=db_path)
        
        pts = DimensionMeasurementEngine.generate_synthetic_parcel(400.0, 300.0, 200.0, num_points=250)
        barcode = "YT882910394"
        samples = [5.400, 5.402, 5.399, 5.401, 5.400]

        record = await orchestrator.process_static_scan(
            point_cloud=pts,
            barcode_input=barcode,
            consecutive_weight_samples=samples
        )

        self.assertEqual(record.status, "ACCEPTED")
        self.assertEqual(record.barcode.code, barcode)
        self.assertEqual(record.weight.gross_weight_kg, 5.400)
        self.assertAlmostEqual(record.dimensions.length_mm, 400.0, delta=4.0)
        self.assertEqual(orchestrator.get_total_count(), 1)
        if os.path.exists(db_path):
            os.unlink(db_path)

    async def test_hand_detection_blocks_scan(self):
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = temp_db.name
        temp_db.close()
        orchestrator = StaticDWSOrchestrator(divisor=5000.0, db_path=db_path)
        
        # Inject hand points
        pts_hand = DimensionMeasurementEngine.generate_synthetic_parcel(400.0, 300.0, 200.0, inject_hand=True)
        samples = [5.400, 5.402, 5.399, 5.401, 5.400]

        record = await orchestrator.process_static_scan(
            point_cloud=pts_hand,
            barcode_input="YT123456789",
            consecutive_weight_samples=samples
        )

        self.assertEqual(record.status, "HOLD_HAND_DETECTED")
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
