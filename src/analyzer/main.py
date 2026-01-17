import logging
import time
import json
import requests
import os
import paho.mqtt.client as mqtt
from datetime import datetime
from DbManager import DbManager
from Classifier import Classifier

CONFIG_SERVICE_URL = os.getenv("CONFIG_SERVICE_URL", "http://configuration:5000")

class Analyzer:
    def __init__(self):
        self.logger = logging.getLogger("Analyzer")
        self.db = DbManager()
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        
        self.broker_host = os.getenv("MQTT_BROKER_HOST", "mosquitto")
        self.broker_port = int(os.getenv("MQTT_BROKER_PORT", 1883))
        
        # Initialize ML classifier for advanced sensor processing
        self.classifier = Classifier()
        
        self.thresholds = {}
        self.update_config()
        self.logger.info("Analyzer initialized with ML classifier")

    def update_config(self):
        try:
            resp = requests.get(f"{CONFIG_SERVICE_URL}/config/thresholds")
            if resp.status_code == 200:
                self.thresholds = resp.json()
                self.logger.info(f"Loaded thresholds: {self.thresholds}")
            else:
                self.logger.warning("Failed to fetch config")
        except Exception as e:
            self.logger.error(f"Config Error: {e}")

    def run(self):
        self.logger.info(f"Connecting to MQTT {self.broker_host}...")
        while True:
            try:
                self.client.connect(self.broker_host, self.broker_port, 60)
                self.client.loop_start()
                break
            except Exception:
                time.sleep(5)
        
        # Analysis Loop
        while True:
            self.analyze()
            time.sleep(5)

    def on_connect(self, client, userdata, flags, rc):
        self.logger.info("Connected to MQTT")

    def analyze(self):
        try:
            # Fetch latest readings from InfluxDB
            sensor_types = ['temperature', 'ammonia', 'feed_level', 'water_level']
            readings = self.db.get_sensor_readings_by_type(sensor_types)
            
            # Prepare readings dictionary for ML classification
            readings_dict = {}
            for sensor_type, reading in readings.items():
                if reading:
                    readings_dict[sensor_type] = reading.value
                    # Check individual reading for issues
                    self._check_reading(reading)
            
            # Use ML classifier for overall farm health assessment
            if len(readings_dict) == 4:  # All sensors available
                self._classify_farm_health(readings_dict)
        except Exception as e:
            self.logger.error(f"Analysis Error: {e}")

    def _check_reading(self, reading):
        issue = None
        val = reading.value
        sensor_type = reading.sensor_type
        
        t_conf = self.thresholds.get("temperature", {})
        a_conf = self.thresholds.get("ammonia", {})
        f_conf = self.thresholds.get("feed_level", {})
        w_conf = self.thresholds.get("water_level", {})

        if sensor_type == 'temperature':
            if val < t_conf.get("min", 0): issue = "TEMP_LOW"
            elif val > t_conf.get("max", 100): issue = "TEMP_HIGH"
        elif sensor_type == 'ammonia':
            if val > a_conf.get("max", 100): issue = "AIR_QUALITY_BAD"
        elif sensor_type == 'feed_level':
            if val < f_conf.get("min", 0): issue = "FEED_LOW"
        elif sensor_type == 'water_level':
            if val < w_conf.get("min", 0): issue = "WATER_LOW"
            
        if issue:
            self.logger.info(f"Issue Detected: {issue}")
            payload = {
                "timestamp": str(datetime.now()),
                "issue": issue,
                "val": val
            }
            self.client.publish("farm/analysis", json.dumps(payload))

    def _classify_farm_health(self, readings_dict: dict):
        """
        Use ML classifier to assess overall farm health
        """
        try:
            # Classify farm health using ML
            classification = self.classifier.classify_sensor_readings(readings_dict)
            
            state = classification.get("state")
            confidence = classification.get("confidence")
            
            self.logger.info(
                f"Farm Health Classification: {state} "
                f"(confidence: {confidence:.2%})"
            )
            
            # If classified as CRITICAL or WARNING, publish classification result
            if state in ["CRITICAL", "WARNING"]:
                payload = {
                    "timestamp": str(datetime.now()),
                    "classification": state,
                    "confidence": confidence,
                    "probabilities": classification.get("probabilities", {}),
                    "features": classification.get("features", {})
                }
                
                # Publish classification to a separate topic for monitoring
                self.client.publish("farm/classification", json.dumps(payload))
                self.logger.info(f"Published classification: {state}")
                
        except Exception as e:
            self.logger.error(f"Classification Error: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    Analyzer().run()
