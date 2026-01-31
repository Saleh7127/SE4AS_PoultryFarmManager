# Project Description: Autonomous Poultry Farm Manager

## 1. Introduction
This project is an **Autonomous Self-Adaptive System (SAS)** designed to manage the delicate environment of modern poultry farms.

### The Problem
Poultry birds are extremely sensitive to environmental changes.
*   **Temperature**: Too hot (>28°C) = Heat stress/death. Too cold (<20°C) = Sickness.
*   **Air Quality**: CO2 and Ammonia (from waste) can damage respiratory systems.
*   **Complexity**: Turning on fans cools the air (good for temp) but can draft birds (bad). 

Managing this manually 24/7 is impossible for large farms.

### The Solution
We built a software system that acts as an "Autopilot" for the farm. It creates a closed feedback loop: it watches the sensors, thinks about what to do, and controls the fans/heaters continuously.

---

## 2. Architecture: MAPE-K Matrix
We follow the **MAPE-K** architectural pattern (Monitor, Analyze, Plan, Execute, Knowledge) widely used in autonomous computing.

| Component | Role | Analogous Human Action |
| :--- | :--- | :--- |
| **Managed System** | The physical farm (simulated here). | The Barn itself. |
| **Monitor (M)** | Data Collection. | Checking the thermometer. |
| **Analyzer (A)** | Diagnosis. | Thinking "It's too hot in here." |
| **Planner (P)** | Decision Making. | Deciding "I should turn on the fan." |
| **Executor (E)** | Action. | Walking to the switch and hitting it. |
| **Knowledge (K)** | Memory & Rules. | Knowing that 28°C is the danger limit. |

---

## 3. How It Works (End-to-End Flow)

Let's trace a single "Heartbeat" of the system:

1.  **Simulation Tick**: The `Environment` service simulates 5 seconds of physics. The temperature rises because of the birds' body heat.
2.  **Sensing**: The environment publishes a message to MQTT: 
    *   `Topic`: `farm1/zone1/sensors/air`
    *   `Payload`: `{"temperature_c": 28.5, "co2_ppm": 1200}`
3.  **Monitoring**: The `Monitor` service sees this message and saves it to **InfluxDB** (Knowledge).
4.  **Analysis**: The `Analyzer` service wakes up, reads the latest data from InfluxDB, and compares it to `system_config.json`.
    *   *Rule*: Temp limit is 28.0.
    *   *Reality*: Temp is 28.5.
    *   *Result*: Uses MQTT to broadcast: `STATUS = CRITICAL (High Temp)`.
5.  **Planning**: The `Planner` service receives the Status.
    *   It calculates the error (0.5°C over limit).
    *   It uses a **P-Controller** to calculate required cooling: `Fan_Speed = Error * Kp = 0.5 * 10 = 5% increase`.
    *   It publishes a **Plan** to MQTT.
6.  **Execution**: The `Executor` service translates the Plan into a specific hardware command.
    *   `Topic`: `farm1/zone1/cmd/fan`
    *   `Payload`: `{"action": "SET", "level": 60}`
7.  **Actuation**: The `Environment` receives the command, spins up the simulated fan, and the temperature starts dropping.

---

## 4. Components in Detail

### Environment (The Simulator)
*   **File**: `environment/model.py`
*   **Physics**: Uses thermodynamic equations (`Q = m*c*dT`) to calculate heat transfer, gas mixing, and thermal mass.
*   **Biology**: Simulates bird metabolism (heat/CO2 output) based on activity levels.

### Monitor
*   **File**: `monitor/monitor_service.py`
*   **Job**: pure data ingestion. It ensures all sensor data is captured for history.

### Analyzer
*   **File**: `analyzer/analyzer_service.py`
*   **Job**: Symptom Detection. It simplifies complex data into simple states: `NORMAL`, `WARNING`, `CRITICAL`.

### Planner
*   **File**: `planner/planner_service.py`
*   **Job**: The Brain.
    *   **Continuous Control**: Uses P-Controllers for Fans/Heaters to smooth out fluctuations.
    *   **Hysteresis**: Uses on/off logic for Feed/Water refill to prevent rapid toggling (chattering).

### Executor
*   **File**: `executor/executor_service.py`
*   **Job**: The Hands. It abstracts the hardware details from the Planner.

---

## 5. How to Manually Control (MQTT Guide)

You can interact with the system manually by sending MQTT messages. This mimics what the Executor does.

### Tools
You can use `mosquitto_pub` inside the docker container or any desktop MQTT client (like MQTT Explorer).

### Command Structure
*   **Topic**: `{farm_id}/{zone_id}/cmd/{actuator}`
*   **Actuators**: `fan`, `heater`, `inlet`, `light`, `feed_dispenser`, `water_valve`.

### Examples

**1. Turn on the Fan to 100%**
```bash
docker compose exec mqtt mosquitto_pub -t "farm1/zone1/cmd/fan" -m '{"action": "SET", "level": 100}'
```

**2. Turn on the Heater**
```bash
docker compose exec mqtt mosquitto_pub -t "farm1/zone1/cmd/heater" -m '{"action": "SET", "level_pct": 50}'
```

**3. Refill the Feed Hopper**
```bash
docker compose exec mqtt mosquitto_pub -t "farm1/zone1/cmd/feed_dispenser" -m '{"action": "ON"}'
```
*Note: The simulation will react to these commands immediately, but the Planner might fight you and turn them back off if it disagrees!*
