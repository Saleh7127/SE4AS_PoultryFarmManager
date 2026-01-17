import random
import json
from paho.mqtt.client import Client
import logging

class TemperatureSensor:
    """
    Temperature sensor for monitoring barn temperature.
    Simulates temperature readings with physics-based updates.
    """
    _temperature: float
    _logger: logging.Logger

    def __init__(self, initial_temp=22.0):
        self._temperature = initial_temp
        self._logger = logging.getLogger(f"{__name__}.TemperatureSensor")

    def get_reading(self) -> float:
        """Get current temperature reading"""
        return self._temperature

    def update_reading(self, new_temp: float):
        """Update temperature reading"""
        self._temperature = max(0.0, min(50.0, new_temp))  # Clamp between 0-50°C

    def add_noise(self, noise_range=0.2):
        """Add small random noise to simulate sensor accuracy"""
        noise = random.uniform(-noise_range, noise_range)
        self._temperature += noise
        self._temperature = max(0.0, min(50.0, self._temperature))

    def simulate(self, client: Client):
        """
        Simulate temperature sensor reading and publish to MQTT
        """
        # Add small random noise for realism
        self.add_noise(0.1)
        
        topic = "farm/sensor/temperature"
        payload = {
            "value": round(self._temperature, 2),
            "unit": "C"
        }
        
        client.publish(topic, json.dumps(payload))
        self._logger.debug(f"Published temperature: {self._temperature:.2f}°C")

