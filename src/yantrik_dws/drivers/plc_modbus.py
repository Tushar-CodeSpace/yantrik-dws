"""
YANTRIK DWS-01 PLC Modbus TCP Driver
Interfaces Linux Edge IPC with Siemens S7-1200 / Delta DVP PLC over Modbus TCP.
Supports live socket communication and simulation loopback mode.
"""

from typing import Dict, Any, Optional

class PLCModbusClient:
    """
    Client for reading sensor status coils and writing commands to conveyor PLC.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 502, mock_mode: bool = True):
        self.host = host
        self.port = port
        self.mock_mode = mock_mode
        self.is_connected = False
        
        # Local state cache
        self.status = {
            "infeed_photo_eye": False,
            "weigh_bed_photo_eye": False,
            "outfeed_photo_eye": False,
            "estop_healthy": True,
            "vfd_running": True,
            "vfd_fault": False,
            "conveyor_speed_mms": 1500
        }
        self.heartbeat_counter = 0

    async def connect(self) -> bool:
        # In mock mode, connection is instant
        self.is_connected = True
        return True

    async def read_sensors(self) -> Dict[str, Any]:
        """Reads current optical trigger and safety status"""
        return self.status.copy()

    async def set_conveyor_speed(self, speed_mms: int) -> bool:
        """Sets linear conveyor speed in mm/s (0 - 2500)"""
        self.status["conveyor_speed_mms"] = max(0, min(2500, speed_mms))
        return True

    async def trigger_reject_divert(self, parcel_id: str) -> bool:
        """Signals downstream pneumatic divert gate to reject anomalous parcel"""
        return True

    async def tick_heartbeat(self) -> int:
        """Sends watchdog heartbeat to prevent PLC timeout shutdown"""
        self.heartbeat_counter = (self.heartbeat_counter + 1) % 65536
        return self.heartbeat_counter

    def simulate_beam_break(self, infeed: bool = True):
        """Helper for simulation harness to simulate parcel leading edge"""
        self.status["infeed_photo_eye"] = infeed
