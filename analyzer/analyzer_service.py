# analyzer/analyzer_service.py
import json
import time

from common.mqtt_utils import create_mqtt_client
from common.config import (
    FARM_ID,
    ZONE_ID,
    TEMP_MIN,
    TEMP_MAX,
    NH3_THRESHOLD,
    FEED_THRESHOLD,
    WATER_THRESHOLD,
    ACTIVITY_MIN,
    CO2_MAX,
)
from common.knowledge import KnowledgeStore

STATUS_INTERVAL_S = 5.0


def build_status(ks: KnowledgeStore, zone: str) -> dict:
    temp = ks.get_latest_sensor_value(zone, "temperature")
    co2 = ks.get_latest_sensor_value(zone, "co2")
    nh3 = ks.get_latest_sensor_value(zone, "ammonia")
    feed = ks.get_latest_sensor_value(zone, "feed_level")
    water = ks.get_latest_sensor_value(zone, "water_level")
    activity = ks.get_latest_sensor_value(zone, "activity")

    temp_ok = temp is not None and TEMP_MIN <= temp <= TEMP_MAX
    co2_ok = co2 is not None and co2 <= CO2_MAX
    nh3_ok = nh3 is not None and nh3 <= NH3_THRESHOLD
    feed_ok = feed is not None and feed >= FEED_THRESHOLD
    water_ok = water is not None and water >= WATER_THRESHOLD
    activity_ok = activity is not None and activity >= ACTIVITY_MIN

    alerts = []
    if temp is None:
        alerts.append("No temperature")
    elif temp < TEMP_MIN:
        alerts.append("Too cold")
    elif temp > TEMP_MAX:
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

    while True:
        try:
            status = build_status(ks, ZONE_ID)
            topic = f"{FARM_ID}/{ZONE_ID}/status"
            payload_str = json.dumps(status)
            mqtt_client.publish(topic, payload_str)
            print(f"[ANALYZER] Published status to {topic}: {payload_str}")
        except Exception as e:
            print(f"[ANALYZER] Error during analysis: {e}")
        time.sleep(STATUS_INTERVAL_S)
