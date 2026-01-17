import random
import json
from paho.mqtt.client import Client
import logging

class WaterLevelSensor:
    """
    Water level sensor for monitoring water availability in the barn.
    Simulates water level percentage readings.
    """
    _water_level: float
    _logger: logging.Logger

    def __init__(self, initial_level=50.0):
        self._water_level = initial_level
        self._logger = logging.getLogger(f"{__name__}.WaterLevelSensor")

    def get_reading(self) -> float:
        """Get current water level reading"""
        return self._water_level

    def update_reading(self, new_level: float):
        """Update water level reading"""
        self._water_level = max(0.0, min(100.0, new_level))  # Clamp between 0-100%

    def add_noise(self, noise_range=0.2):
        """Add small random noise to simulate sensor accuracy"""
        noise = random.uniform(-noise_range, noise_range)
        self._water_level += noise
        self._water_level = max(0.0, min(100.0, self._water_level))

    def simulate(self, client: Client):
        """
        Simulate water level sensor reading and publish to MQTT
        """
        # Add small random noise for realism
        self.add_noise(0.1)
        
        topic = "farm/sensor/water_level"
        payload = {
            "value": round(self._water_level, 2),
            "unit": "%"
        }
        
        client.publish(topic, json.dumps(payload))
        self._logger.debug(f"Published water level: {self._water_level:.2f}%")

