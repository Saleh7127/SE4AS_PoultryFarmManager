import threading
import logging
from Sensors import TemperatureSensor, AmmoniaSensor, FeedLevelSensor, WaterLevelSensor
from Actuators import Fan, Heater, Feeder, WaterValve

class PoultryBarn:
    """
    Poultry Barn manager that coordinates all sensors and actuators.
    Handles physics simulation and state management.
    Uses singleton pattern similar to reference project.
    """
    _instance = None
    _logger = None

    # Sensors
    _temperature_sensor: TemperatureSensor
    _ammonia_sensor: AmmoniaSensor
    _feed_level_sensor: FeedLevelSensor
    _water_level_sensor: WaterLevelSensor

    # Actuators
    _fan: Fan
    _heater: Heater
    _feeder: Feeder
    _water_valve: WaterValve

    _lock: threading.Lock

    def __new__(cls):
        if not hasattr(cls, '_instance') or cls._instance is None:
            cls._instance = super(PoultryBarn, cls).__new__(cls)
            cls._instance._init_barn()
        return cls._instance

    def _init_barn(self):
        """Initialize barn with sensors and actuators"""
        self._logger = logging.getLogger("PoultryBarn")
        self._lock = threading.Lock()

        # Initialize sensors with default values
        self._temperature_sensor = TemperatureSensor(initial_temp=22.0)
        self._ammonia_sensor = AmmoniaSensor(initial_ammonia=5.0)
        self._feed_level_sensor = FeedLevelSensor(initial_level=50.0)
        self._water_level_sensor = WaterLevelSensor(initial_level=50.0)

        # Initialize actuators
        self._fan = Fan(initial_state=False)
        self._heater = Heater(initial_state=False)
        self._feeder = Feeder(initial_state=False)
        self._water_valve = WaterValve(initial_state=False)

        self._logger.info("PoultryBarn initialized with all sensors and actuators")

    def get_temperature_sensor(self) -> TemperatureSensor:
        """Get temperature sensor instance"""
        return self._temperature_sensor

    def get_ammonia_sensor(self) -> AmmoniaSensor:
        """Get ammonia sensor instance"""
        return self._ammonia_sensor

    def get_feed_level_sensor(self) -> FeedLevelSensor:
        """Get feed level sensor instance"""
        return self._feed_level_sensor

    def get_water_level_sensor(self) -> WaterLevelSensor:
        """Get water level sensor instance"""
        return self._water_level_sensor

    def get_fan(self) -> Fan:
        """Get fan actuator instance"""
        return self._fan

    def get_heater(self) -> Heater:
        """Get heater actuator instance"""
        return self._heater

    def get_feeder(self) -> Feeder:
        """Get feeder actuator instance"""
        return self._feeder

    def get_water_valve(self) -> WaterValve:
        """Get water valve actuator instance"""
        return self._water_valve

    def update_physics(self):
        """
        Update barn physics based on actuator states.
        Updates sensor readings based on actuator effects.
        """
        with self._lock:
            # Get current sensor readings
            current_temp = self._temperature_sensor.get_reading()
            current_ammonia = self._ammonia_sensor.get_reading()
            current_feed = self._feed_level_sensor.get_reading()
            current_water = self._water_level_sensor.get_reading()

            # Apply actuator effects
            # Temperature physics
            temp_change = 0.0
            if self._fan.is_on():
                temp_change += self._fan.get_temperature_effect()
            if self._heater.is_on():
                temp_change += self._heater.get_temperature_effect()
            
            # Natural cooling if no active temperature control
            if not self._fan.is_on() and not self._heater.is_on():
                if current_temp > 15.0:
                    temp_change -= 0.05  # Natural cooling
            
            new_temp = current_temp + temp_change
            self._temperature_sensor.update_reading(new_temp)

            # Ammonia physics
            ammonia_change = 0.0
            if self._fan.is_on():
                ammonia_change += self._fan.get_ammonia_effect()  # Fan reduces ammonia
            else:
                ammonia_change += 0.1  # Natural accumulation
            
            new_ammonia = max(0.0, current_ammonia + ammonia_change)
            self._ammonia_sensor.update_reading(new_ammonia)

            # Feed level physics
            feed_change = 0.0
            if self._feeder.is_active():
                feed_change += self._feeder.get_feed_effect()  # Feeder adds feed
            else:
                feed_change -= 0.1  # Natural consumption

            new_feed = max(0.0, min(100.0, current_feed + feed_change))
            self._feed_level_sensor.update_reading(new_feed)

            # Water level physics
            water_change = 0.0
            if self._water_valve.is_open():
                water_change += self._water_valve.get_water_effect()  # Valve adds water
            else:
                water_change -= 0.1  # Natural consumption

            new_water = max(0.0, min(100.0, current_water + water_change))
            self._water_level_sensor.update_reading(new_water)

    def simulate_all_sensors(self, client):
        """
        Simulate all sensor readings and publish to MQTT
        """
        self._temperature_sensor.simulate(client)
        self._ammonia_sensor.simulate(client)
        self._feed_level_sensor.simulate(client)
        self._water_level_sensor.simulate(client)

