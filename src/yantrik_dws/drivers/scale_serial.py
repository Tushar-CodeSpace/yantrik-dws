"""
YANTRIK DWS-01 Scale Serial Driver & Digital Filter
Parses continuous serial streams from digital load cell summing indicators (RS-232/RS-485)
and implements vibration noise filtering and stability detection.
"""

import re
from typing import Optional, List
from collections import deque
try:
    from yantrik_dws.models import WeightReading
except ImportError:
    from ..models import WeightReading

class ScaleSerialParser:
    """
    Parses standard industrial scale serial frames.
    Format: <Status>,<Type>,<Sign><Weight>,<Unit>
    Example: 'ST,GS,+002.450,kg\\r\\n'
    """
    # Regex matching: ST,GS,+001.450,kg or US,GS,+001.450,kg
    PATTERN = re.compile(r"(ST|US|OL),(GS|NT),([+-]?\d+\.?\d*),(kg|g|lb)")

    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self.samples = deque(maxlen=window_size)
        self.tare_weight_kg = 0.0

    def parse_frame(self, raw_line: str) -> Optional[WeightReading]:
        clean = raw_line.strip()
        match = self.PATTERN.search(clean)
        if not match:
            return None

        status_str, type_str, weight_str, unit_str = match.groups()
        try:
            val = float(weight_str)
            # Normalize to kg
            if unit_str == "g":
                val = val / 1000.0
            elif unit_str == "lb":
                val = val * 0.453592
        except ValueError:
            return None

        is_stable = (status_str == "ST")
        
        # When stable lock (ST) is signaled by hardware indicator, use certified stable value
        if is_stable:
            self.samples.clear()
            self.samples.append(val)
            filtered_weight = val
        else:
            # Apply moving median filter for dynamic vibration damping during settling
            self.samples.append(val)
            filtered_weight = self._get_filtered_weight()

        return WeightReading(
            gross_weight_kg=round(filtered_weight, 3),
            is_stable=is_stable,
            tare_weight_kg=self.tare_weight_kg
        )

    def _get_filtered_weight(self) -> float:
        if not self.samples:
            return 0.0
        # Median filter to eliminate mechanical spike noise
        sorted_samples = sorted(self.samples)
        mid = len(sorted_samples) // 2
        return sorted_samples[mid]

    def set_tare(self, tare_val: float):
        self.tare_weight_kg = tare_val

    def reset_filter(self):
        self.samples.clear()

    @staticmethod
    def evaluate_5sample_stability(samples: List[float], max_fluctuation_kg: float = 0.010):
        """
        Founder's Auto-Scan Rule:
        Evaluates the last 5 consecutive weight samples. If the fluctuation between
        maximum and minimum reading is <= 10g (0.010 kg), the reading is certified valid and stable.
        Returns: (is_stable: bool, locked_weight_kg: float, delta_kg: float)
        """
        if not samples or len(samples) < 5:
            val = samples[-1] if samples else 0.0
            return False, val, 999.0

        window = samples[-5:]
        min_w = min(window)
        max_w = max(window)
        delta = round(max_w - min_w, 4)

        is_stable = delta <= max_fluctuation_kg
        locked_weight = round(sum(window) / 5.0, 3)
        return is_stable, locked_weight, delta
