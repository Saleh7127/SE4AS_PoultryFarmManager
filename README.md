# Autonomous Poultry Farm Manager 🐔

An autonomous, self-adaptive system (SAS) designed to manage environmental conditions in poultry farms using the **MAPE-K** feedback loop architecture.

## 1. The Problem ⚠️
Modern poultry farming requires maintaining strict environmental conditions to ensure bird health, welfare, and productivity.
*   **Complexity**: Temperature, CO2, Ammonia, and Humidity interact in complex ways (e.g., ventilation cools the barn but also removes humidity).
*   **Scale**: Managing dozens of barns manually is labor-intensive and error-prone.
*   **Risks**: System failures (e.g., heater breakdown) or extreme weather can lead to massive losses in minutes.

**Challenge**: How can we build a system that autonomously regulates these conditions, adapts to changing weather, and optimizes for both welfare and energy efficiency?

## 2. The Solution 💡
We implemented a **Self-Adaptive System** that continuously monitors the farm and adjusts actuators (fans, heaters, windows) to maintain optimal conditions.

Key features:
*   **Autonomous Regulation**: Automatically controls Temperature, Air Quality (CO2, NH3), and Light cycles.
*   **Physics-Based Simulation**: Includes a robust environment simulator for testing and validation without risking real animals.
*   **Distributed Architecture**: Uses **MAPE-K** (Monitor, Analyze, Plan, Execute, Knowledge) to separate concerns and allow for independent scaling.
*   **Configurable**: Managing multiple farms/zones with different physics and requirements via a central `system_config.json`.

## 3. Architecture (MAPE-K) 🏛️

The system is built as a set of Docker microservices communicating via an **MQTT Bus**.

<p align="center">
  <img src="system_architecture.png" alt="System Architecture" width="800">
</p>


### Components

1.  **Managed System (Environment)** 🏠
    *   Simulates the physics of the barn (Thermodynamics, Gas laws).
    *   Simulates biological processes (Bird heat output, CO2/NH3 generation, eating/drinking).
    *   **Actuators**: Fans, Heaters, Inlets, Lights, Feeders.
    *   **Sensors**: Temperature, CO2, NH3, Feed Level, Water Level.

2.  **Monitor (M)** 👁️
    *   Ingests raw MQTT sensor data.
    *   Standardizes and logs data into the **Knowledge Base** (InfluxDB).

3.  **Analyzer (A)** 🧠
    *   Periodically queries Knowledge (InfluxDB) and checks against goals (from `system_config.json`).
    *   Detects symptoms (e.g., `symptom: "temp_high"`).
    *   Publishes **Status** events to the bus.

4.  **Planner (P)** 📋
    *   Subscribes to Status events.
    *   Decides on specific actions to resolve symptoms.
    *   Uses **P-Controllers**, **Hysteresis** logic, and (Planned) **Machine Learning** forecasting.
    *   Publishes high-level **Plans**.

5.  **Executor (E)** ⚙️
    *   Translates high-level Plans into specific actuator commands (JSON).
    *   Sends commands to the Environment.

6.  **Knowledge (K)** 📚
    *   **InfluxDB**: Stores time-series history (Simulated "Experience").
    *   **system_config.json**: Stores Policies, Thresholds, and Physics parameters.
    *   **MQTT Retained**: Stores live state.

## 4. Getting Started 🚀

### Prerequisites
*   [Docker Desktop](https://www.docker.com/products/docker-desktop)
*   Git

### Installation
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Saleh7127/SE4AS_PoultryFarmManager.git
    cd SE4AS_PoultryFarmManager
    ```

2.  **Configure Environment**:
    *   **Infrastructure**: Check `.env` for infrastructure settings (MQTT ports, InfluxDB credentials).
    *   **Domain Logic**: Check `system_config.json` for farm rules (Thresholds, Physics).

3.  **Start the System**:
    ```bash
    docker compose up -d --build
    ```

4.  **Access Dashboards**:
    *   **Grafana**: `http://localhost:3000` (User: `admin`, Pass: `admin`)
    *   **InfluxDB**: `http://localhost:8086` (User: `admin`, Pass: `adminadmin`)

## 5. Project Structure 📂

The project follows a microservice structure where each MAPE-K component has its own directory.

*   **`analyzer/`**: (A) Service that checks sensor data against thresholds.
    *   `analyzer_service.py`: Main logic for detecting symptoms.
*   **`planner/`**: (P) Service that decides actions.
    *   `planner_service.py`: Contains P-Controllers and Hysteresis logic.
*   **`executor/`**: (E) Service that sends commands.
    *   `executor_service.py`: Translates plans to MQTT commands.
*   **`monitor/`**: (M) Service that logs data.
    *   `monitor_service.py`: Ingests MQTT data into InfluxDB.
*   **`environment/`**: Managed System Simulation.
    *   `model.py`: Physics and biology simulation (Thermodynamics, CO2, Birds).
    *   `main.py`: Hot-reloading service runner.
    *   `sensors.py`: Simulates sensors.
    *   `actuators.py`: Simulates actuators.
*   **`common/`**: Shared code.
    *   `config.py`: Configuration loader (`system_config.json`).
    *   `knowledge.py`: InfluxDB client wrapper.
*   **`mosquitto/`**: MQTT broker.
*   **`grafana/`**: Grafana.
*   **`system_config.json`**: Central configuration for thresholds, physics, and zones.
*   **`docker-compose.yml`**: Orchestration for all services + MQTT, InfluxDB, Grafana.

## 6. Technologies Used 🛠️
*   **Docker**: Microservice containerization.
*   **Eclipse Mosquitto**: Real-time MQTT messaging bus.
*   **InfluxDB**: Time-series Knowledge Base.
*   **Grafana**: Visualization.
*   **Python**: Core logic (Monitor, Analyzer, Planner, Executor, Environment).

## 7. Configuration Guide ⚙️

| File | Purpose | What to Edit |
| :--- | :--- | :--- |
| **`system_config.json`** | Domain Knowledge | Temperature thresholds, Bird count, Barn insulation, Simulation physics. |
| **`.env`** | Infrastructure | Database passwords, MQTT ports, Service intervals. |
| **`grafana/`** | Visualization | Dashboard JSON models (auto-provisioned). |

