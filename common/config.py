import os

FARM_ID = os.getenv("FARM_ID", "farm1")
ZONE_ID = os.getenv("ZONE_ID", "zone1")

# --- TEMPERATURE / AIR QUALITY ---
TEMP_MIN = float(os.getenv("TEMP_MIN", 24))          # demo: higher so heater is relevant
TEMP_MAX = float(os.getenv("TEMP_MAX", 28))
TEMP_SETPOINT = float(os.getenv("TEMP_SETPOINT", 26))

NH3_THRESHOLD = float(os.getenv("NH3_THRESHOLD", 25))

# CO2 (ppm)
CO2_SETPOINT = float(os.getenv("CO2_SETPOINT", 1500))
CO2_MAX = float(os.getenv("CO2_MAX", 3000))

# Fan controller gains (demo-tuned so fan moves a lot)
FAN_KP_TEMP = float(os.getenv("FAN_KP_TEMP", 10.0))    # % per °C
FAN_KP_CO2 = float(os.getenv("FAN_KP_CO2", 0.02))      # % per ppm
FAN_MAX = float(os.getenv("FAN_MAX", 100.0))
FAN_MIN = float(os.getenv("FAN_MIN", 0.0))

# Minimum fan when heater ON (avoid stale air)
HEATER_MIN_FAN = float(os.getenv("HEATER_MIN_FAN", 20.0))

# --- FEED & WATER ---
FEED_THRESHOLD = float(os.getenv("FEED_THRESHOLD", 1.5))         # kg (top-up threshold)
FEED_EMPTY_THRESHOLD = float(os.getenv("FEED_EMPTY_THRESHOLD", 0.3))   # kg (big refill)

WATER_THRESHOLD = float(os.getenv("WATER_THRESHOLD", 0.8))       # L
WATER_EMPTY_THRESHOLD = float(os.getenv("WATER_EMPTY_THRESHOLD", 0.3)) # L

# --- ACTIVITY / LIGHT ---
ACTIVITY_MIN = float(os.getenv("ACTIVITY_MIN", 0.3))

LUX_DAY_MIN = float(os.getenv("LUX_DAY_MIN", 40))  # demo: slightly lower so light toggles

# --- MEASUREMENTS NAMES ---
SENSOR_MEASUREMENT = "sensors"
ACTUATOR_MEASUREMENT = "actuator_commands"
SYMPTOM_MEASUREMENT = "symptoms"
PLAN_MEASUREMENT = "plans"

# Influx defaults (env can override)
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "farm-bucket")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "farm-org")

# --- DYNAMIC CONFIG ---
import json

def load_system_config(path="system_config.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading system config from {path}: {e}")
        return {"farms": [{"id": FARM_ID, "zones": [ZONE_ID]}]}
