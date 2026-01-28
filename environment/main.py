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


class EnvironmentRunner(threading.Thread):
    """
    Single-process environment simulation for ONE zone:
    - Maintains EnvironmentState
    - Listens to actuator commands on MQTT
    - Publishes 6 sensor values every minute
    """

    def __init__(self, farm_id: str, zone_id: str, config_overrides: dict = None):
        super().__init__(daemon=True)
        self.farm_id = farm_id
        self.zone_id = zone_id
        
        # Apply overrides to state
        self.state = EnvironmentState(auto_control=AUTO_CONTROL)
        if config_overrides:
            for k, v in config_overrides.items():
                if hasattr(self.state, k):
                    setattr(self.state, k, v)
                    print(f"[ENV {farm_id}/{zone_id}] Overrode {k}={v}")
                else:
                    print(f"[ENV {farm_id}/{zone_id}] Unknown config key {k}, ignoring.")

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        
        # Unique client ID per runner
        client_id = f"env_{farm_id}_{zone_id}"
        self.client = create_mqtt_client(client_id)
        self._sim_accum_s = 0.0

        # attach callbacks
        self.client.on_message = self._on_message

    def run(self):
        # subscribe to all actuator command topics
        cmd_topic = f"{self.farm_id}/{self.zone_id}/cmd/+"
        print(f"[ENV {self.farm_id}/{self.zone_id}] Subscribing to {cmd_topic}")
        self.client.subscribe(cmd_topic)

        # start MQTT network loop in background
        self.client.loop_start()

        # main simulation loop: sensor publish every 5s, model tick per SIM_STEP_S
        print(f"[ENV {self.farm_id}/{self.zone_id}] Simulation started.")
        while not self._stop_event.is_set():
            self._sim_accum_s += SENSOR_INTERVAL_S
            while self._sim_accum_s >= SIM_STEP_S:
                self._tick(SIM_STEP_S)
                self._sim_accum_s -= SIM_STEP_S
            self._publish_sensors()
            
            # Use event wait for sleep to allow quicker interrupt
            self._stop_event.wait(SENSOR_INTERVAL_S)
            
    def stop(self):
        print(f"[ENV {self.farm_id}/{self.zone_id}] Stopping...")
        self._stop_event.set()
        self.client.loop_stop()
        self.client.disconnect()

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            print(f"[ENV {self.farm_id}/{self.zone_id}] Invalid JSON on {msg.topic}")
            return

        actuator = msg.topic.split("/")[-1]
        with self._lock:
            self._apply_command(actuator, data)

    def _apply_command(self, actuator: str, data: dict):
        s = self.state
        prefix = f"[ENV {self.farm_id}/{self.zone_id}]"
        
        if s.sim_time_s < STARTUP_OVERRIDE_S:
            # print(f"{prefix} Ignoring actuator command during startup override")
            return

        if actuator == "fan":
            level = float(data.get("level", 0.0))
            s.fan_level_command = max(0.0, min(100.0, level))
            s.fan_cmd_last_s = s.sim_time_s
            print(f"{prefix} Fan command set to {s.fan_level_command}%")

        elif actuator == "heater":
            if "level_pct" in data:
                level_pct = float(data.get("level_pct", 0.0))
                s.heater_level_command = max(0.0, min(100.0, level_pct))
                s.heater_cmd_last_s = s.sim_time_s
                print(f"{prefix} Heater level set to {s.heater_level_command}%")
            else:
                action = data.get("action", "").upper()
                if action in {"ON", "OFF"}:
                    s.heater_level_command = 100.0 if action == "ON" else 0.0
                    s.heater_cmd_last_s = s.sim_time_s
                    print(f"{prefix} Heater command set to {action}")

        elif actuator == "inlet":
            open_pct = float(data.get("open_pct", 0.0))
            s.inlet_open_pct_command = max(0.0, min(100.0, open_pct))
            s.inlet_cmd_last_s = s.sim_time_s
            print(f"{prefix} Inlet open_pct set to {s.inlet_open_pct_command}%")

        elif actuator == "feed_dispenser":
            action = data.get("action", "").upper()
            if "on" in data or action in {"ON", "OFF"}:
                on = data.get("on")
                if on is None:
                    on = action == "ON"
                s.feed_refill_on = bool(on)
                print(f"{prefix} Feed refill {'ON' if s.feed_refill_on else 'OFF'}")
            else:
                amount_g = float(data.get("amount_g", 0.0))
                amount_kg = max(0.0, amount_g) / 1000.0
                if amount_kg > 0.0 and FEED_REFILL_FLOW_KG_S > 0.0:
                    s.feed_refill_remaining_s = amount_kg / FEED_REFILL_FLOW_KG_S
                print(f"{prefix} Feed refill for {s.feed_refill_remaining_s:.1f}s")

        elif actuator == "water_valve":
            action = data.get("action", "").upper()
            if "on" in data or action in {"ON", "OFF"}:
                on = data.get("on")
                if on is None:
                    on = action == "ON"
                s.water_refill_on = bool(on)
                print(f"{prefix} Water refill {'ON' if s.water_refill_on else 'OFF'}")
            else:
                duration_s = float(data.get("duration_s", 0.0))
                s.water_refill_remaining_s = max(0.0, duration_s)
                print(f"{prefix} Water refill for {s.water_refill_remaining_s:.1f}s")

        elif actuator == "light":
            level_pct = float(data.get("level_pct", 0.0))
            s.light_level_pct_command = max(0.0, min(100.0, level_pct))
            s.light_cmd_last_s = s.sim_time_s
            print(f"{prefix} Light level set to {s.light_level_pct_command}%")

        else:
            print(f"{prefix} Unknown actuator '{actuator}'")

    def _tick(self, dt_s: float):
        with self._lock:
            step(self.state, dt_s)

    def _snapshot(self) -> EnvironmentState:
        with self._lock:
            # shallow copy via dataclass constructor
            return EnvironmentState(**self.state.__dict__)

    def _publish_sensors(self):
        s = self._snapshot()
        base = f"{self.farm_id}/{self.zone_id}/sensors"

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
            f"[ENV {self.farm_id}/{self.zone_id}] Sensors: T={temperature_c:.2f}C, CO2={co2_ppm:.0f}ppm, "
            f"NH3={nh3_ppm:.1f}ppm, feed={feed_kg:.2f}kg, water={water_l:.2f}L, "
            f"activity={activity:.2f}"
        )


def main():
    from common.config import load_system_config
    
    print("[ENV] Starting Multi-Farm Environment Manager with Hot-Reloading...")
    
    config_path = "system_config.json"
    runners = {} # (farm_id, zone_id) -> EnvironmentRunner
    last_mtime = 0.0

    while True:
        # Check file modification time
        try:
            mtime = os.path.getmtime(config_path)
            if mtime > last_mtime:
                print(f"[ENV] Config changed (mtime={mtime}), reloading...")
                last_mtime = mtime
                
                config = load_system_config(config_path)
                
                # Determine desired set of runners
                desired = set()
                for farm in config.get("farms", []):
                    f_id = farm["id"]
                    for z_id in farm.get("zones", []):
                        desired.add((f_id, z_id))
                
                # Identify changes
                current = set(runners.keys())
                to_add = desired - current
                to_remove = current - desired
                
                # Start new runners
                for (f_id, z_id) in to_add:
                    print(f"[ENV] Starting new runner for {f_id}/{z_id}")
                    
                    # Find config for this zone
                    overrides = {}
                    for farm in config.get("farms", []):
                        if farm["id"] == f_id:
                            # Farm-level config could go here if we supported it
                            for z in farm.get("zones", []):
                                if isinstance(z, dict):  # Support object zones if needed later
                                    # Not implemented yet based on current json structure
                                    pass
                                elif z == z_id:
                                    # Check for overrides if using extended format
                                    # For now, let's assume zones can be objects too or look for sibling 'config' key
                                    pass
                            
                            # Let's check if 'config' exists at farm level or zone level
                            # Current schema matches simplified request:
                            # "farms": [{"id": "f1", "zones": ["z1"], "config": {...}}]
                            if "config" in farm:
                                overrides.update(farm["config"])
                                
                    runner = EnvironmentRunner(f_id, z_id, config_overrides=overrides)
                    runner.start()
                    runners[(f_id, z_id)] = runner
                    
                # Stop removed runners
                for (f_id, z_id) in to_remove:
                    print(f"[ENV] Stopping runner for {f_id}/{z_id}")
                    runner = runners.pop((f_id, z_id))
                    runner.stop()
                    
                print(f"[ENV] Active runners: {list(runners.keys())}")
                
        except OSError:
            print(f"[ENV] Config file {config_path} not found, waiting...")
        except Exception as e:
            print(f"[ENV] Error reloading config: {e}")
            
        time.sleep(5.0)

if __name__ == "__main__":
    main()
