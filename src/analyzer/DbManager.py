import influxdb_client
import os
import time
import logging
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.query_api import QueryApi

class SensorReading:
    """Data class for sensor readings"""
    def __init__(self, timestamp, sensor_type, value, unit):
        self.timestamp = timestamp
        self.sensor_type = sensor_type
        self.value = value
        self.unit = unit

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

    def get_latest_sensor_reading(self, sensor_type: str):
        """
        Get the latest sensor reading for a specific sensor type
        
        Args:
            sensor_type: Type of sensor (e.g., 'temperature', 'ammonia')
            
        Returns:
            SensorReading object or None if not found
        """
        try:
            query_api = self._client.query_api()
            
            # Flux query to get the latest reading for a sensor type
            query = f'''
            from(bucket: "{self._bucket}")
              |> range(start: -7d)
              |> filter(fn: (r) => r["_measurement"] == "sensor_readings")
              |> filter(fn: (r) => r["sensor_type"] == "{sensor_type}")
              |> filter(fn: (r) => r["_field"] == "value")
              |> last()
            '''
            
            result = query_api.query(org=self._org, query=query)
            
            for table in result:
                for record in table.records:
                    # Extract unit from tags
                    unit = record.values.get("unit", "")
                    return SensorReading(
                        timestamp=record.get_time(),
                        sensor_type=sensor_type,
                        value=float(record.get_value()),
                        unit=unit
                    )
            
            return None
        except Exception as e:
            self._logger.error(f"Error querying sensor reading: {e}")
            return None

    def get_sensor_readings_by_type(self, sensor_types: list):
        """
        Get latest readings for multiple sensor types
        
        Args:
            sensor_types: List of sensor type strings
            
        Returns:
            Dictionary mapping sensor_type to SensorReading
        """
        readings = {}
        for sensor_type in sensor_types:
            reading = self.get_latest_sensor_reading(sensor_type)
            if reading:
                readings[sensor_type] = reading
        return readings

    # Keep Session for backward compatibility (not used anymore but kept for interface)
    @property
    def Session(self):
        """Backward compatibility - returns a mock session object"""
        class Session:
            def __init__(self, db_manager):
                self.db_manager = db_manager
            
            def __enter__(self):
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
            
            def query(self, model):
                # This is not used anymore - we use get_latest_sensor_reading instead
                return None
            
            def close(self):
                pass
        return Session(self)
