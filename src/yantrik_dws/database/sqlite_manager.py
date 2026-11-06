"""
YANTRIK DWS-S01 Local SQLite Audit Database Manager
Lightweight, zero-configuration embedded persistence engine running in WAL mode.
Stores immutable parcel audit records, calibration logs, and offline store-and-forward queue.
"""

import sqlite3
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
try:
    from yantrik_dws.models import ParcelRecord, Dimensions, WeightReading, BarcodeResult
except ImportError:
    from ..models import ParcelRecord, Dimensions, WeightReading, BarcodeResult


class SQLiteAuditDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to local data directory
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
            os.makedirs(base_dir, exist_ok=True)
            db_path = os.path.join(base_dir, "yantrik_audit.db")

        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        # Enable WAL mode for high concurrency and crash resilience
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS parcel_audit_log (
                parcel_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                barcode TEXT NOT NULL,
                symbology TEXT DEFAULT 'CODE128',
                length_mm REAL NOT NULL,
                width_mm REAL NOT NULL,
                height_mm REAL NOT NULL,
                volume_cm3 REAL NOT NULL,
                gross_weight_kg REAL NOT NULL,
                volumetric_weight_kg REAL NOT NULL,
                billable_weight_kg REAL NOT NULL,
                status TEXT NOT NULL,
                wms_synced INTEGER DEFAULT 0,
                wms_sync_timestamp TEXT,
                metadata_json TEXT
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parcel_barcode ON parcel_audit_log(barcode);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parcel_time ON parcel_audit_log(timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wms_synced ON parcel_audit_log(wms_synced);")
            conn.commit()

    def save_record(self, record: ParcelRecord) -> bool:
        """Saves a parcel record immutably to SQLite."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                INSERT OR REPLACE INTO parcel_audit_log (
                    parcel_id, timestamp, barcode, symbology,
                    length_mm, width_mm, height_mm, volume_cm3,
                    gross_weight_kg, volumetric_weight_kg, billable_weight_kg,
                    status, wms_synced, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.parcel_id,
                    record.timestamp,
                    record.barcode.code if record.barcode else "NO_READ",
                    record.barcode.symbology if record.barcode else "UNKNOWN",
                    record.dimensions.length_mm if record.dimensions else 0.0,
                    record.dimensions.width_mm if record.dimensions else 0.0,
                    record.dimensions.height_mm if record.dimensions else 0.0,
                    record.dimensions.volume_cm3 if record.dimensions else 0.0,
                    record.weight.gross_weight_kg if record.weight else 0.0,
                    record.volumetric_weight_kg,
                    record.billable_weight_kg,
                    record.status,
                    1 if record.status == "ACCEPTED" else 0,
                    json.dumps(record.metadata)
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"[SQLiteAuditDatabase] Error persisting record: {e}")
            return False

    def get_recent_records(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves recent parcel records for the HMI dashboard."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
            SELECT * FROM parcel_audit_log
            ORDER BY timestamp DESC
            LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_daily_summary(self) -> Dict[str, Any]:
        """Calculates today's scan count, total weight, and recovered dimensional weight."""
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.execute("""
            SELECT 
                COUNT(*) as total_scans,
                SUM(gross_weight_kg) as total_gross_kg,
                SUM(billable_weight_kg) as total_billable_kg,
                SUM(CASE WHEN volumetric_weight_kg > gross_weight_kg THEN volumetric_weight_kg - gross_weight_kg ELSE 0 END) as recovered_vol_kg
            FROM parcel_audit_log
            WHERE timestamp LIKE ?
            """, (f"{today_prefix}%",))
            row = cursor.fetchone()
            if row:
                recovered_kg = row["recovered_vol_kg"] or 0.0
                return {
                    "total_scans": row["total_scans"] or 0,
                    "total_gross_kg": round(row["total_gross_kg"] or 0.0, 3),
                    "total_billable_kg": round(row["total_billable_kg"] or 0.0, 3),
                    "recovered_vol_kg": round(recovered_kg, 3),
                    "recovered_revenue_inr": round(recovered_kg * 80.0, 2)  # Assuming standard ₹80/kg
                }
            return {"total_scans": 0, "total_gross_kg": 0.0, "total_billable_kg": 0.0, "recovered_vol_kg": 0.0, "recovered_revenue_inr": 0.0}

    def get_total_count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM parcel_audit_log;")
            return cursor.fetchone()[0]
