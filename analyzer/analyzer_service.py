# analyzer/analyzer_service.py
import json
import time

from common.mqtt_utils import create_mqtt_client
from common.config import (
    load_system_config, get_config,
    FARM_ID, ZONE_ID
)
from common.knowledge import KnowledgeStore

STATUS_INTERVAL_S = 5.0


def build_status(ks: KnowledgeStore, farm_id: str, zone: str, sys_config: dict) -> dict:
    # Pass farm_id to get_latest_sensor_value
    temp = ks.get_latest_sensor_value(zone, "temperature", farm_id=farm_id)
    co2 = ks.get_latest_sensor_value(zone, "co2", farm_id=farm_id)
    nh3 = ks.get_latest_sensor_value(zone, "ammonia", farm_id=farm_id)
    feed = ks.get_latest_sensor_value(zone, "feed_level", farm_id=farm_id)
    water = ks.get_latest_sensor_value(zone, "water_level", farm_id=farm_id)
    activity = ks.get_latest_sensor_value(zone, "activity", farm_id=farm_id)

    # Resolve thresholds dynamically
    temp_min = float(get_config("temp_min", sys_config, farm_id, zone))
    temp_max = float(get_config("temp_max", sys_config, farm_id, zone))
    co2_max = float(get_config("co2_max", sys_config, farm_id, zone))
    nh3_threshold = float(get_config("nh3_threshold", sys_config, farm_id, zone))
    feed_threshold = float(get_config("feed_threshold", sys_config, farm_id, zone))
    water_threshold = float(get_config("water_threshold", sys_config, farm_id, zone))
    activity_min = float(get_config("activity_min", sys_config, farm_id, zone))

    temp_ok = temp is not None and temp_min <= temp <= temp_max
    co2_ok = co2 is not None and co2 <= co2_max
    nh3_ok = nh3 is not None and nh3 <= nh3_threshold
    feed_ok = feed is not None and feed >= feed_threshold
    water_ok = water is not None and water >= water_threshold
    activity_ok = activity is not None and activity >= activity_min

    alerts = []
    if temp is None:
        alerts.append("No temperature")
    elif temp < temp_min:
        alerts.append("Too cold")
    elif temp > temp_max:
        alerts.append("Too hot")

    if co2 is None:
        alerts.append("No CO2")
    elif not co2_ok:
        alerts.append("High CO2")

    if nh3 is None:
        alerts.append("No NH3")
    elif not nh3_ok:
        alerts.append("High NH3")

    if feed is None:
        alerts.append("No feed data")
    elif not feed_ok:
        alerts.append("Low feed")

    if water is None:
        alerts.append("No water data")
    elif not water_ok:
        alerts.append("Low water")

    if activity is None:
        alerts.append("No activity")
    elif not activity_ok:
        alerts.append("Low activity")

    alert_text = " & ".join(alerts) if alerts else "OK"

    return {
        "farm_id": farm_id,
        "zone": zone,
        "temperature_c": temp,
        "co2_ppm": co2,
        "nh3_ppm": nh3,
        "feed_kg": feed,
        "water_l": water,
        "activity": activity,
        "temp_ok": temp_ok,
        "co2_ok": co2_ok,
        "nh3_ok": nh3_ok,
        "feed_ok": feed_ok,
        "water_ok": water_ok,
        "activity_ok": activity_ok,
        "alert": alert_text,
    }


def start_analyzer():
    print("[ANALYZER] Starting...")
    
    ks = KnowledgeStore()
    mqtt_client = create_mqtt_client("analyzer")
    mqtt_client.loop_start()

    while True:
        # Reload config dynamically
        system_config = load_system_config()
        farms = system_config.get("farms", [])

        for farm in farms:
            f_id = farm["id"]
            zones = farm.get("zones", [])
            for z_id in zones:
                # Handle zone being just a string or object
                if isinstance(z_id, dict):
                    z_name = z_id["id"]
                else:
                    z_name = z_id

                try:
                    status = build_status(ks, f_id, z_name, system_config)
                    
                    # Log symptoms to knowledge base
                    ks.log_symptom(
                        zone=z_name,
                        farm_id=f_id,
                        symptoms={
                            "temp_ok": status["temp_ok"],
                            "co2_ok": status["co2_ok"],
                            "nh3_ok": status["nh3_ok"],
                            "feed_ok": status["feed_ok"],
                            "water_ok": status["water_ok"],
                            "activity_ok": status["activity_ok"],
                            "alert": status["alert"],
                        }
                    )
                    
                    topic = f"{f_id}/{z_name}/status"
                    payload_str = json.dumps(status)
                    mqtt_client.publish(topic, payload_str)
                    print(f"[ANALYZER] Published status to {topic}: {payload_str}")
                except Exception as e:
                    print(f"[ANALYZER] Error during analysis for {f_id}/{z_name}: {e}")
        
        time.sleep(STATUS_INTERVAL_S)

