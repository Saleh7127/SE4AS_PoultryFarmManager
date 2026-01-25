# executor/executor_service.py
import os
import json

from common.mqtt_utils import create_mqtt_client
from common.config import FARM_ID
from common.knowledge import KnowledgeStore

def start_executor():
    print("[EXECUTOR] Starting...")
    ks = KnowledgeStore()
    mqtt_client = create_mqtt_client("executor")

    topic = f"{FARM_ID}/+/plan"
    mqtt_client.subscribe(topic)
    print(f"[EXECUTOR] Subscribed to {topic}")

    def on_message(c, userdata, msg):
        try:
            plan = json.loads(msg.payload.decode())
            print(f"[EXECUTOR] Received plan on {msg.topic}: {plan}")
        except json.JSONDecodeError:
            print(f"[EXECUTOR] Invalid JSON on {msg.topic}")
            return

        zone = plan.get("zone")
        actions = plan.get("actions", [])
        if not zone:
            print("[EXECUTOR] Plan without zone, ignoring")
            return

        for action in actions:
            actuator = action.get("actuator")
            command = action.get("command", {})
            if not actuator:
                continue

            cmd_topic = f"{FARM_ID}/{zone}/cmd/{actuator}"
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
                action_str = command.get("action", "").upper()
                state_str = action_str or "OFF"
                numeric = {"on": 1 if action_str == "ON" else 0}

            elif actuator == "inlet":
                open_pct = int(command.get("open_pct", 0))
                state_str = f"OPEN {open_pct}%"
                numeric = {
                    "open_pct": open_pct,
                    "on": 1 if open_pct > 10 else 0,
                }

            elif actuator == "feed_dispenser":
                amount_g = int(command.get("amount_g", 0))
                state_str = f"DISPENSE {amount_g}g"
                numeric = {
                    "amount_g": amount_g,
                    "on": 1 if amount_g > 0 else 0,
                }

            elif actuator == "water_valve":
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
            )

    mqtt_client.on_message = on_message
    mqtt_client.loop_forever()
