from dataclasses import dataclass, field
import math
import os
import time

@dataclass
class SimulationConfig:
    # Physical Constants (Defaults OK)
    outside_temp_base_c: float = 12.0
    outside_temp_swing_c: float = 4.0
    outside_temp_period_s: float = 24.0 * 3600.0
    outside_co2_ppm: float = 420.0
    outside_temp_seasonal_swing_c: float = 8.0
    outside_temp_seasonal_peak_doy: int = 200
    use_host_time: bool = False

    startup_override_s: float = 60.0

    barn_volume_m3: float = 300.0
    barn_ua_w_per_k: float = 350.0
    thermal_mass_factor: float = 2.5
    air_density: float = 1.2
    air_cp: float = 1005.0

    fan_stages: tuple = (0.0, 40.0, 70.0, 100.0)

    # Configurable Parameters (Loaded from Config)
    fan_max_flow_m3_s: float = None
    base_infiltration_m3_s: float = None

    heater_power_w: float = None
    bird_count: int = None
    bird_heat_w_base: float = None
    bird_heat_w_activity: float = None
    co2_lps_per_bird: float = None
    co2_activity_mult: float = None
    nh3_mg_s_per_bird: float = None
    nh3_activity_mult: float = None
    nh3_temp_coeff: float = None
    nh3_decay_per_s: float = None
    feed_g_per_bird_day: float = None
    water_l_per_bird_day: float = None
    feed_activity_mult: float = None
    water_activity_mult: float = None
    feed_hopper_capacity_kg: float = None
    water_tank_capacity_l: float = None
    feed_refill_flow_kg_s: float = None
    water_refill_flow_l_s: float = None
    feed_initial_kg: float = None
    water_initial_l: float = None

    fan_on_temp_c: float = None
    fan_off_temp_c: float = None
    heater_on_temp_c: float = None
    heater_off_temp_c: float = None
    auto_fan_level: float = None

    min_fan_on_s: float = None
    min_fan_off_s: float = None

    auto_control: bool = True
    auto_control_timeout_s: float = None
    
    lights_on_h: float = None
    lights_off_h: float = None
    light_day_pct: float = None
    light_night_pct: float = None

    fan_ramp_per_min: float = None
    heater_ramp_per_min: float = None
    inlet_ramp_per_min: float = None
    light_ramp_per_min: float = None
    activity_time_constant_min: float = None


@dataclass
class EnvironmentState:
    temperature_c: float = 23.0
    co2_ppm: float = 1500.0
    nh3_ppm: float = 12.0
    feed_kg: float = 8.0
    water_l: float = 7.0
    activity: float = 0.4

    fan_level: float = 0.0           
    fan_level_command: float = 0.0   
    fan_on: bool = False
    fan_last_switch_s: float = 0.0
    fan_cmd_last_s: float = 0.0

    heater_level: float = 0.0        
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

    auto_control: bool = True

    sim_time_s: float = 0.0

    bird_count: int = 2000
    barn_volume_m3: float = 300.0


INLET_FOR_STAGE = {
    0.0: 10.0,
    40.0: 40.0,
    70.0: 60.0,
    100.0: 80.0,
}


def _outside_temp(sim_time_s: float, config: SimulationConfig) -> float:
    if config.use_host_time:
        now = time.time()
        tm = time.localtime(now)
        day_phase = (tm.tm_hour + tm.tm_min / 60.0 + tm.tm_sec / 3600.0) / 24.0
        season_phase = 2.0 * math.pi * ((tm.tm_yday - config.outside_temp_seasonal_peak_doy) / 365.0)
        seasonal_offset = config.outside_temp_seasonal_swing_c * math.cos(season_phase)
        return config.outside_temp_base_c + seasonal_offset + config.outside_temp_swing_c * math.sin(2.0 * math.pi * day_phase)
    phase = (sim_time_s % config.outside_temp_period_s) / config.outside_temp_period_s
    return config.outside_temp_base_c + config.outside_temp_swing_c * math.sin(2.0 * math.pi * phase)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _time_of_day_h(sim_time_s: float, use_host_time: bool) -> float:
    if use_host_time:
        tm = time.localtime()
        return tm.tm_hour + (tm.tm_min / 60.0) + (tm.tm_sec / 3600.0)
    return (sim_time_s / 3600.0) % 24.0


def _stage_fan_level(command_level: float, stages: tuple) -> float:
    if command_level <= 0.0:
        return 0.0
    for stage in stages[1:]:
        if command_level <= stage:
            return stage
    return stages[-1]


def _ventilation_flow_m3_s(fan_level: float, inlet_open_pct: float, config: SimulationConfig) -> float:
    inlet_factor = 0.2 + 0.8 * (inlet_open_pct / 100.0)
    fan_flow = config.fan_max_flow_m3_s * (fan_level / 100.0) * inlet_factor
    return config.base_infiltration_m3_s + fan_flow


def step(state: EnvironmentState, config: SimulationConfig, dt_s: float) -> None:
    """
    Advance the environment dt_s seconds.
    Uses a physically-based thermal and gas mass-balance model.
    """

    state.sim_time_s += dt_s

    state.bird_count = config.bird_count
    state.barn_volume_m3 = config.barn_volume_m3

    # AUTO-CONTROL (HYSTERESIS)
    auto_control_active = state.auto_control and state.sim_time_s >= config.startup_override_s
    if auto_control_active:
        now = state.sim_time_s
        fan_stale = state.fan_cmd_last_s == 0.0 or now - state.fan_cmd_last_s >= config.auto_control_timeout_s
        if fan_stale:
            if state.temperature_c >= config.fan_on_temp_c:
                state.fan_level_command = max(state.fan_level_command, config.auto_fan_level)
            elif state.temperature_c <= config.fan_off_temp_c:
                state.fan_level_command = 0.0

        heater_stale = state.heater_cmd_last_s == 0.0 or now - state.heater_cmd_last_s >= config.auto_control_timeout_s
        if heater_stale:
            if state.temperature_c <= config.heater_on_temp_c:
                state.heater_level_command = 100.0
            elif state.temperature_c >= config.heater_off_temp_c:
                state.heater_level_command = 0.0

        inlet_stale = state.inlet_cmd_last_s == 0.0 or now - state.inlet_cmd_last_s >= config.auto_control_timeout_s
        if inlet_stale:
            staged_fan = _stage_fan_level(state.fan_level_command, config.fan_stages)
            state.inlet_open_pct_command = INLET_FOR_STAGE.get(staged_fan, state.inlet_open_pct_command)

        light_stale = state.light_cmd_last_s == 0.0 or now - state.light_cmd_last_s >= config.auto_control_timeout_s
        if light_stale:
            time_of_day_h = _time_of_day_h(state.sim_time_s, config.use_host_time)
            if config.lights_on_h <= time_of_day_h < config.lights_off_h:
                state.light_level_pct_command = config.light_day_pct
            else:
                state.light_level_pct_command = config.light_night_pct

    if state.sim_time_s < config.startup_override_s:
        state.fan_level_command = 0.0
        state.heater_level_command = 0.0
        state.inlet_open_pct_command = 0.0
        state.light_level_pct_command = 0.0

    # Clamp requested actuator values
    state.fan_level_command = _clamp(state.fan_level_command, 0.0, 100.0)
    state.heater_level_command = _clamp(state.heater_level_command, 0.0, 100.0)
    state.inlet_open_pct_command = _clamp(state.inlet_open_pct_command, 0.0, 100.0)
    state.light_level_pct_command = _clamp(state.light_level_pct_command, 0.0, 100.0)

    # ACTUATOR DYNAMICS
    now = state.sim_time_s

    desired_fan_on = state.fan_level_command > 0.0
    if desired_fan_on != state.fan_on:
        elapsed = now - state.fan_last_switch_s
        if desired_fan_on and elapsed >= config.min_fan_off_s:
            state.fan_on = True
            state.fan_last_switch_s = now
        elif (not desired_fan_on) and elapsed >= config.min_fan_on_s:
            state.fan_on = False
            state.fan_last_switch_s = now

    staged_target = _stage_fan_level(state.fan_level_command, config.fan_stages)
    target_fan_level = staged_target if state.fan_on else 0.0
    dt_min = dt_s / 60.0
    max_step = config.fan_ramp_per_min * dt_min
    delta = target_fan_level - state.fan_level
    if delta > max_step:
        delta = max_step
    elif delta < -max_step:
        delta = -max_step
    state.fan_level = _clamp(state.fan_level + delta, 0.0, 100.0)

    heater_step = config.heater_ramp_per_min * dt_min
    heater_delta = state.heater_level_command - state.heater_level
    if heater_delta > heater_step:
        heater_delta = heater_step
    elif heater_delta < -heater_step:
        heater_delta = -heater_step
    state.heater_level = _clamp(state.heater_level + heater_delta, 0.0, 100.0)

    inlet_step = config.inlet_ramp_per_min * dt_min
    inlet_delta = state.inlet_open_pct_command - state.inlet_open_pct
    if inlet_delta > inlet_step:
        inlet_delta = inlet_step
    elif inlet_delta < -inlet_step:
        inlet_delta = -inlet_step
    state.inlet_open_pct = _clamp(state.inlet_open_pct + inlet_delta, 0.0, 100.0)

    light_step = config.light_ramp_per_min * dt_min
    light_delta = state.light_level_pct_command - state.light_level_pct
    if light_delta > light_step:
        light_delta = light_step
    elif light_delta < -light_step:
        light_delta = -light_step
    state.light_level_pct = _clamp(state.light_level_pct + light_delta, 0.0, 100.0)

    # VENTILATION FLOW
    flow_m3_s = _ventilation_flow_m3_s(state.fan_level, state.inlet_open_pct, config)

    # TEMPERATURE DYNAMICS
    outside_temp = _outside_temp(state.sim_time_s, config)
    heat_capacity_j_per_k = config.air_density * config.air_cp * config.barn_volume_m3 * config.thermal_mass_factor

    q_loss = config.barn_ua_w_per_k * (state.temperature_c - outside_temp)
    q_vent = config.air_density * config.air_cp * flow_m3_s * (state.temperature_c - outside_temp)
    q_heater = config.heater_power_w * (state.heater_level / 100.0)

    bird_heat_w = config.bird_count * (config.bird_heat_w_base + config.bird_heat_w_activity * state.activity)

    dtemp = (q_heater + bird_heat_w - q_loss - q_vent) / heat_capacity_j_per_k
    state.temperature_c = _clamp(state.temperature_c + dtemp * dt_s, 10.0, 40.0)

    # CO2 DYNAMICS (mass balance)
    co2_lps = config.co2_lps_per_bird * (1.0 + config.co2_activity_mult * state.activity)
    co2_m3_s = (co2_lps * config.bird_count) / 1000.0
    co2_gen_ppm_s = (co2_m3_s / config.barn_volume_m3) * 1.0e6
    co2_vent_ppm_s = (flow_m3_s / config.barn_volume_m3) * (config.outside_co2_ppm - state.co2_ppm)

    state.co2_ppm += (co2_gen_ppm_s + co2_vent_ppm_s) * dt_s
    state.co2_ppm = _clamp(state.co2_ppm, 400.0, 6000.0)

    # NH3 DYNAMICS (emission + ventilation + decay)
    temp_factor = max(0.0, state.temperature_c - 20.0)
    nh3_mg_s = (
        config.nh3_mg_s_per_bird
        * config.bird_count
        * (1.0 + config.nh3_activity_mult * state.activity)
        * (1.0 + config.nh3_temp_coeff * temp_factor)
    )

    # Convert mg/s to ppm/s: ppm = mg/m3 * (24.45 / 17.0)
    nh3_ppm_gen_s = (nh3_mg_s / config.barn_volume_m3) * (24.45 / 17.0)
    nh3_vent_ppm_s = (flow_m3_s / config.barn_volume_m3) * (0.0 - state.nh3_ppm)
    nh3_decay_ppm_s = -config.nh3_decay_per_s * state.nh3_ppm

    state.nh3_ppm += (nh3_ppm_gen_s + nh3_vent_ppm_s + nh3_decay_ppm_s) * dt_s
    state.nh3_ppm = _clamp(state.nh3_ppm, 0.0, 200.0)

    # FEED & WATER DYNAMICS
    feed_kg_s = (config.feed_g_per_bird_day / 1000.0) / 86400.0
    feed_rate = config.bird_count * feed_kg_s * (0.6 + config.feed_activity_mult * state.activity)
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
            config.feed_hopper_capacity_kg,
            state.feed_kg + config.feed_refill_flow_kg_s * dt_s,
        )

    water_l_s = config.water_l_per_bird_day / 86400.0
    water_rate = config.bird_count * water_l_s * (0.7 + config.water_activity_mult * state.activity)
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
            config.water_tank_capacity_l,
            state.water_l + config.water_refill_flow_l_s * dt_s,
        )

    # ACTIVITY DYNAMICS
    time_of_day_h = _time_of_day_h(state.sim_time_s, config.use_host_time)
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
    activity_tau_s = config.activity_time_constant_min * 60.0
    state.activity += (target_activity - state.activity) * (dt_s / activity_tau_s)
    state.activity = _clamp(state.activity, 0.0, 1.0)


