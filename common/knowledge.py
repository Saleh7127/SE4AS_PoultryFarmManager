# common/knowledge.py
import os
from typing import Optional, List, Dict, Any

from influxdb_client import Point, InfluxDBClient
from influxdb_client.client.query_api import QueryApi

from common.influx_utils import create_influx_client
from common.config import (
    SENSOR_MEASUREMENT,
    ACTUATOR_MEASUREMENT,
    SYMPTOM_MEASUREMENT,
    PLAN_MEASUREMENT,
    FARM_ID,
)

INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET")
INFLUX_ORG = os.getenv("INFLUXDB_ORG")


class KnowledgeStore:
    """
    Knowledge layer that abstracts access to InfluxDB.

    - Writers: log_sensor(), log_actuator_command()
    - Readers: get_latest_sensor_value(), get_sensor_history(), etc.

    All other components (monitor, analyzer, executor) should talk to this
    instead of using InfluxDB directly.
    """

    def __init__(self) -> None:
        self._client: InfluxDBClient = create_influx_client()
        self._write_api = self._client.write_api()
        self._query_api: QueryApi = self._client.query_api()

    def log_sensor(
        self,
        zone: str,
        sensor_type: str,
        value: float,
        extra_tags: Optional[Dict[str, str]] = None,
        farm_id: Optional[str] = None,
    ) -> None:
        """
        Store a single sensor reading.

        sensor_type examples: "temperature", "co2", "ammonia",
                              "feed_level", "water_level", "activity"
        """
        farm = farm_id if farm_id else FARM_ID
        tags = {"farm": farm, "zone": zone, "type": sensor_type}
        if extra_tags:
            tags.update(extra_tags)

        point = Point(SENSOR_MEASUREMENT)
        for k, v in tags.items():
            point = point.tag(k, v)
        point = point.field("value", float(value))

        self._write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

    def log_actuator_command(
        self,
        zone: str,
        actuator: str,
        state_str: str,
        numeric_fields: Optional[Dict[str, float]] = None,
        payload: Optional[str] = None,
        farm_id: Optional[str] = None,
    ) -> None:
        """
        Store an actuator command + state.

        numeric_fields can hold things like {"level": 60} or {"duration_s": 15}
        """
        farm = farm_id if farm_id else FARM_ID
        tags = {"farm": farm, "zone": zone, "actuator": actuator}

        point = Point(ACTUATOR_MEASUREMENT)
        for k, v in tags.items():
            point = point.tag(k, v)

        point = point.field("state", state_str)
        if numeric_fields:
            for k, v in numeric_fields.items():
                point = point.field(k, v)

        if payload is not None:
            point = point.field("payload", payload)

        self._write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

    def log_symptom(
        self,
        zone: str,
        symptoms: Dict[str, Any],
        farm_id: Optional[str] = None,
    ) -> None:
        """
        Store analysis symptoms (e.g. alerts, health checks).
        symptoms dict should contain boolean flags or simple values.
        e.g. {"temp_ok": False, "alert_text": "Too cold"}
        """
        farm = farm_id if farm_id else FARM_ID
        tags = {"farm": farm, "zone": zone}
        
        point = Point(SYMPTOM_MEASUREMENT)
        for k, v in tags.items():
            point = point.tag(k, v)
            
        for k, v in symptoms.items():
            if k == "alert": 
                 point = point.field(k, str(v))
            elif isinstance(v, bool):
                 point = point.field(k, v)
            elif isinstance(v, (int, float)):
                 point = point.field(k, float(v))
            else:
                 point = point.field(k, str(v))

        self._write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

    def log_plan(
        self,
        zone: str,
        plan_actions: List[Dict[str, Any]],
        farm_id: Optional[str] = None,
    ) -> None:
        """
        Store the Planner's intent.
        plan_actions is a list of dicts: [{"actuator": "fan", "command": {...}, "priority": 1}]
        Each action becomes a point.
        """
        farm = farm_id if farm_id else FARM_ID
        points = []
        for action in plan_actions:
            actuator = action.get("actuator", "unknown")
            priority = action.get("priority", 0)
            command = action.get("command", {})

            point = Point(PLAN_MEASUREMENT)
            point = point.tag("farm", farm)
            point = point.tag("zone", zone)
            point = point.tag("actuator", actuator)
            
            point = point.field("priority", int(priority))
            
            # Flatten command fields
            for k, v in command.items():
                field_name = f"cmd_{k}"
                if isinstance(v, bool):
                    point = point.field(field_name, v)
                elif isinstance(v, (int, float)):
                    point = point.field(field_name, float(v))
                else:
                    point = point.field(field_name, str(v))
            
            points.append(point)

        if points:
             self._write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)

    def get_latest_sensor_value(
        self,
        zone: str,
        sensor_type: str,
        window: str = "-10m",
        farm_id: Optional[str] = None,
    ) -> Optional[float]:
        """
        Return the latest sensor value for given zone/type in the last `window`.
        """
        farm = farm_id if farm_id else FARM_ID
        flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {window})
  |> filter(fn: (r) => r["_measurement"] == "{SENSOR_MEASUREMENT}")
  |> filter(fn: (r) => r["farm"] == "{farm}")
  |> filter(fn: (r) => r["zone"] == "{zone}")
  |> filter(fn: (r) => r["type"] == "{sensor_type}")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
'''
        tables = self._query_api.query(flux, org=INFLUX_ORG)
        for table in tables:
            for record in table.records:
                return float(record.get_value())
        return None

    def get_sensor_history(
        self,
        zone: str,
        sensor_type: str,
        start: str = "-1h",
        agg: Optional[str] = None,
        every: str = "1m",
        farm_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Optional helper: get history for plotting or analysis.

        Returns list of { "time": <ISO>, "value": <float> }
        """
        farm = farm_id if farm_id else FARM_ID
        agg_pipe = ""
        if agg:
            agg_pipe = f'  |> aggregateWindow(every: {every}, fn: {agg}, createEmpty: false)\n'

        flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {start})
  |> filter(fn: (r) => r["_measurement"] == "{SENSOR_MEASUREMENT}")
  |> filter(fn: (r) => r["farm"] == "{farm}")
  |> filter(fn: (r) => r["zone"] == "{zone}")
  |> filter(fn: (r) => r["type"] == "{sensor_type}")
{agg_pipe}
  |> sort(columns: ["_time"], desc: false)
'''
        tables = self._query_api.query(flux, org=INFLUX_ORG)
        result: List[Dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                result.append(
                    {
                        "time": record.get_time().isoformat(),
                        "value": float(record.get_value()),
                    }
                )
        return result
