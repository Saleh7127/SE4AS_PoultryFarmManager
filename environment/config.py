import os

FARM_ID = os.getenv("FARM_ID", "farm1")
ZONE_ID = os.getenv("ZONE_ID", "zone1")
SENSOR_INTERVAL_S = float(os.getenv("SENSOR_INTERVAL_S", 5))
