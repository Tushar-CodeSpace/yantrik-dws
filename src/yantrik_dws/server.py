#!/usr/bin/env python3
"""
YANTRIK DWS-S01 Zero-Dependency Embedded Edge Server
Runs natively using Python's standard library (http.server) with zero external pip dependencies.
Serves the operator touchscreen HMI and provides local REST APIs for parcel intake,
SQLite persistence, optical clearance checking, and 5-sample weight stability validation.
"""

import http.server
import json
import os
import sys
import urllib.parse
from typing import Dict, Any

# Ensure src root is in path
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

try:
    from yantrik_dws.services.event_orchestrator import StaticDWSOrchestrator
    from yantrik_dws.vision.dimensioner import DimensionMeasurementEngine
    from yantrik_dws.database.sqlite_manager import SQLiteAuditDatabase
except ImportError:
    from services.event_orchestrator import StaticDWSOrchestrator
    from vision.dimensioner import DimensionMeasurementEngine
    from database.sqlite_manager import SQLiteAuditDatabase

# Initialize Core Services
orchestrator = StaticDWSOrchestrator()
db = orchestrator.db
FRONTEND_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "ui/index.html"))


class YantrikDWSHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Concise logging
        sys.stderr.write(f"[YANTRIK-HTTP] {args[0]} - {args[1]}\n")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Serve Touchscreen HMI at root
        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(FRONTEND_FILE, "rb") as f:
                self.wfile.write(f.read())
            return

        # 2. API Health Check
        elif path == "/api/v1/health":
            self.send_json_response(200, {
                "status": "HEALTHY",
                "system": "YANTRIK DWS-S01 Static Workstation",
                "db_engine": "SQLite WAL Mode",
                "total_records_stored": db.get_total_count()
            })
            return

        # 3. API Summary
        elif path == "/api/v1/summary":
            summary = db.get_daily_summary()
            self.send_json_response(200, summary)
            return

        # 4. API Recent Parcels
        elif path == "/api/v1/parcels":
            records = db.get_recent_records(limit=25)
            self.send_json_response(200, records)
            return

        # Fallback to default file serving
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        if path == "/api/v1/scan":
            # Extract scan parameters or apply simulated defaults
            l = float(body.get("length_mm", 380.0))
            w = float(body.get("width_mm", 260.0))
            h = float(body.get("height_mm", 180.0))
            gross_wt = float(body.get("gross_weight_kg", 2.450))
            barcode = body.get("barcode", "YT882910394")
            inject_hand = bool(body.get("inject_hand", False))

            # Generate synthetic point cloud (with optional hand interference)
            pt_cloud = DimensionMeasurementEngine.generate_synthetic_parcel(
                length_mm=l, width_mm=w, height_mm=h, inject_hand=inject_hand
            )

            # Generate 5 consecutive weight readings
            fluctuation = float(body.get("fluctuation_g", 4.0)) / 1000.0
            import random
            samples = [round(gross_wt + random.uniform(-fluctuation, fluctuation), 3) for _ in range(5)]

            # Run synchronous orchestrator cycle
            import asyncio
            record = asyncio.run(orchestrator.process_static_scan(
                point_cloud=pt_cloud,
                barcode_input=barcode,
                consecutive_weight_samples=samples
            ))

            self.send_json_response(200, record.to_dict())
            return

        self.send_response(404)
        self.end_headers()

    def send_json_response(self, code: int, data: Dict[str, Any]):
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)


def run_server(port: int = 8000):
    server_address = ("0.0.0.0", port)
    httpd = http.server.ThreadingHTTPServer(server_address, YantrikDWSHandler)
    print("======================================================================")
    print(f"      YANTRIK DWS-S01 INDUSTRIAL EDGE SERVER (PORT {port})          ")
    print("======================================================================")
    print(f"  ● Operator Touchscreen HMI:  http://localhost:{port}/")
    print(f"  ● Local SQLite Database:     {db.db_path}")
    print(f"  ● REST API Endpoint:         http://localhost:{port}/api/v1/scan")
    print("----------------------------------------------------------------------")
    print("  Ready for parcel intake. Press Ctrl+C to terminate.")
    print("======================================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[YANTRIK] Edge server gracefully stopped.")


if __name__ == "__main__":
    port = int(os.environ.get("YANTRIK_PORT", 8000))
    run_server(port)
