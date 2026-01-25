import json
import time
import random
import paho.mqtt.client as mqtt

from common.config import FARM_ID, ZONE_ID
from environment.actuators import EnvSimulator

MQTT_HOST = "mqtt"
MQTT_PORT = 1883
MQTT_USER = "admin"
MQTT_PASSWORD = "admin"


def start_sensors():
    sim = EnvSimulator()
    sim.connect()

    pub = mqtt.Client(client_id="sensors")
    pub.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    pub.connect(MQTT_HOST, MQTT_PORT, 60)
    pub.loop_start()

    tick = 0

    while True:
        sim.tick(1.0)  # advance environment 1s
        state = sim.snapshot()
        tick += 1

        base = f"{FARM_ID}/{ZONE_ID}/sensors"

        # --- Add some measurement noise ---
        temperature_c = state.temperature_c + random.gauss(0, 0.2)
        co2_ppm = state.co2_ppm + random.gauss(0, 30)
        nh3_ppm = state.nh3_ppm + random.gauss(0, 2)
        feed_kg = max(0.0, state.feed_kg + random.gauss(0, 0.02))
        water_l = max(0.0, state.water_l + random.gauss(0, 0.01))
        activity = min(1.0, max(0.0, state.activity + random.gauss(0, 0.02)))

        # --- Different sampling rates ---
        # Air sensors: every 2 seconds
        if tick % 2 == 0:
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

        # Feed / water / activity: every 5 seconds
        if tick % 5 == 0:
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

        time.sleep(1.0)
