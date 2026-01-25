from dataclasses import dataclass
import math

@dataclass
class EnvironmentState:
    # --- SENSORS (6) ---
    temperature_c: float = 22.0
    co2_ppm: float = 1800.0
    nh3_ppm: float = 20.0
    feed_kg: float = 0.1
    water_l: float = 0.1
    activity: float = 0.2

    # --- ACTUATORS (6) ---
    fan_level: float = 0.0           # actual fan output 0–100%
    fan_level_command: float = 0.0   # what planner asked for
    heater_on: bool = False
    heater_last_switch_s: float = 0.0
    inlet_open_pct: float = 30.0
    light_level_pct: float = 10.0

    # internal time for demo behavior
    sim_time_s: float = 0.0

def step(state: EnvironmentState, dt_s: float) -> None:
    """
    Advance the environment dt_s seconds.
    Physics is still simplified, but tuned to be slower and more barn-like.
    """

    state.sim_time_s += dt_s

    # --------------------------
    # 0. ACTUATOR DYNAMICS
    # --------------------------
    # Fan does not jump instantly; it ramps towards the commanded level.
    MAX_FAN_CHANGE_PER_S = 5.0  # % per second
    delta = state.fan_level_command - state.fan_level
    max_step = MAX_FAN_CHANGE_PER_S * dt_s
    if delta > max_step:
        delta = max_step
    elif delta < -max_step:
        delta = -max_step
    state.fan_level = max(0.0, min(100.0, state.fan_level + delta))

    # --------------------------
    # 1. FEED & WATER DYNAMICS
    # --------------------------
    # Base feed consumption ~0.09 kg/h per "flock unit"
    feed_consumption = 0.000025 * dt_s  # kg/s

    # Birds eat less if water is low
    if state.water_l < 0.5:
        feed_consumption *= 0.5
    # Eat more when activity high
    if state.activity > 0.6:
        feed_consumption *= 1.3

    state.feed_kg = max(0.0, state.feed_kg - feed_consumption)

    # Water consumption: ~0.04 L/h base
    water_consumption = 0.000011 * dt_s  # L/s

    # Drink more when hot
    if state.temperature_c > 26:
        water_consumption *= 1.5

    state.water_l = max(0.0, state.water_l - water_consumption)

    # --------------------------
    # 2. TEMPERATURE
    # --------------------------
    # Outside air: 24 h sine wave compressed to shorter sim (~1h cycle)
    day_phase = math.sin((state.sim_time_s / 1800.0) * math.pi)  # ~1 h period
    outside_temp = 20.0 + 4.0 * day_phase  # 16–24°C range

    # Small drift towards outside temperature (thermal mass)
    toward_outside = (outside_temp - state.temperature_c) * 0.0005 * dt_s

    # Birds generate heat slowly
    bird_heat = 0.001 * dt_s  # +0.06 °C/min

    # Ventilation effect depends on both fan and inlet position
    vent_factor = (state.fan_level / 100.0) * (state.inlet_open_pct / 100.0)

    # Fan cools via ventilation
    fan_cooling = 0.008 * vent_factor * dt_s  # up to ~0.48 °C/min at full vent

    # Heater warms moderately when ON
    heater_heat = 0.005 * dt_s if state.heater_on else 0.0  # ~0.3 °C/min

    state.temperature_c += toward_outside + bird_heat + heater_heat - fan_cooling
    state.temperature_c = max(10.0, min(40.0, state.temperature_c))

    # --------------------------
    # 3. CO2 DYNAMICS
    # --------------------------
    # Birds produce CO2
    co2_prod = 5.0 * dt_s  # ppm/s ~300 ppm/min

    # Ventilation removes it, scaled by vent_factor
    co2_vent = 15.0 * vent_factor * dt_s

    state.co2_ppm += co2_prod - co2_vent
    state.co2_ppm = max(400.0, min(6000.0, state.co2_ppm))

    # --------------------------
    # 4. NH3 DYNAMICS
    # --------------------------
    nh3_base = 0.01 * dt_s
    # More ammonia when warm
    if state.temperature_c > 26:
        nh3_base += (state.temperature_c - 26.0) * 0.005 * dt_s

    # Ventilation removes ammonia
    nh3_vent = 0.03 * vent_factor * dt_s

    state.nh3_ppm += nh3_base - nh3_vent
    state.nh3_ppm = max(0.0, min(100.0, state.nh3_ppm))

    # --------------------------
    # 5. ACTIVITY
    # --------------------------
    target = 0.7

    # Too cold or too hot reduces activity
    if state.temperature_c < 22 or state.temperature_c > 30:
        target -= 0.3
    # Bad air quality reduces activity
    if state.co2_ppm > 2500 or state.nh3_ppm > 35:
        target -= 0.2
    # Feed/water issues
    if state.feed_kg < 0.5:
        target -= 0.2
    if state.water_l < 0.4:
        target -= 0.2

    # Simple day–night effect: lower activity at night
    # (simulated 24h clock using sim_time_s)
    time_of_day_h = (state.sim_time_s / 3600.0) % 24.0
    if time_of_day_h < 6.0 or time_of_day_h > 20.0:
        target -= 0.2

    target = max(0.0, min(1.0, target))
    state.activity += (target - state.activity) * 0.05 * dt_s
    state.activity = max(0.0, min(1.0, state.activity))

    # --------------------------
    # 6. LIGHT / LUX (for demo)
    # --------------------------
    # Light level is actuator-driven (no extra dynamics here yet)
    # base_lux = (state.light_level_pct / 100.0) * 200.0
