import random
import json
from paho.mqtt.client import Client
import logging

class FeedLevelSensor:
    """
    Feed level sensor for monitoring feed availability in the barn.
    Simulates feed level percentage readings.
    """
    _feed_level: float
    _logger: logging.Logger

    def __init__(self, initial_level=50.0):
        self._feed_level = initial_level
        self._logger = logging.getLogger(f"{__name__}.FeedLevelSensor")

    def get_reading(self) -> float:
        """Get current feed level reading"""
        return self._feed_level

    def update_reading(self, new_level: float):
        """Update feed level reading"""
        self._feed_level = max(0.0, min(100.0, new_level))  # Clamp between 0-100%

    def add_noise(self, noise_range=0.2):
        """Add small random noise to simulate sensor accuracy"""
        noise = random.uniform(-noise_range, noise_range)
        self._feed_level += noise
        self._feed_level = max(0.0, min(100.0, self._feed_level))

    def simulate(self, client: Client):
        """
        Simulate feed level sensor reading and publish to MQTT
        """
        # Add small random noise for realism
        self.add_noise(0.1)
        
        topic = "farm/sensor/feed_level"
        payload = {
            "value": round(self._feed_level, 2),
            "unit": "%"
        }
        
        client.publish(topic, json.dumps(payload))
        self._logger.debug(f"Published feed level: {self._feed_level:.2f}%")

