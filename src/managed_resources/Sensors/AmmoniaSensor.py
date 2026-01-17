import random
import json
from paho.mqtt.client import Client
import logging

class AmmoniaSensor:
    """
    Ammonia sensor for monitoring air quality in the barn.
    Simulates ammonia concentration readings.
    """
    _ammonia: float
    _logger: logging.Logger

    def __init__(self, initial_ammonia=5.0):
        self._ammonia = initial_ammonia
        self._logger = logging.getLogger(f"{__name__}.AmmoniaSensor")

    def get_reading(self) -> float:
        """Get current ammonia reading"""
        return self._ammonia

    def update_reading(self, new_ammonia: float):
        """Update ammonia reading"""
        self._ammonia = max(0.0, min(100.0, new_ammonia))  # Clamp between 0-100 ppm

    def add_noise(self, noise_range=0.1):
        """Add small random noise to simulate sensor accuracy"""
        noise = random.uniform(-noise_range, noise_range)
        self._ammonia += noise
        self._ammonia = max(0.0, min(100.0, self._ammonia))

    def simulate(self, client: Client):
        """
        Simulate ammonia sensor reading and publish to MQTT
        """
        # Add small random noise for realism
        self.add_noise(0.05)
        
        topic = "farm/sensor/ammonia"
        payload = {
            "value": round(self._ammonia, 2),
            "unit": "ppm"
        }
        
        client.publish(topic, json.dumps(payload))
        self._logger.debug(f"Published ammonia: {self._ammonia:.2f} ppm")

