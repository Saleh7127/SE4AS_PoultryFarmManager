import json
import os
import time
from typing import Dict, List, Optional, Tuple

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
    HEATER_MIN_FAN,
)
from common.models import Action, Plan

HEATER_KP_TEMP = float(os.getenv("HEATER_KP_TEMP", "25.0"))
HEATER_DEADBAND_C = float(os.getenv("HEATER_DEADBAND_C", "0.4"))
HEATER_MIN_ON_S = float(os.getenv("HEATER_MIN_ON_S", "120.0"))
HEATER_MIN_OFF_S = float(os.getenv("HEATER_MIN_OFF_S", "120.0"))
HEATER_MIN_LEVEL = float(os.getenv("HEATER_MIN_LEVEL", "10.0"))
LIGHT_ACTIVITY_HIGH = float(os.getenv("LIGHT_ACTIVITY_HIGH", "0.85"))
FAN_MIN_VENT_PCT = float(os.getenv("FAN_MIN_VENT_PCT", "15.0"))
INLET_MIN_PCT = float(os.getenv("INLET_MIN_PCT", "10.0"))
FAN_COLD_MAX_PCT = float(os.getenv("FAN_COLD_MAX_PCT", "35.0"))
INLET_COLD_MAX_PCT = float(os.getenv("INLET_COLD_MAX_PCT", "50.0"))
COLD_VENT_DELTA_C = float(os.getenv("COLD_VENT_DELTA_C", "0.6"))
LIGHT_MIN_DAY_PCT = float(os.getenv("LIGHT_MIN_DAY_PCT", "30.0"))
LIGHT_MIN_NIGHT_PCT = float(os.getenv("LIGHT_MIN_NIGHT_PCT", "5.0"))
LIGHTS_ON_H = float(os.getenv("LIGHTS_ON_H", "6.0"))
LIGHTS_OFF_H = float(os.getenv("LIGHTS_OFF_H", "22.0"))

FAN_RATE_LIMIT_PER_MIN = float(os.getenv("FAN_RATE_LIMIT_PER_MIN", "80.0"))
HEATER_RATE_LIMIT_PER_MIN = float(os.getenv("HEATER_RATE_LIMIT_PER_MIN", "100.0"))
INLET_RATE_LIMIT_PER_MIN = float(os.getenv("INLET_RATE_LIMIT_PER_MIN", "120.0"))
LIGHT_RATE_LIMIT_PER_MIN = float(os.getenv("LIGHT_RATE_LIMIT_PER_MIN", "150.0"))

FEED_REFILL_LOW_KG = float(os.getenv("FEED_REFILL_LOW_KG", FEED_THRESHOLD))
FEED_REFILL_HIGH_KG = float(os.getenv("FEED_REFILL_HIGH_KG", FEED_THRESHOLD + 1.0))
WATER_REFILL_LOW_L = float(os.getenv("WATER_REFILL_LOW_L", WATER_THRESHOLD))
WATER_REFILL_HIGH_L = float(os.getenv("WATER_REFILL_HIGH_L", WATER_THRESHOLD + 0.5))

_LAST_LEVELS: Dict[Tuple[str, str], float] = {}
_LAST_TS: Dict[Tuple[str, str], float] = {}
_REFILL_STATE: Dict[Tuple[str, str], bool] = {}
_HEATER_STATE: Dict[str, bool] = {}
_HEATER_SWITCH_TS: Dict[str, float] = {}


def _rate_limit(zone: str, actuator: str, target: float, max_rate_per_min: float) -> float:
    key = (zone, actuator)
    now = time.time()
    prev = _LAST_LEVELS.get(key, target)
    prev_ts = _LAST_TS.get(key, now)
    dt = max(0.1, now - prev_ts)
    max_delta = max_rate_per_min * (dt / 60.0)
    if target > prev + max_delta:
        new_value = prev + max_delta
    elif target < prev - max_delta:
        new_value = prev - max_delta
    else:
        new_value = target
    _LAST_LEVELS[key] = new_value
    _LAST_TS[key] = now
    return new_value


def _hysteresis_state(
    zone: str,
    actuator: str,
    value: Optional[float],
    low: float,
    high: float,
) -> bool:
    key = (zone, actuator)
    state = _REFILL_STATE.get(key, False)
    if value is None:
        return state
    if value <= low:
        state = True
    elif value >= high:
        state = False
    _REFILL_STATE[key] = state
    return state


def _heater_on_state(zone: str, temp: Optional[float]) -> bool:
    now = time.time()
    last_state = _HEATER_STATE.get(zone, False)
    last_switch = _HEATER_SWITCH_TS.get(zone, now)

    if last_state:
        if temp >= TEMP_SETPOINT + HEATER_DEADBAND_C:
            if now - last_switch >= HEATER_MIN_ON_S:
                last_state = False
                last_switch = now
    else:
        if temp is not None and temp <= TEMP_SETPOINT - HEATER_DEADBAND_C:
            if now - last_switch >= HEATER_MIN_OFF_S:
                last_state = True
                last_switch = now

    _HEATER_STATE[zone] = last_state
    _HEATER_SWITCH_TS[zone] = last_switch
    return last_state


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

    # ===============================
    # 2) HEATER CONTROL (LEVEL 0–100%)
    # ===============================
    heater_level: Optional[float] = None
    if temp is not None:
        heater_on = _heater_on_state(zone, temp)
        if heater_on:
            temp_deficit = max(0.0, TEMP_SETPOINT - temp)
            heater_level = min(100.0, HEATER_KP_TEMP * temp_deficit)
            if heater_level < HEATER_MIN_LEVEL:
                heater_level = HEATER_MIN_LEVEL
        else:
            heater_level = 0.0
        heater_level = _rate_limit(zone, "heater", heater_level, HEATER_RATE_LIMIT_PER_MIN)

    # If heater is ON, keep at least some fan
    if heater_level is not None and heater_level > 0.0 and fan_level is not None:
        fan_level = max(fan_level, HEATER_MIN_FAN)
    if fan_level is not None:
        fan_level = max(fan_level, FAN_MIN_VENT_PCT)
        if (
            temp is not None
            and temp < TEMP_SETPOINT - COLD_VENT_DELTA_C
            and (co2 is None or co2 < CO2_MAX)
            and (nh3 is None or nh3 < NH3_THRESHOLD)
        ):
            fan_level = min(fan_level, FAN_COLD_MAX_PCT)

    if fan_level is not None:
        fan_level = _rate_limit(zone, "fan", fan_level, FAN_RATE_LIMIT_PER_MIN)
        actions.append(
            Action(
                actuator="fan",
                priority=1,
                command={"action": "SET", "level": int(fan_level)},
            )
        )

    if heater_level is not None:
        actions.append(
            Action(
                actuator="heater",
                priority=1,
                command={"action": "SET", "level_pct": int(heater_level)},
            )
        )

    # ===============================
    # 3) FEED & WATER (HYSTERESIS REFILL)
    # ===============================
    feed_refill_on = _hysteresis_state(zone, "feed", feed, FEED_REFILL_LOW_KG, FEED_REFILL_HIGH_KG)
    water_refill_on = _hysteresis_state(zone, "water", water, WATER_REFILL_LOW_L, WATER_REFILL_HIGH_L)

    actions.append(
        Action(
            actuator="feed_dispenser",
            priority=3,
            command={"action": "ON" if feed_refill_on else "OFF"},
        )
    )

    actions.append(
        Action(
            actuator="water_valve",
            priority=3,
            command={"action": "ON" if water_refill_on else "OFF"},
        )
    )

    # ===============================
    # 4) INLET (FAN + AIR QUALITY)
    # ===============================
    inlet_open: Optional[float] = None
    if fan_level is not None:
        inlet_open = 20.0 + 0.6 * fan_level
        if co2 is not None and co2 > CO2_SETPOINT:
            inlet_open += min(20.0, (co2 - CO2_SETPOINT) / 50.0)
        if nh3 is not None and nh3 > NH3_THRESHOLD:
            inlet_open += min(15.0, (nh3 - NH3_THRESHOLD) * 1.5)
        inlet_open = max(INLET_MIN_PCT, min(100.0, inlet_open))
        if (
            temp is not None
            and temp < TEMP_SETPOINT - COLD_VENT_DELTA_C
            and (co2 is None or co2 < CO2_MAX)
            and (nh3 is None or nh3 < NH3_THRESHOLD)
        ):
            inlet_open = min(inlet_open, INLET_COLD_MAX_PCT)

    if inlet_open is not None:
        inlet_open = _rate_limit(zone, "inlet", inlet_open, INLET_RATE_LIMIT_PER_MIN)
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
    now = time.localtime()
    time_of_day_h = now.tm_hour + (now.tm_min / 60.0) + (now.tm_sec / 3600.0)
    night = not (LIGHTS_ON_H <= time_of_day_h < LIGHTS_OFF_H)
    min_light = LIGHT_MIN_NIGHT_PCT if night else LIGHT_MIN_DAY_PCT
    if activity is not None:
        activity_error = ACTIVITY_MIN - activity
        light_level = 60.0 + 70.0 * activity_error
        if activity > LIGHT_ACTIVITY_HIGH:
            light_level -= 20.0
        light_level = max(min_light, min(100.0, light_level))
    else:
        light_level = min_light

    if light_level is not None:
        light_level = _rate_limit(zone, "light", light_level, LIGHT_RATE_LIMIT_PER_MIN)
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
