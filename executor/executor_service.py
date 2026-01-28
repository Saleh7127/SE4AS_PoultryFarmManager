# executor/executor_service.py
import os
import json

from common.mqtt_utils import create_mqtt_client
from common.config import FARM_ID, ZONE_ID
from common.knowledge import KnowledgeStore


def _log_startup_off(ks: KnowledgeStore, mqtt_client) -> None:
    from common.config import load_system_config
    
    config = load_system_config()
    farms = config.get("farms", [])
    
    for farm in farms:
        f_id = farm["id"]
        for zone in farm.get("zones", []):
            initial = [
                ("fan", {"action": "SET", "level": 0}, "SET 0%", {"level": 0, "on": 0}),
                ("heater", {"action": "SET", "level_pct": 0}, "SET 0%", {"level_pct": 0, "on": 0}),
                ("inlet", {"action": "SET", "open_pct": 0}, "OPEN 0%", {"open_pct": 0, "on": 0}),
                ("feed_dispenser", {"action": "OFF"}, "OFF", {"on": 0}),
                ("water_valve", {"action": "OFF"}, "OFF", {"on": 0}),
                ("light", {"action": "SET", "level_pct": 0}, "SET 0%", {"level_pct": 0, "on": 0}),
            ]

            for actuator, command, state_str, numeric in initial:
                cmd_topic = f"{f_id}/{zone}/cmd/{actuator}"
                payload_str = json.dumps(command)
                mqtt_client.publish(cmd_topic, payload_str)
                ks.log_actuator_command(
                    zone=zone,
                    actuator=actuator,
                    state_str=state_str,
                    numeric_fields=numeric,
                    payload=payload_str,
                    farm_id=f_id,
                )

def start_executor():
    print("[EXECUTOR] Starting...")
    ks = KnowledgeStore()
    mqtt_client = create_mqtt_client("executor")
    _log_startup_off(ks, mqtt_client)

    topic = "+/+/plan"
    mqtt_client.subscribe(topic)
    print(f"[EXECUTOR] Subscribed to {topic}")

    def on_message(c, userdata, msg):
        try:
            plan = json.loads(msg.payload.decode())
            print(f"[EXECUTOR] Received plan on {msg.topic}: {plan}")
        except json.JSONDecodeError:
            print(f"[EXECUTOR] Invalid JSON on {msg.topic}")
            return

        # Extract farm_id from topic or payload
        parts = msg.topic.split("/")
        if len(parts) == 3:
             farm_id = parts[0]
        else:
             farm_id = plan.get("farm_id") # fallback if passed in payload

        zone = plan.get("zone")
        actions = plan.get("actions", [])
        
        if not zone or not farm_id:
            print("[EXECUTOR] Plan without zone or farm_id, ignoring")
            return

        for action in actions:
            actuator = action.get("actuator")
            command = action.get("command", {})
            if not actuator:
                continue

            cmd_topic = f"{farm_id}/{zone}/cmd/{actuator}"
            payload_str = json.dumps(command)
            mqtt_client.publish(cmd_topic, payload_str)
            print(f"[EXECUTOR] Sent command to {cmd_topic}: {payload_str}")

            # ----- Log to Knowledge -----
            state_str = ""
            numeric = {}

            if actuator == "fan":
                level = int(command.get("level", 0))
                state_str = f"SET {level}%"
                numeric = {"level": level, "on": 1 if level > 0 else 0}

            elif actuator == "heater":
                if "level_pct" in command:
                    level_pct = int(command.get("level_pct", 0))
                    state_str = f"SET {level_pct}%"
                    numeric = {"level_pct": level_pct, "on": 1 if level_pct > 0 else 0}
                else:
                    action_str = command.get("action", "").upper()
                    if action_str == "ON":
                        state_str = "SET 100%"
                        numeric = {"level_pct": 100, "on": 1}
                    else:
                        state_str = "SET 0%"
                        numeric = {"level_pct": 0, "on": 0}

            elif actuator == "inlet":
                open_pct = int(command.get("open_pct", 0))
                state_str = f"OPEN {open_pct}%"
                numeric = {
                    "open_pct": open_pct,
                    "on": 1 if open_pct > 10 else 0,
                }

            elif actuator == "feed_dispenser":
                action_str = command.get("action", "").upper()
                if action_str in {"ON", "OFF"} or "on" in command:
                    on = command.get("on")
                    if on is None:
                        on = action_str == "ON"
                    state_str = "ON" if on else "OFF"
                    numeric = {"on": 1 if on else 0}
                else:
                    amount_g = int(command.get("amount_g", 0))
                    state_str = f"DISPENSE {amount_g}g"
                    numeric = {
                        "amount_g": amount_g,
                        "on": 1 if amount_g > 0 else 0,
                    }

            elif actuator == "water_valve":
                action_str = command.get("action", "").upper()
                if action_str in {"ON", "OFF"} or "on" in command:
                    on = command.get("on")
                    if on is None:
                        on = action_str == "ON"
                    state_str = "ON" if on else "OFF"
                    numeric = {"on": 1 if on else 0}
                else:
                    duration_s = int(command.get("duration_s", 0))
                    state_str = f"OPEN {duration_s}s"
                    numeric = {
                        "duration_s": duration_s,
                        "on": 1 if duration_s > 0 else 0,
                    }

            elif actuator == "light":
                level_pct = int(command.get("level_pct", 0))
                state_str = f"SET {level_pct}%"
                numeric = {
                    "level_pct": level_pct,
                    "on": 1 if level_pct > 0 else 0,
                }

            ks.log_actuator_command(
                zone=zone,
                actuator=actuator,
                state_str=state_str,
                numeric_fields=numeric,
                payload=payload_str,
                farm_id=farm_id,
            )

    mqtt_client.on_message = on_message
    mqtt_client.loop_forever()
