# environment/main.py

import json
import threading
import time

from common.mqtt_utils import create_mqtt_client
from common.config import FARM_ID, ZONE_ID
from .model import EnvironmentState, step


class EnvironmentRunner:
    """
    Single-process environment simulation:
    - Maintains EnvironmentState
    - Listens to actuator commands on MQTT
    - Publishes 6 sensor values every second
    """

    def __init__(self):
        self.state = EnvironmentState()
        self._lock = threading.Lock()
        self.client = create_mqtt_client("environment")

        # attach callbacks
        self.client.on_message = self._on_message

    def start(self):
        # subscribe to all actuator command topics
        cmd_topic = f"{FARM_ID}/{ZONE_ID}/cmd/+"
        print(f"[ENV] Subscribing to {cmd_topic}")
        self.client.subscribe(cmd_topic)

        # start MQTT network loop in background
        self.client.loop_start()

        # main simulation loop: 1s steps
        while True:
            self._tick(1.0)
            self._publish_sensors()
            time.sleep(1.0)

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

        if actuator == "fan":
            level = float(data.get("level", 0.0))
            s.fan_level = max(0.0, min(100.0, level))
            print(f"[ENV] Fan set to {s.fan_level}%")

        elif actuator == "heater":
            action = data.get("action", "").upper()
            s.heater_on = (action == "ON")
            print(f"[ENV] Heater set to {action}")

        elif actuator == "inlet":
            open_pct = float(data.get("open_pct", 0.0))
            s.inlet_open_pct = max(0.0, min(100.0, open_pct))
            print(f"[ENV] Inlet open_pct set to {s.inlet_open_pct}%")

        elif actuator == "feed_dispenser":
            amount_g = float(data.get("amount_g", 0.0))
            delta = max(0.0, amount_g) / 1000.0
            s.feed_kg += delta
            print(f"[ENV] Feed dispenser +{delta:.3f} kg (now {s.feed_kg:.3f} kg)")

        elif actuator == "water_valve":
            duration_s = float(data.get("duration_s", 0.0))
            duration_s = max(0.0, duration_s)
            refill_l = 0.02 * duration_s   # 0.02 L/s → 0.3L in 15s
            s.water_l += refill_l
            print(f"[ENV] Water valve +{refill_l:.3f} L (now {s.water_l:.3f} L)")

        elif actuator == "light":
            level_pct = float(data.get("level_pct", 0.0))
            s.light_level_pct = max(0.0, min(100.0, level_pct))
            print(f"[ENV] Light level set to {s.light_level_pct}%")

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

        # air: temperature, CO2, NH3
        air_payload = {
            "temperature_c": s.temperature_c,
            "co2_ppm": s.co2_ppm,
            "nh3_ppm": s.nh3_ppm,
        }
        self.client.publish(f"{base}/air", json.dumps(air_payload))

        # feed level
        feed_payload = {"feed_kg": s.feed_kg}
        self.client.publish(f"{base}/feed_level", json.dumps(feed_payload))

        # water level
        water_payload = {"water_l": s.water_l}
        self.client.publish(f"{base}/water_level", json.dumps(water_payload))

        # activity
        activity_payload = {"activity": s.activity}
        self.client.publish(f"{base}/activity", json.dumps(activity_payload))

        print(
            f"[ENV] Sensors: T={s.temperature_c:.2f}°C, CO2={s.co2_ppm:.0f}ppm, "
            f"NH3={s.nh3_ppm:.1f}ppm, feed={s.feed_kg:.2f}kg, water={s.water_l:.2f}L, "
            f"activity={s.activity:.2f}"
        )


def main():
    runner = EnvironmentRunner()
    runner.start()


if __name__ == "__main__":
    main()
