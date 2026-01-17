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
                # Try to ping the server
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

    def store_sensor_reading(self, sensor_type: str, value: float, unit: str, tags: dict = None):
        """
        Store a sensor reading in InfluxDB
        
        Args:
            sensor_type: Type of sensor (e.g., 'temperature', 'ammonia')
            value: Sensor reading value
            unit: Unit of measurement (e.g., 'C', 'ppm', '%')
            tags: Optional dictionary of additional tags
        """
        try:
            write_api = self._client.write_api(write_options=SYNCHRONOUS)
            
            point = Point("sensor_readings") \
                .tag("sensor_type", sensor_type) \
                .tag("unit", unit) \
                .field("value", float(value))
            
            # Add additional tags if provided
            if tags:
                for tag_key, tag_value in tags.items():
                    point = point.tag(tag_key, str(tag_value))
            
            write_api.write(bucket=self._bucket, org=self._org, record=point)
            self._logger.debug(f"Stored sensor reading: {sensor_type} = {value} {unit}")
        except Exception as e:
            self._logger.error(f"Error storing sensor reading: {e}")

    def store_data_from_topic(self, topic: str, payload: str):
        """
        Store data from MQTT topic
        
        Args:
            topic: MQTT topic (e.g., 'farm/sensor/temperature')
            payload: JSON payload string
        """
        try:
            import json
            data = json.loads(payload)
            
            # Extract sensor type from topic
            # Format: farm/sensor/{sensor_type}
            parts = topic.split("/")
            if len(parts) >= 3 and parts[0] == "farm" and parts[1] == "sensor":
                sensor_type = parts[2]
                value = data.get("value")
                unit = data.get("unit", "")
                
                if value is not None:
                    self.store_sensor_reading(sensor_type, value, unit)
        except Exception as e:
            self._logger.error(f"Error processing topic data: {e}")
