# environment/main.py

import json
import os
import random
import threading
import time

from common.mqtt_utils import create_mqtt_client
from common.config import FARM_ID, ZONE_ID
from .model import (
    EnvironmentState,
    step,
    STARTUP_OVERRIDE_S,
    FEED_REFILL_FLOW_KG_S,
    WATER_REFILL_FLOW_L_S,
)

SENSOR_INTERVAL_S = float(os.getenv("SENSOR_INTERVAL_S", 5.0))
SIM_STEP_S = float(os.getenv("SIM_STEP_S", SENSOR_INTERVAL_S))
AUTO_CONTROL = os.getenv("AUTO_CONTROL", "true").lower() in {"1", "true", "yes"}


class EnvironmentRunner:
    """
    Single-process environment simulation:
    - Maintains EnvironmentState
    - Listens to actuator commands on MQTT
    - Publishes 6 sensor values every minute
    """

    def __init__(self):
        self.state = EnvironmentState(auto_control=AUTO_CONTROL)
        self._lock = threading.Lock()
        self.client = create_mqtt_client("environment")
        self._sim_accum_s = 0.0

        # attach callbacks
        self.client.on_message = self._on_message

    def start(self):
        # subscribe to all actuator command topics
        cmd_topic = f"{FARM_ID}/{ZONE_ID}/cmd/+"
        print(f"[ENV] Subscribing to {cmd_topic}")
        self.client.subscribe(cmd_topic)

        # start MQTT network loop in background
        self.client.loop_start()

        # main simulation loop: sensor publish every 5s, model tick per SIM_STEP_S
        while True:
            self._sim_accum_s += SENSOR_INTERVAL_S
            while self._sim_accum_s >= SIM_STEP_S:
                self._tick(SIM_STEP_S)
                self._sim_accum_s -= SIM_STEP_S
            self._publish_sensors()
            time.sleep(SENSOR_INTERVAL_S)

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            print(f"[ENV] Invalid JSON on {msg.topic}")
            return

        actuator = msg.topic.split("/")[-1]
        with self._lock:
            self._apply_command(actuator, data)

    def _apply_command(self, actuator: str, data: dict):
        s = self.state
        if s.sim_time_s < STARTUP_OVERRIDE_S:
            print("[ENV] Ignoring actuator command during startup override")
            return

        if actuator == "fan":
            level = float(data.get("level", 0.0))
            s.fan_level_command = max(0.0, min(100.0, level))
            s.fan_cmd_last_s = s.sim_time_s
            print(f"[ENV] Fan command set to {s.fan_level_command}%")

        elif actuator == "heater":
            if "level_pct" in data:
                level_pct = float(data.get("level_pct", 0.0))
                s.heater_level_command = max(0.0, min(100.0, level_pct))
                s.heater_cmd_last_s = s.sim_time_s
                print(f"[ENV] Heater level set to {s.heater_level_command}%")
            else:
                action = data.get("action", "").upper()
                if action in {"ON", "OFF"}:
                    s.heater_level_command = 100.0 if action == "ON" else 0.0
                    s.heater_cmd_last_s = s.sim_time_s
                    print(f"[ENV] Heater command set to {action}")

        elif actuator == "inlet":
            open_pct = float(data.get("open_pct", 0.0))
            s.inlet_open_pct_command = max(0.0, min(100.0, open_pct))
            s.inlet_cmd_last_s = s.sim_time_s
            print(f"[ENV] Inlet open_pct set to {s.inlet_open_pct_command}%")

        elif actuator == "feed_dispenser":
            action = data.get("action", "").upper()
            if "on" in data or action in {"ON", "OFF"}:
                on = data.get("on")
                if on is None:
                    on = action == "ON"
                s.feed_refill_on = bool(on)
                print(f"[ENV] Feed refill {'ON' if s.feed_refill_on else 'OFF'}")
            else:
                amount_g = float(data.get("amount_g", 0.0))
                amount_kg = max(0.0, amount_g) / 1000.0
                if amount_kg > 0.0 and FEED_REFILL_FLOW_KG_S > 0.0:
                    s.feed_refill_remaining_s = amount_kg / FEED_REFILL_FLOW_KG_S
                print(f"[ENV] Feed refill for {s.feed_refill_remaining_s:.1f}s")

        elif actuator == "water_valve":
            action = data.get("action", "").upper()
            if "on" in data or action in {"ON", "OFF"}:
                on = data.get("on")
                if on is None:
                    on = action == "ON"
                s.water_refill_on = bool(on)
                print(f"[ENV] Water refill {'ON' if s.water_refill_on else 'OFF'}")
            else:
                duration_s = float(data.get("duration_s", 0.0))
                s.water_refill_remaining_s = max(0.0, duration_s)
                print(f"[ENV] Water refill for {s.water_refill_remaining_s:.1f}s")

        elif actuator == "light":
            level_pct = float(data.get("level_pct", 0.0))
            s.light_level_pct_command = max(0.0, min(100.0, level_pct))
            s.light_cmd_last_s = s.sim_time_s
            print(f"[ENV] Light level set to {s.light_level_pct_command}%")

        else:
            print(f"[ENV] Unknown actuator '{actuator}'")

    def _tick(self, dt_s: float):
        with self._lock:
            step(self.state, dt_s)

    def _snapshot(self) -> EnvironmentState:
        with self._lock:
            # shallow copy via dataclass constructor
            return EnvironmentState(**self.state.__dict__)

    def _publish_sensors(self):
        s = self._snapshot()
        base = f"{FARM_ID}/{ZONE_ID}/sensors"

        # measurement noise
        temperature_c = s.temperature_c + random.gauss(0.0, 0.2)
        co2_ppm = max(400.0, s.co2_ppm + random.gauss(0.0, 30.0))
        nh3_ppm = max(0.0, s.nh3_ppm + random.gauss(0.0, 2.0))
        feed_kg = max(0.0, s.feed_kg + random.gauss(0.0, 0.005))
        water_l = max(0.0, s.water_l + random.gauss(0.0, 0.002))
        activity = max(0.0, min(1.0, s.activity + random.gauss(0.0, 0.02)))

        # air: temperature, CO2, NH3
        air_payload = {
            "temperature_c": temperature_c,
            "co2_ppm": co2_ppm,
            "nh3_ppm": nh3_ppm,
        }
        self.client.publish(f"{base}/air", json.dumps(air_payload))

        # feed level
        feed_payload = {"feed_kg": feed_kg}
        self.client.publish(f"{base}/feed_level", json.dumps(feed_payload))

        # water level
        water_payload = {"water_l": water_l}
        self.client.publish(f"{base}/water_level", json.dumps(water_payload))

        # activity
        activity_payload = {"activity": activity}
        self.client.publish(f"{base}/activity", json.dumps(activity_payload))

        print(
            f"[ENV] Sensors: T={temperature_c:.2f}C, CO2={co2_ppm:.0f}ppm, "
            f"NH3={nh3_ppm:.1f}ppm, feed={feed_kg:.2f}kg, water={water_l:.2f}L, "
            f"activity={activity:.2f}"
        )


def main():
    runner = EnvironmentRunner()
    runner.start()


if __name__ == "__main__":
    main()
