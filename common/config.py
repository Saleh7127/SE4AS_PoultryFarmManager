import os
import json

SENSOR_MEASUREMENT = "sensors"
ACTUATOR_MEASUREMENT = "actuator_commands"
SYMPTOM_MEASUREMENT = "symptoms"
PLAN_MEASUREMENT = "plans"

INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "farm-bucket")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "farm-org")


def load_system_config(path="system_config.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading system config from {path}: {e}")
        return {"farms": []}

def get_config(key: str, system_config: dict, farm_id: str = None, zone_id: str = None, default=None):
    """
    Retrieve config value with precedence:
    1. Zone-specific config (in system_config)
    2. Farm-specific config (not yet fully implemented in schema but supported here)
    3. Global defaults (in system_config['defaults'])
    4. Hardcoded DEFAULTS
    """
    if farm_id and zone_id:
        for farm in system_config.get("farms", []):
            if farm["id"] == farm_id:
                for z in farm.get("zones", []):
                    if isinstance(z, dict) and z.get("id") == zone_id:
                        if "config" in z and key in z["config"]:
                            return z["config"][key]
                    elif z == zone_id:
                        if "config" in farm and key in farm["config"]:
                            return farm["config"][key]
                
                if "config" in farm and key in farm["config"]:
                    return farm["config"][key]

    if "defaults" in system_config and key in system_config["defaults"]:
        return system_config["defaults"][key]

    return default
