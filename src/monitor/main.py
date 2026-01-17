import json
import logging
import os
import time
import paho.mqtt.client as mqtt
from datetime import datetime
from DbManager import DbManager

class Monitor:
    def __init__(self):
        self.db = DbManager()
        self.logger = logging.getLogger("Monitor")
        
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.broker_host = os.getenv("MQTT_BROKER_HOST", "mosquitto")
        self.broker_port = int(os.getenv("MQTT_BROKER_PORT", 1883))

    def run(self):
        self.logger.info(f"Connecting to MQTT Broker at {self.broker_host}...")
        while True:
            try:
                self.client.connect(self.broker_host, self.broker_port, 60)
                self.client.loop_forever()
            except Exception as e:
                self.logger.error(f"Connection failed: {e}. Retrying in 5s...")
                time.sleep(5)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("Connected! Subscribing to farm/sensor/#")
            client.subscribe("farm/sensor/#")
        else:
            self.logger.error(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            topic = msg.topic
            
            # Store using the new InfluxDB method
            self.db.store_data_from_topic(topic, payload)
            
            # Log the data
            try:
                data = json.loads(payload)
                sensor_type = topic.split("/")[-1]
                value = data.get("value")
                if value is not None:
                    self.logger.debug(f"Saved {sensor_type}: {value}")
            except:
                pass
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    Monitor().run()
