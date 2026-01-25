import os
import json
from influxdb_client import Point
from common.influx_utils import create_influx_client
from common.mqtt_utils import create_mqtt_client
from common.config import FARM_ID, SENSOR_MEASUREMENT

INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET")

def start_monitor():
    influx = create_influx_client()
    write_api = influx.write_api()
    mqtt_client = create_mqtt_client("monitor")

    topic = f"{FARM_ID}/+/sensors/+"
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

        _, zone, _, sensor_type = parts
        points = []

        if sensor_type == "air":
            temp = data.get("temperature_c")
            co2 = data.get("co2_ppm")
            nh3 = data.get("nh3_ppm")
            if temp is not None:
                points.append(
                    Point(SENSOR_MEASUREMENT)
                    .tag("zone", zone)
                    .tag("type", "temperature")
                    .field("value", float(temp))
                )
            if co2 is not None:
                points.append(
                    Point(SENSOR_MEASUREMENT)
                    .tag("zone", zone)
                    .tag("type", "co2")
                    .field("value", float(co2))
                )
            if nh3 is not None:
                points.append(
                    Point(SENSOR_MEASUREMENT)
                    .tag("zone", zone)
                    .tag("type", "ammonia")
                    .field("value", float(nh3))
                )

        elif sensor_type == "feed_level":
            feed = data.get("feed_kg")
            if feed is not None:
                points.append(
                    Point(SENSOR_MEASUREMENT)
                    .tag("zone", zone)
                    .tag("type", "feed_level")
                    .field("value", float(feed))
                )

        elif sensor_type == "water_level":
            water = data.get("water_l")
            if water is not None:
                points.append(
                    Point(SENSOR_MEASUREMENT)
                    .tag("zone", zone)
                    .tag("type", "water_level")
                    .field("value", float(water))
                )

        elif sensor_type == "activity":
            activity = data.get("activity")
            if activity is not None:
                points.append(
                    Point(SENSOR_MEASUREMENT)
                    .tag("zone", zone)
                    .tag("type", "activity")
                    .field("value", float(activity))
                )

        else:
            print(f"[MONITOR] Unknown sensor type: {sensor_type}")
            return

        if points:
            write_api.write(bucket=INFLUX_BUCKET, record=points)
            print(f"[MONITOR] Wrote {len(points)} points for zone={zone}, type={sensor_type}")

    mqtt_client.on_message = on_message
    mqtt_client.loop_forever()
