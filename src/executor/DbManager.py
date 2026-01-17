import influxdb_client
import os
import time
import logging
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

class DbManager:
    _instance = None
    _client = None
    _token = None
    _org = None
    _bucket = None
    _url = None
    _logger = None

    def __new__(cls):
        if not hasattr(cls, '_instance') or cls._instance is None:
            cls._instance = super(DbManager, cls).__new__(cls)
            cls._instance._logger = logging.getLogger("DbManager")
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        self._url = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
        self._token = os.getenv("INFLUXDB_TOKEN", "poultryfarmtoken")
        self._org = os.getenv("INFLUXDB_ORG", "poultry_farm")
        self._bucket = os.getenv("INFLUXDB_BUCKET", "poultry_farm")
        
        self._wait_for_influxdb()
        
        self._client = InfluxDBClient(url=self._url, token=self._token, org=self._org)
        self._logger.info(f"Connected to InfluxDB at {self._url}")

    def _wait_for_influxdb(self):
        retries = 30
        while retries > 0:
            try:
                test_client = InfluxDBClient(url=self._url, token=self._token, org=self._org, timeout=5000)
                if test_client.ping():
                    self._logger.info("InfluxDB is ready")
                    test_client.close()
                    return
                test_client.close()
            except Exception as e:
                if retries % 5 == 0:  # Log every 5 retries to reduce log spam
                    self._logger.warning(f"InfluxDB not ready yet. Retrying... ({retries} retries left)")
                time.sleep(2)
                retries -= 1
        
        raise Exception("Could not connect to InfluxDB after multiple retries")

    def store_actuator_log(self, actuator_type: str, action: str, details: str = None, tags: dict = None):
        """
        Store an actuator action log in InfluxDB
        
        Args:
            actuator_type: Type of actuator (e.g., 'fan', 'heater')
            action: Action performed (e.g., 'ON', 'OFF', 'DISPENSE')
            details: Optional JSON string with additional details
            tags: Optional dictionary of additional tags
        """
        try:
            write_api = self._client.write_api(write_options=SYNCHRONOUS)
            
            point = Point("actuator_logs") \
                .tag("actuator_type", actuator_type) \
                .tag("action", action) \
                .field("value", 1.0)  # Use 1.0 as a flag value
            
            if details:
                point = point.field("details", details)
            
            # Add additional tags if provided
            if tags:
                for tag_key, tag_value in tags.items():
                    point = point.tag(tag_key, str(tag_value))
            
            write_api.write(bucket=self._bucket, org=self._org, record=point)
            self._logger.debug(f"Stored actuator log: {actuator_type} -> {action}")
        except Exception as e:
            self._logger.error(f"Error storing actuator log: {e}")

    def add_actuator_log(self, log_data: dict):
        """
        Add actuator log from dictionary (backward compatibility)
        
        Args:
            log_data: Dictionary with keys: timestamp, actuator_type, action, details
        """
        actuator_type = log_data.get("actuator_type")
        action = log_data.get("action")
        details = log_data.get("details")
        
        if actuator_type and action:
            self.store_actuator_log(actuator_type, action, details)
