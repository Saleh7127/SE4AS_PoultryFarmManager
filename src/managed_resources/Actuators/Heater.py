import logging
from paho.mqtt.client import Client

class Heater:
    """
    Heater actuator for temperature control.
    Increases temperature when active.
    """
    _is_on: bool
    _logger: logging.Logger

    def __init__(self, initial_state=False):
        self._is_on = initial_state
        self._logger = logging.getLogger(f"{__name__}.Heater")

    def is_on(self) -> bool:
        """Check if heater is currently on"""
        return self._is_on

    def turn_on(self):
        """Turn heater on"""
        self._is_on = True
        self._logger.info("Heater turned ON")

    def turn_off(self):
        """Turn heater off"""
        self._is_on = False
        self._logger.info("Heater turned OFF")

    def set_state(self, state: bool):
        """Set heater state"""
        if state:
            self.turn_on()
        else:
            self.turn_off()

    def get_temperature_effect(self) -> float:
        """
        Get temperature change effect when heater is on.
        Returns positive value to increase temperature.
        """
        return 0.5 if self._is_on else 0.0

