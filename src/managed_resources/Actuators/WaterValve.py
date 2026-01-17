import logging
from paho.mqtt.client import Client

class WaterValve:
    """
    Water valve actuator for controlling water supply.
    Increases water level when open.
    """
    _is_open: bool
    _fill_rate: float
    _logger: logging.Logger

    def __init__(self, initial_state=False):
        self._is_open = initial_state
        self._fill_rate = 5.0  # Default fill rate per cycle
        self._logger = logging.getLogger(f"{__name__}.WaterValve")

    def is_open(self) -> bool:
        """Check if water valve is currently open"""
        return self._is_open

    def open(self):
        """Open water valve"""
        self._is_open = True
        self._logger.info("Water valve opened")

    def close(self):
        """Close water valve"""
        self._is_open = False
        self._logger.info("Water valve closed")

    def set_state(self, state: bool):
        """Set water valve state"""
        if state:
            self.open()
        else:
            self.close()

    def get_water_effect(self) -> float:
        """
        Get water level increase effect when valve is open.
        Returns positive value to increase water level.
        """
        return self._fill_rate if self._is_open else 0.0

