# Autonomous Poultry Farm Manager (Microservices)

A self-adaptive system using the MAPE-K loop pattern to manage a poultry farm environment, refactored into a microservices architecture.

## Architecture
The system is composed of several Docker containers, orchestrated via Docker Compose:

-   **Managed Resources (Simulator)**: Simulates the physical barn (Sensors/Actuators).
-   **Configuration Service**: Flask API serving `config.json` (thresholds).
-   **Monitor**: Subscribes to MQTT sensors, logs to DB.
-   **Analyzer**: Checks thresholds (fetched from Config) -> MQTT `farm/analysis`.
-   **Planner**: Listens to analysis -> Plans actions (Actuator config) -> MQTT `farm/plan`.
-   **Executor**: Listens to plans -> Publishes MQTT commands -> Logs to DB.
-   **Mosquitto**: MQTT Broker.
-   **InfluxDB**: Time-series database for sensor data and actuator logs.
-   **Grafana**: Monitoring and visualization dashboard for real-time sensor data and actuator logs.

## Prerequisites
-   Docker Desktop

## Setup & Run
1.  **Build and Run**:
    ```bash
    docker compose up --build
    ```
    *Note: The first time will take a while to build all python images.*

2.  **Verify**:
    -   **MQTT**: Connect to `localhost:1883`.
    -   **Config API**: Visit `http://localhost:5001/config/all`.
    -   **InfluxDB**: Connect to `http://localhost:8086` (user: admin, password: adminadmin, org: poultry_farm, bucket: poultry_farm).
    -   **Grafana**: Visit `http://localhost:3000` (user: admin, password: admin).

## Project Structure
```text
src/
├── configuration/   # Flask Param Service
├── monitor/         # Monitor Service
├── analyzer/        # Analyzer Service
├── planner/         # Planner Service
├── executor/        # Executor Service
└── managed_resources/ # Simulator

grafana/
├── provisioning/
│   ├── datasources/  # InfluxDB datasource configuration
│   └── dashboards/   # Dashboard definitions
```

## Monitoring & Visualization

### Grafana Dashboard

Grafana is pre-configured with:
- **InfluxDB Datasource**: Automatically configured on startup
- **Poultry Farm Monitoring Dashboard**: Pre-built dashboard with:
  - Temperature monitoring (with thresholds)
  - Ammonia (Air Quality) monitoring
  - Feed Level tracking
  - Water Level tracking
  - Current sensor values panel
  - Actuator logs table

**Access Grafana:**
1. Navigate to `http://localhost:3000`
2. Login with:
   - Username: `admin`
   - Password: `admin`
3. The dashboard will be available in the Dashboards section

**Dashboard Features:**
- Real-time sensor data visualization (1-hour window)
- Color-coded thresholds for alerts
- Actuator activity logs
- Auto-refresh every 5 seconds

## Data Flow

See `DATA_FLOW_DOCUMENTATION.md` for detailed information on how data enters the system.

**Quick Summary:**
1. **Sensors** (Managed Resources) publish data to MQTT every 2 seconds
2. **Monitor** service subscribes to MQTT and stores data in InfluxDB
3. **Executor** service logs actuator actions directly to InfluxDB
4. **Grafana** visualizes data from InfluxDB in real-time
