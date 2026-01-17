import logging
from paho.mqtt.client import Client

class Feeder:
    """
    Feeder actuator for dispensing feed.
    Increases feed level when active.
    """
    _is_active: bool
    _dispense_amount: float
    _logger: logging.Logger

    def __init__(self, initial_state=False):
        self._is_active = initial_state
        self._dispense_amount = 10.0  # Default amount per dispense cycle
        self._logger = logging.getLogger(f"{__name__}.Feeder")

    def is_active(self) -> bool:
        """Check if feeder is currently active"""
        return self._is_active

    def activate(self, amount: float = None):
        """Activate feeder to dispense feed"""
        if amount is not None:
            self._dispense_amount = amount
        self._is_active = True
        self._logger.info(f"Feeder activated (amount: {self._dispense_amount})")

    def deactivate(self):
        """Deactivate feeder"""
        self._is_active = False
        self._logger.info("Feeder deactivated")

    def set_state(self, state: bool, amount: float = None):
        """Set feeder state"""
        if state:
            self.activate(amount)
        else:
            self.deactivate()

    def get_feed_effect(self) -> float:
        """
        Get feed level increase effect when feeder is active.
        Returns positive value to increase feed level.
        """
        return self._dispense_amount if self._is_active else 0.0

