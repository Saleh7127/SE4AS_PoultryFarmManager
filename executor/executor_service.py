import os
import json
from influxdb_client import Point

from common.mqtt_utils import create_mqtt_client
from common.influx_utils import create_influx_client, INFLUXDB_BUCKET, INFLUXDB_ORG
from common.config import FARM_ID, ACTUATOR_MEASUREMENT

INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET") or INFLUXDB_BUCKET
INFLUX_ORG = os.getenv("INFLUXDB_ORG") or INFLUXDB_ORG


def start_executor():
    print("[EXECUTOR] Starting...")
    influx = create_influx_client()
    write_api = influx.write_api()
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

            # ----- Log to InfluxDB -----
            state_str = ""
            point = (
                Point(ACTUATOR_MEASUREMENT)
                .tag("zone", zone)
                .tag("actuator", actuator)
            )

            if actuator == "fan":
                level = int(command.get("level", 0))
                state_str = f"SET {level}%"
                point = point.field("state", state_str)
                point = point.field("level", level)
                point = point.field("on", 1 if level > 0 else 0)

            elif actuator == "heater":
                action_str = command.get("action", "").upper()
                state_str = action_str or "OFF"
                on = 1 if action_str == "ON" else 0
                point = point.field("state", state_str)
                point = point.field("on", on)

            elif actuator == "inlet":
                open_pct = int(command.get("open_pct", 0))
                state_str = f"OPEN {open_pct}%"
                point = point.field("state", state_str)
                point = point.field("open_pct", open_pct)
                point = point.field("on", 1 if open_pct > 10 else 0)

            elif actuator == "feed_dispenser":
                amount_g = int(command.get("amount_g", 0))
                state_str = f"DISPENSE {amount_g}g"
                point = point.field("state", state_str)
                point = point.field("amount_g", amount_g)
                point = point.field("on", 1 if amount_g > 0 else 0)

            elif actuator == "water_valve":
                duration_s = int(command.get("duration_s", 0))
                state_str = f"OPEN {duration_s}s"
                point = point.field("state", state_str)
                point = point.field("duration_s", duration_s)
                point = point.field("on", 1 if duration_s > 0 else 0)

            elif actuator == "light":
                level_pct = int(command.get("level_pct", 0))
                state_str = f"SET {level_pct}%"
                point = point.field("state", state_str)
                point = point.field("level_pct", level_pct)
                point = point.field("on", 1 if level_pct > 0 else 0)

            # fallback payload for debugging if needed
            point = point.field("payload", payload_str)

            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

    mqtt_client.on_message = on_message
    mqtt_client.loop_forever()
