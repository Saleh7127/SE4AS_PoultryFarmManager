import json
import os
import time
import random
import paho.mqtt.client as mqtt

from common.config import FARM_ID, ZONE_ID
from environment.actuators import EnvSimulator

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = os.getenv("MQTT_PORT", 1883)
MQTT_USER = os.getenv("MQTT_USER", "admin")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "admin")
SENSOR_INTERVAL_S = float(os.getenv("SENSOR_INTERVAL_S", 5.0))
SIM_STEP_S = float(os.getenv("SIM_STEP_S", SENSOR_INTERVAL_S))


def start_sensors():
    sim = EnvSimulator()
    sim.connect()

    pub = mqtt.Client(client_id="sensors")
    pub.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    pub.connect(MQTT_HOST, MQTT_PORT, 60)
    pub.loop_start()

    sim_accum_s = 0.0
    while True:
        sim_accum_s += SENSOR_INTERVAL_S
        while sim_accum_s >= SIM_STEP_S:
            sim.tick(SIM_STEP_S)
            sim_accum_s -= SIM_STEP_S
        state = sim.snapshot()

        base = f"{FARM_ID}/{ZONE_ID}/sensors"

        temperature_c = state.temperature_c + random.gauss(0, 0.2)
        co2_ppm = state.co2_ppm + random.gauss(0, 30)
        nh3_ppm = state.nh3_ppm + random.gauss(0, 2)
        feed_kg = max(0.0, state.feed_kg + random.gauss(0, 0.005))
        water_l = max(0.0, state.water_l + random.gauss(0, 0.002))
        activity = min(1.0, max(0.0, state.activity + random.gauss(0, 0.02)))

        pub.publish(
            f"{base}/air",
            json.dumps(
                {
                    "temperature_c": temperature_c,
                    "co2_ppm": co2_ppm,
                    "nh3_ppm": nh3_ppm,
                }
            ),
        )

        pub.publish(
            f"{base}/feed_level",
            json.dumps({"feed_kg": feed_kg}),
        )

        pub.publish(
            f"{base}/water_level",
            json.dumps({"water_l": water_l}),
        )

        pub.publish(
            f"{base}/activity",
            json.dumps({"activity": activity}),
        )

        time.sleep(SENSOR_INTERVAL_S)
