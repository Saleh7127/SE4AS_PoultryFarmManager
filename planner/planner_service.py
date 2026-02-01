import json
import os
import time
from typing import Dict, List, Optional, Tuple

from common.mqtt_utils import create_mqtt_client
from common.config import get_config, load_system_config
from common.models import Action, Plan
from common.knowledge import KnowledgeStore

# Helper to avoid importing too many constants if we can look them up dynamically
# We will use get_config for everything.

_LAST_LEVELS: Dict[Tuple[str, str], float] = {}
_LAST_TS: Dict[Tuple[str, str], float] = {}
_REFILL_STATE: Dict[Tuple[str, str], bool] = {}
_HEATER_STATE: Dict[str, bool] = {}
_HEATER_SWITCH_TS: Dict[str, float] = {}


def _rate_limit(farm_id: str, zone: str, actuator: str, target: float, max_rate_per_min: float) -> float:
    key = (farm_id, zone, actuator)
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
    farm_id: str,
    zone: str,
    actuator: str,
    value: Optional[float],
    low: float,
    high: float,
) -> bool:
    key = (farm_id, zone, actuator)
    state = _REFILL_STATE.get(key, False)
    if value is None:
        return state
    if value <= low:
        state = True
    elif value >= high:
        state = False
    _REFILL_STATE[key] = state
    return state


def _heater_on_state(farm_id: str, zone: str, temp: Optional[float], setpoint: float, deadband: float, min_on_s: float, min_off_s: float) -> bool:
    now = time.time()
    key = f"{farm_id}/{zone}"
    last_state = _HEATER_STATE.get(key, False)
    last_switch = _HEATER_SWITCH_TS.get(key, now)

    if last_state:
        if temp >= setpoint + deadband:
            if now - last_switch >= min_on_s:
                last_state = False
                last_switch = now
    else:
        if temp is not None and temp <= setpoint - deadband:
            if now - last_switch >= min_off_s:
                last_state = True
                last_switch = now

    _HEATER_STATE[key] = last_state
    _HEATER_SWITCH_TS[key] = last_switch
    return last_state


def _build_actions_from_status(status: dict, sys_config: dict) -> List[Action]:
    farm_id = status.get("farm_id", "unknown")
    zone = status.get("zone", "unknown")
    actions: List[Action] = []

    # Helper for config lookup
    def cfg(key, default=None):
        return get_config(key, sys_config, farm_id, zone, default)

    # Load Params
    TEMP_SETPOINT = float(cfg("temp_setpoint"))
    CO2_SETPOINT = float(cfg("co2_setpoint"))
    NH3_THRESHOLD = float(cfg("nh3_threshold"))
    CO2_MAX = float(cfg("co2_max"))
    
    FAN_KP_TEMP = float(cfg("fan_kp_temp"))
    FAN_KP_CO2 = float(cfg("fan_kp_co2"))
    FAN_MAX = float(cfg("fan_max"))
    FAN_MIN = float(cfg("fan_min"))
    
    HEATER_KP_TEMP = float(cfg("heater_kp_temp"))
    HEATER_DEADBAND_C = float(cfg("heater_deadband_c"))
    HEATER_MIN_ON_S = float(cfg("heater_min_on_s"))
    HEATER_MIN_OFF_S = float(cfg("heater_min_off_s"))
    HEATER_MIN_LEVEL = float(cfg("heater_min_level"))
    HEATER_MIN_FAN = float(cfg("heater_min_fan"))
    
    FAN_MIN_VENT_PCT = float(cfg("fan_min_vent_pct"))
    INLET_MIN_PCT = float(cfg("inlet_min_pct"))
    
    FAN_COLD_MAX_PCT = float(cfg("fan_cold_max_pct"))
    INLET_COLD_MAX_PCT = float(cfg("inlet_cold_max_pct"))
    COLD_VENT_DELTA_C = float(cfg("cold_vent_delta_c"))
    
    LIGHT_ACTIVITY_HIGH = float(cfg("light_activity_high"))
    ACTIVITY_MIN = float(cfg("activity_min"))
    LIGHT_MIN_DAY_PCT = float(cfg("light_min_day_pct"))
    LIGHT_MIN_NIGHT_PCT = float(cfg("light_min_night_pct"))
    LIGHTS_ON_H = float(cfg("lights_on_h"))
    LIGHTS_OFF_H = float(cfg("lights_off_h"))

    FAN_RATE_LIMIT_PER_MIN = float(cfg("fan_rate_limit_per_min"))
    HEATER_RATE_LIMIT_PER_MIN = float(cfg("heater_rate_limit_per_min"))
    INLET_RATE_LIMIT_PER_MIN = float(cfg("inlet_rate_limit_per_min"))
    LIGHT_RATE_LIMIT_PER_MIN = float(cfg("light_rate_limit_per_min"))
    
    FEED_THRESHOLD = float(cfg("feed_threshold"))
    WATER_THRESHOLD = float(cfg("water_threshold"))
    
    FEED_REFILL_LOW_KG = float(cfg("feed_refill_low_kg"))
    FEED_REFILL_HIGH_KG = float(cfg("feed_refill_high_kg"))
    WATER_REFILL_LOW_L = float(cfg("water_refill_low_l"))
    WATER_REFILL_HIGH_L = float(cfg("water_refill_high_l"))

    temp = status.get("temperature_c")
    nh3 = status.get("nh3_ppm")
    feed = status.get("feed_kg")
    water = status.get("water_l")
    activity = status.get("activity")
    co2 = status.get("co2_ppm")

    # FAN CONTROL (0–100%)
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

    # HEATER CONTROL (LEVEL 0–100%)
    heater_level: Optional[float] = None
    if temp is not None:
        heater_on = _heater_on_state(farm_id, zone, temp, TEMP_SETPOINT, HEATER_DEADBAND_C, HEATER_MIN_ON_S, HEATER_MIN_OFF_S)
        if heater_on:
            temp_deficit = max(0.0, TEMP_SETPOINT - temp)
            heater_level = min(100.0, HEATER_KP_TEMP * temp_deficit)
            if heater_level < HEATER_MIN_LEVEL:
                heater_level = HEATER_MIN_LEVEL
        else:
            heater_level = 0.0
        heater_level = _rate_limit(farm_id, zone, "heater", heater_level, HEATER_RATE_LIMIT_PER_MIN)

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
        fan_level = _rate_limit(farm_id, zone, "fan", fan_level, FAN_RATE_LIMIT_PER_MIN)
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

    # FEED & WATER (HYSTERESIS REFILL)
    feed_refill_on = _hysteresis_state(farm_id, zone, "feed", feed, FEED_REFILL_LOW_KG, FEED_REFILL_HIGH_KG)
    water_refill_on = _hysteresis_state(farm_id, zone, "water", water, WATER_REFILL_LOW_L, WATER_REFILL_HIGH_L)

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

    # INLET (FAN + AIR QUALITY)
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
        # Note: using raw inlet_open for rate limit, but int() for command
        inlet_open = _rate_limit(farm_id, zone, "inlet", inlet_open, INLET_RATE_LIMIT_PER_MIN)
        actions.append(
            Action(
                actuator="inlet",
                priority=2,
                command={"action": "SET", "open_pct": int(inlet_open)},
            )
        )

    # LIGHT DIMMER (ACTIVITY)
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
        light_level = _rate_limit(farm_id, zone, "light", light_level, LIGHT_RATE_LIMIT_PER_MIN)
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
    ks = KnowledgeStore()
    
    # Load initial config
    config_path = "system_config.json"
    system_config = load_system_config(config_path)

    
    config_container = {"data": system_config, "last_load": time.time()}

    # Subscribe to status from all farms and zones
    topic = "+/+/status"
    mqtt_client.subscribe(topic)
    print(f"[PLANNER] Subscribed to {topic}")

    def on_message(c, userdata, msg):
        # Reload config if needed (simple poller)
        try:
             # Basic 5s throttle on reload check
             now = time.time()
             if now - config_container["last_load"] > 5.0:
                 if os.path.exists(config_path):
                     mtime = os.path.getmtime(config_path)
                     config_container["data"] = load_system_config(config_path)
                     config_container["last_load"] = now
        except Exception as e:
            print(f"[PLANNER] Config reload failed: {e}")

        try:
            status = json.loads(msg.payload.decode())
            print(f"[PLANNER] Received status on {msg.topic}: {status}")
        except json.JSONDecodeError:
            print(f"[PLANNER] Invalid JSON on {msg.topic}")
            return

        # Extract farm and zone from topic
        parts = msg.topic.split("/")
        if len(parts) != 3:
            print(f"[PLANNER] Unexpected topic format: {msg.topic}")
            return
        
        farm_id, zone, _ = parts

        if not zone:
            print("[PLANNER] Status without zone, ignoring")
            return

        actions = _build_actions_from_status(status, config_container["data"])
        if not actions:
            print(f"[PLANNER] No actions needed for {farm_id}/{zone}")
            return

        plan = Plan(zone=zone, actions=actions)
        plan_topic = f"{farm_id}/{zone}/plan"
        payload = {
            "farm_id": farm_id,
            "zone": plan.zone,
            "actions": [
                {"actuator": a.actuator, "priority": a.priority, "command": a.command}
                for a in plan.actions
            ],
        }


        mqtt_client.publish(plan_topic, json.dumps(payload))
        print(f"[PLANNER] Published plan to {plan_topic}: {payload}")
        
        # Log plan to Knowledge Base
        try:
             ks.log_plan(
                 zone=zone,
                 farm_id=farm_id,
                 plan_actions=payload["actions"]
             )
        except Exception as e:
             print(f"[PLANNER] Failed to log plan to KB: {e}")

    mqtt_client.on_message = on_message
    mqtt_client.loop_forever()
