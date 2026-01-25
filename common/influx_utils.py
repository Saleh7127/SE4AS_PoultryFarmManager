import os
from influxdb_client import InfluxDBClient

INFLUXDB_URL = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_ADMIN_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET")

def create_influx_client() -> InfluxDBClient:
    if not INFLUXDB_URL or not INFLUXDB_TOKEN or not INFLUXDB_ORG:
        raise RuntimeError("InfluxDB env vars not set correctly")
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
