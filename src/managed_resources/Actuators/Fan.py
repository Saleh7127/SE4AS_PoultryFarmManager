import logging
from paho.mqtt.client import Client

class Fan:
    """
    Fan actuator for temperature and air quality control.
    Reduces temperature and ammonia levels when active.
    """
    _is_on: bool
    _logger: logging.Logger

    def __init__(self, initial_state=False):
        self._is_on = initial_state
        self._logger = logging.getLogger(f"{__name__}.Fan")

    def is_on(self) -> bool:
        """Check if fan is currently on"""
        return self._is_on

    def turn_on(self):
        """Turn fan on"""
        self._is_on = True
        self._logger.info("Fan turned ON")

    def turn_off(self):
        """Turn fan off"""
        self._is_on = False
        self._logger.info("Fan turned OFF")

    def set_state(self, state: bool):
        """Set fan state"""
        if state:
            self.turn_on()
        else:
            self.turn_off()

    def get_temperature_effect(self) -> float:
        """
        Get temperature change effect when fan is on.
        Returns negative value to reduce temperature.
        """
        return -0.5 if self._is_on else 0.0

    def get_ammonia_effect(self) -> float:
        """
        Get ammonia reduction effect when fan is on.
        Returns negative value to reduce ammonia.
        """
        return -1.0 if self._is_on else 0.0

