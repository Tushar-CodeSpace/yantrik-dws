"""
YANTRIK DWS-01 Data Models & Schemas
Defines core domain objects, parcel measurements, and database entities.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid

@dataclass
class Dimensions:
    length_mm: float
    width_mm: float
    height_mm: float
    volume_cm3: float = field(init=False)
    is_irregular: bool = False
    confidence_score: float = 1.0

    def __post_init__(self):
        self.volume_cm3 = round((self.length_mm * self.width_mm * self.height_mm) / 1000.0, 2)

@dataclass
class WeightReading:
    gross_weight_kg: float
    is_stable: bool = True
    tare_weight_kg: float = 0.0

@dataclass
class BarcodeResult:
    code: str
    symbology: str = "CODE128"
    read_success: bool = True

@dataclass
class ParcelRecord:
    parcel_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dimensions: Optional[Dimensions] = None
    weight: Optional[WeightReading] = None
    barcode: Optional[BarcodeResult] = None
    volumetric_weight_kg: float = 0.0
    billable_weight_kg: float = 0.0
    status: str = "ACCEPTED"  # ACCEPTED, RECHECK_REQUIRED, REJECTED
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_weights(self, divisor: float = 5000.0):
        """Calculate volumetric and billable weight based on standard logistics divisor (5000 cm3/kg)"""
        if self.dimensions:
            # L(cm) * W(cm) * H(cm) / 5000
            l_cm = self.dimensions.length_mm / 10.0
            w_cm = self.dimensions.width_mm / 10.0
            h_cm = self.dimensions.height_mm / 10.0
            self.volumetric_weight_kg = round((l_cm * w_cm * h_cm) / divisor, 3)
        
        gross = self.weight.gross_weight_kg if self.weight else 0.0
        self.billable_weight_kg = max(gross, self.volumetric_weight_kg)
        return self.billable_weight_kg

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data
