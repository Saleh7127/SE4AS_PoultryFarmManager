import logging
import time
import json
import os
import paho.mqtt.client as mqtt
from PoultryBarn import PoultryBarn

class Simulator:
    def __init__(self):
        self.logger = logging.getLogger("Simulator")
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.broker_host = os.getenv("MQTT_BROKER_HOST", "mosquitto")
        self.broker_port = int(os.getenv("MQTT_BROKER_PORT", 1883))
        
        # Initialize PoultryBarn singleton (manages all sensors and actuators)
        self.barn = PoultryBarn()
        
        self.logger.info("Simulator initialized with modular architecture")

    def run(self):
        self.logger.info(f"Connecting to MQTT {self.broker_host}...")
        while True:
            try:
                self.client.connect(self.broker_host, self.broker_port, 60)
                self.client.loop_start()
                break
            except Exception:
                time.sleep(5)

        self.logger.info("Physics Loop Started")
        while True:
            # Update physics based on actuator states
            self.barn.update_physics()
            
            # Simulate and publish all sensor readings
            self.barn.simulate_all_sensors(self.client)
            
            time.sleep(5)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe("farm/actuator/#")
            self.logger.info("Connected. Listening to Actuators.")
        else:
            self.logger.error(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            action = payload.get("action")
            component = payload.get("component")
            
            # Extract component from topic if not in payload
            if not component:
                parts = topic.split("/")
                if len(parts) >= 3:
                    component = parts[2]  # farm/actuator/{component}
            
            self.logger.info(f"Received actuator command: {component} -> {action}")
            
            # Update actuator states using modular architecture
            if component == "fan":
                self.barn.get_fan().set_state(action == "ON")
                
            elif component == "heater":
                self.barn.get_heater().set_state(action == "ON")
                
            elif component == "feeder":
                if action == "DISPENSE":
                    amount = payload.get("amount", 10.0)
                    self.barn.get_feeder().set_state(True, amount=amount)
                else:
                    self.barn.get_feeder().set_state(False)
                    
            elif component == "water_valve":
                self.barn.get_water_valve().set_state(action == "OPEN")
            
            self.logger.info(f"Actuator Updated: {component} -> {action}")
            
        except Exception as e:
            self.logger.error(f"Error processing actuator command: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    Simulator().run()
