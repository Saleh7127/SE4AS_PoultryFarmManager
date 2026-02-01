# System Taxonomy Classification

## Detailed Classification

### 1. Reason
*   ✅ **Change in the Context**: **YES**.
    *   The system adapts primarily because the environment (context) changes: temperature drops, CO2 rises, ammonia accumulates.
    *   *System Evidence*: The `analyzer` service constantly checks sensor data against thresholds defined in `system_config.json`.
*   ✅ **Change Caused by the User(s)**: **YES**.
    *   The user can override automatic control by sending manual MQTT commands (e.g., turning on a fan manually), forcing the system to adapt its state.
*   ❌ **Change in the Technical Resources**: **NO**.
    *   The system *does not* currently adapt to server failures, network latency, or hardware malfunctions (e.g., a broken fan).

### 2. Level
*   ✅ **Application**: **YES**.
    *   The adaptation logic is embedded in the application layer (`planner`, `analyzer` services) running as Docker containers. It is not operating system or middleware logic.
*   ❌ **System Software**: **NO**.
*   ❌ **Communication**: **NO**.
*   ❌ **Technical Resources**: **NO**.
    *   The logic runs *on* the resource (server) but is not embedded *in* the resource (e.g., smart firmware).
*   ❌ **Context**: **NO**.
    *   The intelligence is not distributed into the environment (e.g., smart dust), but is a centralized software application.

### 3. Time
*   ✅ **Reactive**: **YES**.
    *   The system waits for a problem to appear (e.g., `temp > 26.0`) before acting.
    *   *System Evidence*: The feedback loop acts only *after* sensors report a violation.
*   ❌ **Proactive**: **NO**.
    *   The system does not forecast future states (e.g., predicting weather changes) to act in advance.

### 4. Technique
*   ✅ **Parameter**: **YES**.
    *   The system adapts by changing *parameters* (e.g., Fan Speed 0-100%, Heater Level 0-100%).
*   ❌ **Structure**: **NO**.
    *   We do not dynamically add/remove components or change the software architecture at runtime.
*   ❌ **Context**: **NO**.
    *   We do not adapt by changing our physical location or context (e.g., moving to a deeper server tier).

### 5. Adaptation Control
*   **Approach**: ✅ **External**.
    *   The adaptation logic (MAPE-K loop) is external to the managed resource (the Farm Environment). The "Manager" (Planner/Analyzer) is distinct from the "Managed" (Environment).
*   **Adaptation Decision Criteria**:
    *   ✅ **Goals**: Explicit goals (e.g., "Maintain Temp = 26.0°C").
    *   ✅ **Rules/Policies**: Distinct IF-THEN rules (e.g., "If NH3 > 25, increase ventilation").
*   **Degree of Decentralization**:
    *   ✅ **Centralized**:
        *   A single `planner` instance makes global decisions for the zone based on aggregated data.
    *   ❌ **Decentralized**:
        *   Zones do not negotiate with each other; actuators do not decide for themselves.
