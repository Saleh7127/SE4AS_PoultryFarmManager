import json
import os
import threading
import time

import paho.mqtt.client as mqtt

from common.config import FARM_ID, ZONE_ID
from environment.model import (
    EnvironmentState,
    step,
    STARTUP_OVERRIDE_S,
    FEED_REFILL_FLOW_KG_S,
    WATER_REFILL_FLOW_L_S,
)

MQTT_HOST = "mqtt"
MQTT_PORT = 1883
MQTT_USER = "admin"
MQTT_PASSWORD = "admin"
SENSOR_INTERVAL_S = float(os.getenv("SENSOR_INTERVAL_S", 5.0))
SIM_STEP_S = float(os.getenv("SIM_STEP_S", SENSOR_INTERVAL_S))
AUTO_CONTROL = os.getenv("AUTO_CONTROL", "true").lower() in {"1", "true", "yes"}


class EnvSimulator:
    def __init__(self):
        self.state = EnvironmentState(auto_control=AUTO_CONTROL)
        self._lock = threading.Lock()
        self.client = mqtt.Client(client_id="environment")
        self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self.client.on_message = self._on_message

    def connect(self):
        self.client.connect(MQTT_HOST, MQTT_PORT, 60)
        cmd_topic = f"{FARM_ID}/{ZONE_ID}/cmd/+"
        print(f"[ENV] Subscribing to {cmd_topic}")
        self.client.subscribe(cmd_topic)
        self.client.loop_start()


    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            print(f"[ENV] Invalid JSON on {msg.topic}")
            return

        actuator = msg.topic.split("/")[-1]
        with self._lock:
            self.apply_command(actuator, data)

    def apply_command(self, actuator: str, data: dict):
        s = self.state
        if s.sim_time_s < STARTUP_OVERRIDE_S:
            return

        if actuator == "fan":
            level = float(data.get("level", 0.0))
            s.fan_level_command = max(0.0, min(100.0, level))
            s.fan_cmd_last_s = s.sim_time_s


        elif actuator == "heater":
            if "level_pct" in data:
                level_pct = float(data.get("level_pct", 0.0))
                s.heater_level_command = max(0.0, min(100.0, level_pct))
                s.heater_cmd_last_s = s.sim_time_s
            else:
                action = data.get("action", "").upper()
                if action in {"ON", "OFF"}:
                    s.heater_level_command = 100.0 if action == "ON" else 0.0
                    s.heater_cmd_last_s = s.sim_time_s


        elif actuator == "inlet":
            open_pct = float(data.get("open_pct", 0.0))
            s.inlet_open_pct_command = max(0.0, min(100.0, open_pct))
            s.inlet_cmd_last_s = s.sim_time_s

        elif actuator == "feed_dispenser":
            action = data.get("action", "").upper()
            if "on" in data or action in {"ON", "OFF"}:
                on = data.get("on")
                if on is None:
                    on = action == "ON"
                s.feed_refill_on = bool(on)
            else:
                amount_g = float(data.get("amount_g", 0.0))
                amount_kg = max(0.0, amount_g) / 1000.0
                if amount_kg > 0.0 and FEED_REFILL_FLOW_KG_S > 0.0:
                    s.feed_refill_remaining_s = amount_kg / FEED_REFILL_FLOW_KG_S

        elif actuator == "water_valve":
            action = data.get("action", "").upper()
            if "on" in data or action in {"ON", "OFF"}:
                on = data.get("on")
                if on is None:
                    on = action == "ON"
                s.water_refill_on = bool(on)
            else:
                duration_s = float(data.get("duration_s", 0.0))
                s.water_refill_remaining_s = max(0.0, duration_s)

        elif actuator == "light":
            level_pct = float(data.get("level_pct", 0.0))
            s.light_level_pct_command = max(0.0, min(100.0, level_pct))
            s.light_cmd_last_s = s.sim_time_s

    def tick(self, dt_s: float):
        with self._lock:
            step(self.state, dt_s)

    def snapshot(self) -> EnvironmentState:
        with self._lock:
            return EnvironmentState(**self.state.__dict__)


def run_environment_loop():
    sim = EnvSimulator()
    sim.connect()

    while True:
        sim.tick(SIM_STEP_S)
        time.sleep(SENSOR_INTERVAL_S)
