"""
YANTRIK DWS-01 Mock Scale Simulator
Generates synthetic continuous RS-232 / RS-485 serial data streams
simulating industrial digital weighing indicators with mechanical noise and settling times.
"""

import random
import time
from typing import Generator

class MockScaleSimulator:
    def __init__(self, base_weight_kg: float = 2.500, noise_amplitude_kg: float = 0.015):
        self.base_weight_kg = base_weight_kg
        self.noise_amplitude_kg = noise_amplitude_kg

    def generate_streaming_line(self, is_stable: bool = True) -> str:
        """
        Generates a standard ASCII frame:
        Example: 'ST,GS,+002.504,kg\\r\\n'
        """
        status = "ST" if is_stable else "US"
        noise = random.gauss(0, self.noise_amplitude_kg)
        current = max(0.0, self.base_weight_kg + noise)
        sign = "+" if current >= 0 else "-"
        weight_str = f"{sign}{current:07.3f}"
        return f"{status},GS,{weight_str},kg\r\n"

    def simulate_parcel_settling(self, target_weight_kg: float, steps: int = 5) -> Generator[str, None, None]:
        """
        Simulates the mechanical settling curve when a package is placed onto the platform scale.
        Yields unsteady frames followed by locked stable frames.
        """
        # Phase 1: Impact / oscillation (Unstable)
        for i in range(steps):
            oscillation = (steps - i) * 0.15 * random.choice([-1, 1])
            yield self.generate_streaming_line(is_stable=False)

        # Phase 2: Settled (Stable)
        self.base_weight_kg = target_weight_kg
        for _ in range(3):
            yield self.generate_streaming_line(is_stable=True)
