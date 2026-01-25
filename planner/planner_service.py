import json
from typing import List, Optional

from common.mqtt_utils import create_mqtt_client
from common.config import (
    FARM_ID,
    TEMP_MIN,
    TEMP_MAX,
    NH3_THRESHOLD,
    FEED_THRESHOLD,
    WATER_THRESHOLD,
    ACTIVITY_MIN,
    CO2_MAX,
    LUX_DAY_MIN,
    TEMP_SETPOINT,
    CO2_SETPOINT,
    FAN_KP_TEMP,
    FAN_KP_CO2,
    FAN_MAX,
    FAN_MIN,
    FEED_EMPTY_THRESHOLD,
    WATER_EMPTY_THRESHOLD,
    HEATER_MIN_FAN,
)
from common.models import Action, Plan


def _build_actions_from_status(status: dict) -> List[Action]:
    zone = status.get("zone", "unknown")
    actions: List[Action] = []

    temp = status.get("temperature_c")
    nh3 = status.get("nh3_ppm")
    feed = status.get("feed_kg")
    water = status.get("water_l")
    activity = status.get("activity")
    co2 = status.get("co2_ppm")

    # ===============================
    # 1) FAN CONTROL (0–100%)
    # ===============================
    fan_level: Optional[float] = None

    if temp is not None or co2 is not None:
        temp_error = 0.0
        if temp is not None:
            temp_error = max(0.0, temp - TEMP_SETPOINT)

        co2_error = 0.0
        if co2 is not None:
            co2_error = max(0.0, co2 - CO2_SETPOINT)

        fan_from_temp = FAN_KP_TEMP * temp_error
        fan_from_co2 = FAN_KP_CO2 * co2_error

        fan_level = fan_from_temp + fan_from_co2

        # Extra boost for high ammonia
        if nh3 is not None and nh3 > NH3_THRESHOLD:
            fan_level += 30.0

        if temp is None and co2 is None:
            fan_level = FAN_MAX

        fan_level = max(FAN_MIN, min(FAN_MAX, fan_level))

    if fan_level is not None:
        actions.append(
            Action(
                actuator="fan",
                priority=1,
                command={"action": "SET", "level": int(fan_level)},
            )
        )

    # ===============================
    # 2) HEATER CONTROL (ON/OFF)
    # ===============================
    if temp is not None:
        heater_cmd = None
        if temp < TEMP_MIN:
            heater_cmd = "ON"
        elif temp > TEMP_MIN + 0.5:
            heater_cmd = "OFF"

        if heater_cmd is not None:
            actions.append(
                Action(
                    actuator="heater",
                    priority=1,
                    command={"action": heater_cmd},
                )
            )

        # If heater is ON, keep at least some fan
        if heater_cmd == "ON" and fan_level is not None and fan_level < HEATER_MIN_FAN:
            actions.append(
                Action(
                    actuator="fan",
                    priority=1,
                    command={"action": "SET", "level": int(HEATER_MIN_FAN)},
                )
            )

    # ===============================
    # 3) FEED & WATER (EMPTY / LOW)
    # ===============================

    # FEED DISPENSER pulses (200g / 500g)
    if feed is not None:
        if feed < FEED_EMPTY_THRESHOLD:      # very low
            amount_g = 500
        elif feed < FEED_THRESHOLD:          # low
            amount_g = 200
        else:
            amount_g = 0

        if amount_g > 0:
            actions.append(
                Action(
                    actuator="feed_dispenser",
                    priority=3,
                    command={"action": "DISPENSE", "amount_g": amount_g},
                )
            )

    # WATER VALVE pulses (5s / 15s)
    if water is not None:
        if water < WATER_EMPTY_THRESHOLD:
            duration_s = 15
        elif water < WATER_THRESHOLD:
            duration_s = 5
        else:
            duration_s = 0

        if duration_s > 0:
            actions.append(
                Action(
                    actuator="water_valve",
                    priority=3,
                    command={"action": "OPEN", "duration_s": duration_s},
                )
            )

    # ===============================
    # 4) INLET (SIMPLE FAN-BASED)
    # ===============================
    inlet_open: Optional[float] = None
    if fan_level is not None:
        if fan_level > 60:
            inlet_open = 80.0
        elif fan_level > 20:
            inlet_open = 60.0
        else:
            inlet_open = 40.0

    if inlet_open is not None:
        actions.append(
            Action(
                actuator="inlet",
                priority=2,
                command={"action": "SET", "open_pct": int(inlet_open)},
            )
        )

    # ===============================
    # 5) LIGHT DIMMER (ACTIVITY)
    # ===============================
    # For demo: no explicit lux sensor, we infer from light level and use activity
    light_level: Optional[float] = None
    if activity is not None:
        # If activity low, brighten; if high, dim a bit
        if activity < ACTIVITY_MIN:
            light_level = 80.0
        elif activity > 0.8:
            light_level = 30.0

    if light_level is not None:
        actions.append(
            Action(
                actuator="light",
                priority=4,
                command={"action": "SET", "level_pct": int(light_level)},
            )
        )

    actions.sort(key=lambda a: a.priority)
    return actions


def start_planner():
    print("[PLANNER] Starting...")
    mqtt_client = create_mqtt_client("planner")

    topic = f"{FARM_ID}/+/status"
    mqtt_client.subscribe(topic)
    print(f"[PLANNER] Subscribed to {topic}")

    def on_message(c, userdata, msg):
        try:
            status = json.loads(msg.payload.decode())
            print(f"[PLANNER] Received status on {msg.topic}: {status}")
        except json.JSONDecodeError:
            print(f"[PLANNER] Invalid JSON on {msg.topic}")
            return

        zone = status.get("zone")
        if not zone:
            print("[PLANNER] Status without zone, ignoring")
            return

        actions = _build_actions_from_status(status)
        if not actions:
            print(f"[PLANNER] No actions needed for zone={zone}")
            return

        plan = Plan(zone=zone, actions=actions)
        plan_topic = f"{FARM_ID}/{zone}/plan"
        payload = {
            "zone": plan.zone,
            "actions": [
                {"actuator": a.actuator, "priority": a.priority, "command": a.command}
                for a in plan.actions
            ],
        }

        mqtt_client.publish(plan_topic, json.dumps(payload))
        print(f"[PLANNER] Published plan to {plan_topic}: {payload}")

    mqtt_client.on_message = on_message
    mqtt_client.loop_forever()
