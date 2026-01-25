import json
import threading
import time

import paho.mqtt.client as mqtt

from common.config import FARM_ID, ZONE_ID
from environment.model import EnvironmentState, step

MQTT_HOST = "mqtt"
MQTT_PORT = 1883
MQTT_USER = "admin"
MQTT_PASSWORD = "admin"


class EnvSimulator:
    def __init__(self):
        self.state = EnvironmentState()
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
    
    def _set_heater(self, turn_on: bool):
        s = self.state
        MIN_HEATER_ON_S = 120.0   # 2 minutes
        MIN_HEATER_OFF_S = 120.0  # 2 minutes

        now = s.sim_time_s

        # Allow first switch immediately
        if s.heater_last_switch_s == 0.0 and not s.heater_on and turn_on:
            s.heater_on = True
            s.heater_last_switch_s = now
            return

        elapsed = now - s.heater_last_switch_s

        if turn_on:
            # Currently OFF -> can we turn ON?
            if (not s.heater_on) and (elapsed >= MIN_HEATER_OFF_S):
                s.heater_on = True
                s.heater_last_switch_s = now
        else:
            # Currently ON -> can we turn OFF?
            if s.heater_on and (elapsed >= MIN_HEATER_ON_S):
                s.heater_on = False
                s.heater_last_switch_s = now


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

        if actuator == "fan":
            level = float(data.get("level", 0.0))
            self.state.fan_level_command = max(0.0, min(100.0, level))


        elif actuator == "heater":
            action = data.get("action", "").upper()
            if action == "ON":
                self._set_heater(True)
            elif action == "OFF":
                self._set_heater(False)


        elif actuator == "inlet":
            open_pct = float(data.get("open_pct", 0.0))
            s.inlet_open_pct = max(0.0, min(100.0, open_pct))

        elif actuator == "feed_dispenser":
            amount_g = float(data.get("amount_g", 0.0))
            s.feed_kg += max(0.0, amount_g) / 1000.0

        elif actuator == "water_valve":
            duration_s = float(data.get("duration_s", 0.0))
            duration_s = max(0.0, duration_s)
            refill_l = 0.02 * duration_s   # 0.02 L/s --> 0.3L in 15s
            s.water_l += refill_l

        elif actuator == "light":
            level_pct = float(data.get("level_pct", 0.0))
            s.light_level_pct = max(0.0, min(100.0, level_pct))

    def tick(self, dt_s: float):
        with self._lock:
            step(self.state, dt_s)

    def snapshot(self) -> EnvironmentState:
        with self._lock:
            # shallow copy is fine for simple dataclass
            return EnvironmentState(**self.state.__dict__)


def run_environment_loop():
    sim = EnvSimulator()
    sim.connect()

    while True:
        sim.tick(1.0)  # 1 second per step
        time.sleep(1.0)
