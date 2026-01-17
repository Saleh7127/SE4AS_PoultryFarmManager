import logging
import time
import json
import requests
import os
import paho.mqtt.client as mqtt
from datetime import datetime
from Computation import Computation

CONFIG_SERVICE_URL = os.getenv("CONFIG_SERVICE_URL", "http://configuration:5000")

class Planner:
    def __init__(self):
        self.logger = logging.getLogger("Planner")
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.broker_host = os.getenv("MQTT_BROKER_HOST", "mosquitto")
        self.broker_port = int(os.getenv("MQTT_BROKER_PORT", 1883))
        
        # Initialize Computation singleton for state management
        self.computation = Computation()
        
        self.logger.info("Planner initialized with advanced computation logic")

    def run(self):
        self.logger.info(f"Connecting to MQTT {self.broker_host}...")
        while True:
            try:
                self.client.connect(self.broker_host, self.broker_port, 60)
                self.client.loop_forever()
            except Exception:
                time.sleep(5)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe("farm/analysis")
            self.logger.info("Connected! Subscribed to farm/analysis")
        else:
            self.logger.error(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.plan(payload)
        except Exception as e:
            self.logger.error(f"Planning Error: {e}")

    def plan(self, analysis_payload):
        """
        Advanced planning with state management, priority queues, and conflict resolution
        """
        issue = analysis_payload.get("issue")
        value = analysis_payload.get("val", 0.0)
        timestamp_str = analysis_payload.get("timestamp")
        
        # Parse timestamp if provided
        timestamp = None
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now()
        
        # Register the issue with computation engine
        self.computation.register_issue(issue, value, timestamp)
        
        # Get the highest priority issue (may be different if starvation occurred)
        priority_issue, priority, priority_value = self.computation.get_highest_priority_issue()
        
        # Use priority issue if available, otherwise use current issue
        current_issue = priority_issue if priority_issue else issue
        current_value = priority_value if priority_issue else value
        
        self.logger.info(
            f"Planning for issue: {current_issue} "
            f"(priority: {priority}, value: {current_value:.2f})"
        )
        
        # Generate actions using advanced computation logic
        actions = self.computation.plan_actions(current_issue, current_value)
        
        # If we processed a different issue due to starvation, also check other high-priority issues
        if priority_issue != issue:
            # Generate multi-parameter plan to handle multiple issues
            all_actions = self.computation.get_multi_parameter_plan()
            if all_actions:
                actions = all_actions
        
        if actions:
            plan_payload = {
                "timestamp": str(datetime.now()),
                "related_issue": current_issue,
                "original_issue": issue,  # Keep track of original issue
                "priority": priority,
                "actions": actions
            }
            self.logger.info(f"Publishing Plan: {plan_payload}")
            self.client.publish("farm/plan", json.dumps(plan_payload))
            
            # Note: We don't clear issues immediately - they will be cleared
            # when the issue is actually resolved (values return to normal)
        else:
            self.logger.warning(f"No actions generated for issue: {current_issue}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    Planner().run()
