import logging
import time
import json
import os
import paho.mqtt.client as mqtt
from datetime import datetime
from DbManager import DbManager

class Executor:
    def __init__(self):
        self.logger = logging.getLogger("Executor")
        self.db = DbManager()
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.broker_host = os.getenv("MQTT_BROKER_HOST", "mosquitto")
        self.broker_port = int(os.getenv("MQTT_BROKER_PORT", 1883))

    def run(self):
        self.logger.info(f"Connecting to MQTT {self.broker_host}...")
        while True:
            try:
                self.client.connect(self.broker_host, self.broker_port, 60)
                self.client.loop_forever()
            except Exception:
                time.sleep(5)

    def on_connect(self, client, userdata, flags, rc):
        client.subscribe("farm/plan")
        self.logger.info("Subscribed to farm/plan")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.execute(payload)
        except Exception as e:
            self.logger.error(f"Execution Error: {e}")

    def execute(self, plan_payload):
        actions = plan_payload.get("actions", [])
        for action in actions:
            component = action.get("component")
            topic = f"farm/actuator/{component}"
            
            self.client.publish(topic, json.dumps(action))
            self.logger.info(f"Executed: {action} -> {topic}")
            
            log_entry = {
                "timestamp": datetime.now(),
                "actuator_type": component,
                "action": action.get("action"),
                "details": json.dumps(action)
            }
            self.db.add_actuator_log(log_entry)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    Executor().run()
