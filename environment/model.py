from dataclasses import dataclass
import math
import os
import time


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# -------------------------
# Simulation Constants
# -------------------------
OUTSIDE_TEMP_BASE_C = _env_float("OUTSIDE_TEMP_BASE_C", 16.0)
OUTSIDE_TEMP_SWING_C = _env_float("OUTSIDE_TEMP_SWING_C", 7.0)
OUTSIDE_TEMP_PERIOD_S = 24.0 * 3600.0
OUTSIDE_CO2_PPM = _env_float("OUTSIDE_CO2_PPM", 420.0)
OUTSIDE_TEMP_SEASONAL_SWING_C = _env_float("OUTSIDE_TEMP_SEASONAL_SWING_C", 8.0)
OUTSIDE_TEMP_SEASONAL_PEAK_DOY = _env_int("OUTSIDE_TEMP_SEASONAL_PEAK_DOY", 200)
USE_HOST_TIME = os.getenv("USE_HOST_TIME", "false").lower() in {"1", "true", "yes"}

# Startup override (force all actuators OFF for this period)
STARTUP_OVERRIDE_S = _env_float("STARTUP_OVERRIDE_S", 60.0)

# Barn physics
BARN_VOLUME_M3 = _env_float("BARN_VOLUME_M3", 600.0)
BARN_UA_W_PER_K = _env_float("BARN_UA_W_PER_K", 250.0)
THERMAL_MASS_FACTOR = _env_float("THERMAL_MASS_FACTOR", 3.0)

AIR_DENSITY = _env_float("AIR_DENSITY", 1.2)
AIR_CP = _env_float("AIR_CP", 1005.0)

# Ventilation
FAN_MAX_FLOW_M3_S = _env_float("FAN_MAX_FLOW_M3_S", 4.0)
BASE_INFILTRATION_M3_S = _env_float("BASE_INFILTRATION_M3_S", 0.15)

# Heaters
HEATER_POWER_W = _env_float("HEATER_POWER_W", 20000.0)

# Birds (biology)
BIRD_COUNT = _env_int("BIRD_COUNT", 2000)
BIRD_HEAT_W_BASE = _env_float("BIRD_HEAT_W_BASE", 10.0)
BIRD_HEAT_W_ACTIVITY = _env_float("BIRD_HEAT_W_ACTIVITY", 6.0)

CO2_LPS_PER_BIRD = _env_float("CO2_LPS_PER_BIRD", 0.0012)  # L/s per bird
CO2_ACTIVITY_MULT = _env_float("CO2_ACTIVITY_MULT", 1.5)

NH3_MG_S_PER_BIRD = _env_float("NH3_MG_S_PER_BIRD", 0.04)  # mg/s per bird
NH3_ACTIVITY_MULT = _env_float("NH3_ACTIVITY_MULT", 1.5)
NH3_TEMP_COEFF = _env_float("NH3_TEMP_COEFF", 0.04)
NH3_DECAY_PER_S = _env_float("NH3_DECAY_PER_S", 1.0 / 3600.0)

FEED_G_PER_BIRD_DAY = _env_float("FEED_G_PER_BIRD_DAY", 110.0)
WATER_L_PER_BIRD_DAY = _env_float("WATER_L_PER_BIRD_DAY", 0.25)
FEED_ACTIVITY_MULT = _env_float("FEED_ACTIVITY_MULT", 0.8)
WATER_ACTIVITY_MULT = _env_float("WATER_ACTIVITY_MULT", 1.1)
FEED_HOPPER_CAPACITY_KG = _env_float("FEED_HOPPER_CAPACITY_KG", 30.0)
WATER_TANK_CAPACITY_L = _env_float("WATER_TANK_CAPACITY_L", 20.0)
FEED_REFILL_FLOW_KG_S = _env_float("FEED_REFILL_FLOW_KG_S", 0.02)
WATER_REFILL_FLOW_L_S = _env_float("WATER_REFILL_FLOW_L_S", 0.15)
FEED_INITIAL_KG = _env_float("FEED_INITIAL_KG", min(20.0, FEED_HOPPER_CAPACITY_KG))
WATER_INITIAL_L = _env_float("WATER_INITIAL_L", min(15.0, WATER_TANK_CAPACITY_L))

# Hysteresis thresholds (adult birds)
FAN_ON_TEMP_C = _env_float("FAN_ON_TEMP_C", 25.0)
FAN_OFF_TEMP_C = _env_float("FAN_OFF_TEMP_C", 23.0)
HEATER_ON_TEMP_C = _env_float("HEATER_ON_TEMP_C", 20.0)
HEATER_OFF_TEMP_C = _env_float("HEATER_OFF_TEMP_C", 24.0)
AUTO_FAN_LEVEL = _env_float("AUTO_FAN_LEVEL", 60.0)

# Minimum on/off durations (fans only)
MIN_FAN_ON_S = _env_float("MIN_FAN_ON_S", 120.0)
MIN_FAN_OFF_S = _env_float("MIN_FAN_OFF_S", 120.0)

# If no external command recently, auto-control takes over
AUTO_CONTROL_TIMEOUT_S = _env_float("AUTO_CONTROL_TIMEOUT_S", 300.0)

# Staged ventilation (fan) levels and inlet defaults
FAN_STAGES = (0.0, 40.0, 70.0, 100.0)
INLET_FOR_STAGE = {
    0.0: 10.0,
    40.0: 40.0,
    70.0: 60.0,
    100.0: 80.0,
}

# Light schedule (24h clock)
LIGHTS_ON_H = _env_float("LIGHTS_ON_H", 6.0)
LIGHTS_OFF_H = _env_float("LIGHTS_OFF_H", 22.0)
LIGHT_DAY_PCT = _env_float("LIGHT_DAY_PCT", 70.0)
LIGHT_NIGHT_PCT = _env_float("LIGHT_NIGHT_PCT", 5.0)

# Actuator ramps
FAN_RAMP_PER_MIN = _env_float("FAN_RAMP_PER_MIN", 40.0)  # % per minute
HEATER_RAMP_PER_MIN = _env_float("HEATER_RAMP_PER_MIN", 60.0)
INLET_RAMP_PER_MIN = _env_float("INLET_RAMP_PER_MIN", 60.0)
LIGHT_RAMP_PER_MIN = _env_float("LIGHT_RAMP_PER_MIN", 80.0)

# Activity dynamics
ACTIVITY_TIME_CONSTANT_MIN = _env_float("ACTIVITY_TIME_CONSTANT_MIN", 15.0)


@dataclass
class EnvironmentState:
    # --- SENSORS (6) ---
    temperature_c: float = 23.0
    co2_ppm: float = 1500.0
    nh3_ppm: float = 12.0
    feed_kg: float = FEED_INITIAL_KG
    water_l: float = WATER_INITIAL_L
    activity: float = 0.4

    # --- ACTUATORS (6) ---
    fan_level: float = 0.0           # actual fan output 0–100%
    fan_level_command: float = 0.0   # requested fan level
    fan_on: bool = False
    fan_last_switch_s: float = 0.0
    fan_cmd_last_s: float = 0.0

    heater_level: float = 0.0        # actual heater output 0–100%
    heater_level_command: float = 0.0
    heater_cmd_last_s: float = 0.0

    inlet_open_pct: float = 30.0
    inlet_open_pct_command: float = 30.0
    inlet_cmd_last_s: float = 0.0

    light_level_pct: float = 30.0
    light_level_pct_command: float = 30.0
    light_cmd_last_s: float = 0.0

    feed_refill_on: bool = False
    feed_refill_remaining_s: float = 0.0
    water_refill_on: bool = False
    water_refill_remaining_s: float = 0.0

    # Auto-control fallback
    auto_control: bool = True

    # internal time for demo behavior
    sim_time_s: float = 0.0

    # Physical config (overridable)
    bird_count: int = BIRD_COUNT
    barn_volume_m3: float = BARN_VOLUME_M3


def _outside_temp(sim_time_s: float) -> float:
    if USE_HOST_TIME:
        now = time.time()
        tm = time.localtime(now)
        day_phase = (tm.tm_hour + tm.tm_min / 60.0 + tm.tm_sec / 3600.0) / 24.0
        season_phase = 2.0 * math.pi * ((tm.tm_yday - OUTSIDE_TEMP_SEASONAL_PEAK_DOY) / 365.0)
        seasonal_offset = OUTSIDE_TEMP_SEASONAL_SWING_C * math.cos(season_phase)
        return OUTSIDE_TEMP_BASE_C + seasonal_offset + OUTSIDE_TEMP_SWING_C * math.sin(2.0 * math.pi * day_phase)
    phase = (sim_time_s % OUTSIDE_TEMP_PERIOD_S) / OUTSIDE_TEMP_PERIOD_S
    return OUTSIDE_TEMP_BASE_C + OUTSIDE_TEMP_SWING_C * math.sin(2.0 * math.pi * phase)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _time_of_day_h(sim_time_s: float) -> float:
    if USE_HOST_TIME:
        tm = time.localtime()
        return tm.tm_hour + (tm.tm_min / 60.0) + (tm.tm_sec / 3600.0)
    return (sim_time_s / 3600.0) % 24.0


def _stage_fan_level(command_level: float) -> float:
    if command_level <= 0.0:
        return 0.0
    for stage in FAN_STAGES[1:]:
        if command_level <= stage:
            return stage
    return FAN_STAGES[-1]


def _ventilation_flow_m3_s(fan_level: float, inlet_open_pct: float) -> float:
    inlet_factor = 0.2 + 0.8 * (inlet_open_pct / 100.0)
    fan_flow = FAN_MAX_FLOW_M3_S * (fan_level / 100.0) * inlet_factor
    return BASE_INFILTRATION_M3_S + fan_flow


def step(state: EnvironmentState, dt_s: float) -> None:
    """
    Advance the environment dt_s seconds.
    Uses a physically-based thermal and gas mass-balance model.
    """

    state.sim_time_s += dt_s

    # --------------------------
    # 0. AUTO-CONTROL (HYSTERESIS)
    # --------------------------
    auto_control_active = state.auto_control and state.sim_time_s >= STARTUP_OVERRIDE_S
    if auto_control_active:
        now = state.sim_time_s
        fan_stale = state.fan_cmd_last_s == 0.0 or now - state.fan_cmd_last_s >= AUTO_CONTROL_TIMEOUT_S
        if fan_stale:
            if state.temperature_c >= FAN_ON_TEMP_C:
                state.fan_level_command = max(state.fan_level_command, AUTO_FAN_LEVEL)
            elif state.temperature_c <= FAN_OFF_TEMP_C:
                state.fan_level_command = 0.0

        heater_stale = state.heater_cmd_last_s == 0.0 or now - state.heater_cmd_last_s >= AUTO_CONTROL_TIMEOUT_S
        if heater_stale:
            if state.temperature_c <= HEATER_ON_TEMP_C:
                state.heater_level_command = 100.0
            elif state.temperature_c >= HEATER_OFF_TEMP_C:
                state.heater_level_command = 0.0

        inlet_stale = state.inlet_cmd_last_s == 0.0 or now - state.inlet_cmd_last_s >= AUTO_CONTROL_TIMEOUT_S
        if inlet_stale:
            staged_fan = _stage_fan_level(state.fan_level_command)
            state.inlet_open_pct_command = INLET_FOR_STAGE.get(staged_fan, state.inlet_open_pct_command)

        light_stale = state.light_cmd_last_s == 0.0 or now - state.light_cmd_last_s >= AUTO_CONTROL_TIMEOUT_S
        if light_stale:
            time_of_day_h = _time_of_day_h(state.sim_time_s)
            if LIGHTS_ON_H <= time_of_day_h < LIGHTS_OFF_H:
                state.light_level_pct_command = LIGHT_DAY_PCT
            else:
                state.light_level_pct_command = LIGHT_NIGHT_PCT

    if state.sim_time_s < STARTUP_OVERRIDE_S:
        state.fan_level_command = 0.0
        state.heater_level_command = 0.0
        state.inlet_open_pct_command = 0.0
        state.light_level_pct_command = 0.0

    # Clamp requested actuator values
    state.fan_level_command = _clamp(state.fan_level_command, 0.0, 100.0)
    state.heater_level_command = _clamp(state.heater_level_command, 0.0, 100.0)
    state.inlet_open_pct_command = _clamp(state.inlet_open_pct_command, 0.0, 100.0)
    state.light_level_pct_command = _clamp(state.light_level_pct_command, 0.0, 100.0)

    # --------------------------
    # 1. ACTUATOR DYNAMICS
    # --------------------------
    now = state.sim_time_s

    desired_fan_on = state.fan_level_command > 0.0
    if desired_fan_on != state.fan_on:
        elapsed = now - state.fan_last_switch_s
        if desired_fan_on and elapsed >= MIN_FAN_OFF_S:
            state.fan_on = True
            state.fan_last_switch_s = now
        elif (not desired_fan_on) and elapsed >= MIN_FAN_ON_S:
            state.fan_on = False
            state.fan_last_switch_s = now

    staged_target = _stage_fan_level(state.fan_level_command)
    target_fan_level = staged_target if state.fan_on else 0.0
    dt_min = dt_s / 60.0
    max_step = FAN_RAMP_PER_MIN * dt_min
    delta = target_fan_level - state.fan_level
    if delta > max_step:
        delta = max_step
    elif delta < -max_step:
        delta = -max_step
    state.fan_level = _clamp(state.fan_level + delta, 0.0, 100.0)

    heater_step = HEATER_RAMP_PER_MIN * dt_min
    heater_delta = state.heater_level_command - state.heater_level
    if heater_delta > heater_step:
        heater_delta = heater_step
    elif heater_delta < -heater_step:
        heater_delta = -heater_step
    state.heater_level = _clamp(state.heater_level + heater_delta, 0.0, 100.0)

    inlet_step = INLET_RAMP_PER_MIN * dt_min
    inlet_delta = state.inlet_open_pct_command - state.inlet_open_pct
    if inlet_delta > inlet_step:
        inlet_delta = inlet_step
    elif inlet_delta < -inlet_step:
        inlet_delta = -inlet_step
    state.inlet_open_pct = _clamp(state.inlet_open_pct + inlet_delta, 0.0, 100.0)

    light_step = LIGHT_RAMP_PER_MIN * dt_min
    light_delta = state.light_level_pct_command - state.light_level_pct
    if light_delta > light_step:
        light_delta = light_step
    elif light_delta < -light_step:
        light_delta = -light_step
    state.light_level_pct = _clamp(state.light_level_pct + light_delta, 0.0, 100.0)

    # --------------------------
    # 2. VENTILATION FLOW
    # --------------------------
    flow_m3_s = _ventilation_flow_m3_s(state.fan_level, state.inlet_open_pct)

    # --------------------------
    # 3. TEMPERATURE DYNAMICS
    # --------------------------
    outside_temp = _outside_temp(state.sim_time_s)
    heat_capacity_j_per_k = AIR_DENSITY * AIR_CP * state.barn_volume_m3 * THERMAL_MASS_FACTOR

    q_loss = BARN_UA_W_PER_K * (state.temperature_c - outside_temp)
    q_vent = AIR_DENSITY * AIR_CP * flow_m3_s * (state.temperature_c - outside_temp)
    q_heater = HEATER_POWER_W * (state.heater_level / 100.0)

    bird_heat_w = state.bird_count * (BIRD_HEAT_W_BASE + BIRD_HEAT_W_ACTIVITY * state.activity)

    dtemp = (q_heater + bird_heat_w - q_loss - q_vent) / heat_capacity_j_per_k
    state.temperature_c = _clamp(state.temperature_c + dtemp * dt_s, 10.0, 40.0)

    # --------------------------
    # 4. CO2 DYNAMICS (mass balance)
    # --------------------------
    co2_lps = CO2_LPS_PER_BIRD * (1.0 + CO2_ACTIVITY_MULT * state.activity)
    co2_m3_s = (co2_lps * state.bird_count) / 1000.0
    co2_gen_ppm_s = (co2_m3_s / state.barn_volume_m3) * 1.0e6
    co2_vent_ppm_s = (flow_m3_s / state.barn_volume_m3) * (OUTSIDE_CO2_PPM - state.co2_ppm)

    state.co2_ppm += (co2_gen_ppm_s + co2_vent_ppm_s) * dt_s
    state.co2_ppm = _clamp(state.co2_ppm, 400.0, 6000.0)

    # --------------------------
    # 5. NH3 DYNAMICS (emission + ventilation + decay)
    # --------------------------
    temp_factor = max(0.0, state.temperature_c - 20.0)
    nh3_mg_s = (
        NH3_MG_S_PER_BIRD
        * state.bird_count
        * (1.0 + NH3_ACTIVITY_MULT * state.activity)
        * (1.0 + NH3_TEMP_COEFF * temp_factor)
    )

    # Convert mg/s to ppm/s: ppm = mg/m3 * (24.45 / 17.0)
    nh3_ppm_gen_s = (nh3_mg_s / state.barn_volume_m3) * (24.45 / 17.0)
    nh3_vent_ppm_s = (flow_m3_s / state.barn_volume_m3) * (0.0 - state.nh3_ppm)
    nh3_decay_ppm_s = -NH3_DECAY_PER_S * state.nh3_ppm

    state.nh3_ppm += (nh3_ppm_gen_s + nh3_vent_ppm_s + nh3_decay_ppm_s) * dt_s
    state.nh3_ppm = _clamp(state.nh3_ppm, 0.0, 200.0)

    # --------------------------
    # 6. FEED & WATER DYNAMICS
    # --------------------------
    feed_kg_s = (FEED_G_PER_BIRD_DAY / 1000.0) / 86400.0
    feed_rate = state.bird_count * feed_kg_s * (0.6 + FEED_ACTIVITY_MULT * state.activity)
    if state.temperature_c > 28.0:
        feed_rate *= 0.9
    if state.temperature_c < 18.0:
        feed_rate *= 0.85
    if state.water_l < 1.0:
        feed_rate *= 0.7
    state.feed_kg = max(0.0, state.feed_kg - feed_rate * dt_s)
    if state.feed_refill_remaining_s > 0.0:
        state.feed_refill_remaining_s = max(0.0, state.feed_refill_remaining_s - dt_s)
    feed_refill_active = state.feed_refill_on or state.feed_refill_remaining_s > 0.0
    if feed_refill_active:
        state.feed_kg = min(
            FEED_HOPPER_CAPACITY_KG,
            state.feed_kg + FEED_REFILL_FLOW_KG_S * dt_s,
        )

    water_l_s = WATER_L_PER_BIRD_DAY / 86400.0
    water_rate = state.bird_count * water_l_s * (0.7 + WATER_ACTIVITY_MULT * state.activity)
    if state.temperature_c > 26.0:
        water_rate *= 1.2
    if state.temperature_c < 18.0:
        water_rate *= 0.9
    state.water_l = max(0.0, state.water_l - water_rate * dt_s)
    if state.water_refill_remaining_s > 0.0:
        state.water_refill_remaining_s = max(0.0, state.water_refill_remaining_s - dt_s)
    water_refill_active = state.water_refill_on or state.water_refill_remaining_s > 0.0
    if water_refill_active:
        state.water_l = min(
            WATER_TANK_CAPACITY_L,
            state.water_l + WATER_REFILL_FLOW_L_S * dt_s,
        )

    # --------------------------
    # 7. ACTIVITY DYNAMICS
    # --------------------------
    time_of_day_h = _time_of_day_h(state.sim_time_s)
    circadian = 0.5 + 0.5 * math.sin(2.0 * math.pi * (time_of_day_h - 6.0) / 24.0)
    light_factor = state.light_level_pct / 100.0

    target_activity = 0.15 + 0.5 * light_factor + 0.2 * circadian

    if state.temperature_c < 20.0 or state.temperature_c > 30.0:
        target_activity -= 0.2
    if state.co2_ppm > 3000.0:
        target_activity -= 0.15
    if state.nh3_ppm > 20.0:
        target_activity -= 0.15
    if state.feed_kg < 1.0:
        target_activity -= 0.1
    if state.water_l < 1.0:
        target_activity -= 0.1

    target_activity = _clamp(target_activity, 0.0, 1.0)
    activity_tau_s = ACTIVITY_TIME_CONSTANT_MIN * 60.0
    state.activity += (target_activity - state.activity) * (dt_s / activity_tau_s)
    state.activity = _clamp(state.activity, 0.0, 1.0)


