# monitor/monitor_service.py
import json
from common.mqtt_utils import create_mqtt_client
from common.knowledge import KnowledgeStore

def start_monitor():
    ks = KnowledgeStore()
    mqtt_client = create_mqtt_client("monitor")

    # Subscribe to all farms, all zones 
    # Topic format: {farm_id}/{zone_id}/sensors/{sensor_type}
    topic = "+/+/sensors/+"
    print(f"[MONITOR] Subscribing to {topic}")
    mqtt_client.subscribe(topic)

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            print(f"[MONITOR] Invalid JSON on {msg.topic}")
            return

        parts = msg.topic.split("/")  # [farm, zone, 'sensors', sensor_type]
        if len(parts) != 4:
            print(f"[MONITOR] Unexpected topic structure: {msg.topic}")
            return

        farm_id, zone, _, sensor_type = parts

        if sensor_type == "air":
            temp = data.get("temperature_c")
            co2 = data.get("co2_ppm")
            nh3 = data.get("nh3_ppm")
            if temp is not None:
                ks.log_sensor(zone, "temperature", float(temp), farm_id=farm_id)
            if co2 is not None:
                ks.log_sensor(zone, "co2", float(co2), farm_id=farm_id)
            if nh3 is not None:
                ks.log_sensor(zone, "ammonia", float(nh3), farm_id=farm_id)

        elif sensor_type == "feed_level":
            feed = data.get("feed_kg")
            if feed is not None:
                ks.log_sensor(zone, "feed_level", float(feed), farm_id=farm_id)

        elif sensor_type == "water_level":
            water = data.get("water_l")
            if water is not None:
                ks.log_sensor(zone, "water_level", float(water), farm_id=farm_id)

        elif sensor_type == "activity":
            activity = data.get("activity")
            if activity is not None:
                ks.log_sensor(zone, "activity", float(activity), farm_id=farm_id)

        else:
            print(f"[MONITOR] Unknown sensor type: {sensor_type}")

    mqtt_client.on_message = on_message
    mqtt_client.loop_forever()
