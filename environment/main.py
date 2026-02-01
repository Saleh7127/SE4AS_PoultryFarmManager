# environment/main.py

import json
import os
import random
import threading
import time
from dataclasses import fields

from common.mqtt_utils import create_mqtt_client
from common.config import get_config
from .model import (
    EnvironmentState,
    SimulationConfig,
    step,
)

SENSOR_INTERVAL_S = float(os.getenv("SENSOR_INTERVAL_S", 5.0))
SIM_STEP_S = float(os.getenv("SIM_STEP_S", SENSOR_INTERVAL_S))


class EnvironmentRunner(threading.Thread):
    """
    Single-process environment simulation for ONE zone:
    - Maintains EnvironmentState
    - Listens to actuator commands on MQTT
    - Publishes 6 sensor values every minute
    """

    def __init__(self, farm_id: str, zone_id: str, system_config: dict):
        super().__init__(daemon=True)
        self.farm_id = farm_id
        self.zone_id = zone_id
        self.system_config = system_config
        
        self.config = SimulationConfig()
        
        for field_info in fields(SimulationConfig):
            key = field_info.name
            val = get_config(key, system_config, farm_id, zone_id)
            if val is not None:
                target_type = field_info.type
                try:
                    if target_type == bool:
                         if isinstance(val, str):
                             val = val.lower() in ("true", "1", "yes")
                         else:
                             val = bool(val)
                    else:
                        val = target_type(val)
                    setattr(self.config, key, val)
                except (ValueError, TypeError) as e:
                    print(f"[ENV {farm_id}/{zone_id}] Warning: Could not cast config {key}={val} to {target_type}: {e}")

        self.state = EnvironmentState(auto_control=self.config.auto_control)
        self.state.bird_count = self.config.bird_count
        self.state.barn_volume_m3 = self.config.barn_volume_m3

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        
        client_id = f"env_{farm_id}_{zone_id}"
        self.client = create_mqtt_client(client_id)
        self._sim_accum_s = 0.0
        self.client.on_message = self._on_message

    def run(self):
        cmd_topic = f"{self.farm_id}/{self.zone_id}/cmd/+"
        print(f"[ENV {self.farm_id}/{self.zone_id}] Subscribing to {cmd_topic}")
        self.client.subscribe(cmd_topic)
        self.client.loop_start()

        print(f"[ENV {self.farm_id}/{self.zone_id}] Simulation started.")
        while not self._stop_event.is_set():
            self._sim_accum_s += SENSOR_INTERVAL_S
            while self._sim_accum_s >= SIM_STEP_S:
                self._tick(SIM_STEP_S)
                self._sim_accum_s -= SIM_STEP_S
            self._publish_sensors()
            
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
        
        if s.sim_time_s < self.config.startup_override_s:
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
                if amount_kg > 0.0 and self.config.feed_refill_flow_kg_s > 0.0:
                    s.feed_refill_remaining_s = amount_kg / self.config.feed_refill_flow_kg_s
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
            step(self.state, self.config, dt_s)

    def _snapshot(self) -> EnvironmentState:
        with self._lock:
            return EnvironmentState(**self.state.__dict__)

    def _publish_sensors(self):
        s = self._snapshot()
        base = f"{self.farm_id}/{self.zone_id}/sensors"

        temperature_c = s.temperature_c + random.gauss(0.0, 0.2)
        co2_ppm = max(400.0, s.co2_ppm + random.gauss(0.0, 30.0))
        nh3_ppm = max(0.0, s.nh3_ppm + random.gauss(0.0, 2.0))
        feed_kg = max(0.0, s.feed_kg + random.gauss(0.0, 0.005))
        water_l = max(0.0, s.water_l + random.gauss(0.0, 0.002))
        activity = max(0.0, min(1.0, s.activity + random.gauss(0.0, 0.02)))

        air_payload = {
            "temperature_c": temperature_c,
            "co2_ppm": co2_ppm,
            "nh3_ppm": nh3_ppm,
        }
        self.client.publish(f"{base}/air", json.dumps(air_payload))

        feed_payload = {"feed_kg": feed_kg}
        self.client.publish(f"{base}/feed_level", json.dumps(feed_payload))

        water_payload = {"water_l": water_l}
        self.client.publish(f"{base}/water_level", json.dumps(water_payload))

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
    runners = {} 
    last_mtime = 0.0

    while True:
        try:
            mtime = os.path.getmtime(config_path)
            if mtime > last_mtime:
                print(f"[ENV] Config changed (mtime={mtime}), reloading...")
                last_mtime = mtime
                
                config = load_system_config(config_path)
                
                desired = set()
                for farm in config.get("farms", []):
                    f_id = farm["id"]
                    for z in farm.get("zones", []):
                        z_id = z["id"] if isinstance(z, dict) else z
                        desired.add((f_id, z_id))
                
                # Identify changes
                current = set(runners.keys())
                to_add = desired - current
                to_remove = current - desired
                
                for (f_id, z_id) in to_add:
                    print(f"[ENV] Starting new runner for {f_id}/{z_id}")
                    real_zone_id = z_id
                    runner = EnvironmentRunner(f_id, z_id, system_config=config)
                    runner.start()
                    runners[(f_id, z_id)] = runner
                    
                for (f_id, z_id) in to_remove:
                    print(f"[ENV] Stopping runner for {f_id}/{z_id}")
                    runner = runners.pop((f_id, z_id))
                    runner.stop()
                    
                print(f"[ENV] Active runners: {list(runners.keys())}")
                
        except OSError:
            print(f"[ENV] Config file {config_path} not found, waiting...")
        except Exception as e:
            print(f"[ENV] Error reloading config: {e}")
            import traceback
            traceback.print_exc()
            
        time.sleep(5.0)

if __name__ == "__main__":
    main()
