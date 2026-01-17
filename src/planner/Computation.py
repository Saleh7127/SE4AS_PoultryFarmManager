import os
import time
import requests
import logging
from collections import deque
from datetime import datetime

class Computation:
    """
    Advanced computation class for planning with state management,
    priority queues, starvation detection, and conflict resolution.
    Uses singleton pattern to maintain state across planning cycles.
    """
    _instance = None
    _logger = None
    
    # State tracking
    _issue_history: dict  # Track when issues were first detected
    _last_action_time: dict  # Track when actuators were last activated
    _issue_priority: dict  # Priority levels for issues
    _starvation_queue: deque  # Queue of issues that haven't been addressed
    _active_issues: dict  # Currently active issues with their values
    _actuator_states: dict  # Current state of actuators
    
    # Configuration
    _config_service_url: str
    _actuator_config: dict
    _thresholds: dict
    _starvation_threshold: int  # Time in seconds before an issue is considered starved
    
    # Issue priorities (higher = more critical)
    ISSUE_PRIORITIES = {
        "TEMP_HIGH": 10,
        "TEMP_LOW": 10,
        "AIR_QUALITY_BAD": 9,
        "WATER_LOW": 8,
        "FEED_LOW": 7
    }
    
    # Conflicting actuators (can't run simultaneously)
    CONFLICTS = {
        "heater": ["fan"],
        "fan": ["heater"]
    }

    def __new__(cls):
        if not hasattr(cls, '_instance') or cls._instance is None:
            cls._instance = super(Computation, cls).__new__(cls)
            cls._instance._logger = logging.getLogger("Computation")
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        """Initialize state variables"""
        self._config_service_url = os.getenv("CONFIG_SERVICE_URL", "http://configuration:5000")
        self._issue_history = {}
        self._last_action_time = {}
        self._issue_priority = {}
        self._starvation_queue = deque()
        self._active_issues = {}
        self._actuator_states = {
            "fan": False,
            "heater": False,
            "feeder": False,
            "water_valve": False
        }
        self._actuator_config = {}
        self._thresholds = {}
        self._starvation_threshold = 300  # 5 minutes default
        
        # Load configuration
        self._load_configuration()

    def _load_configuration(self):
        """Load configuration from configuration service"""
        try:
            # Load actuator config
            resp = requests.get(f"{self._config_service_url}/config/actuators", timeout=5)
            if resp.status_code == 200:
                self._actuator_config = resp.json()
                self._logger.info(f"Loaded actuator config: {self._actuator_config}")
            
            # Load thresholds for severity calculation
            resp = requests.get(f"{self._config_service_url}/config/thresholds", timeout=5)
            if resp.status_code == 200:
                self._thresholds = resp.json()
                self._logger.info(f"Loaded thresholds: {self._thresholds}")
        except Exception as e:
            self._logger.error(f"Error loading configuration: {e}")

    def register_issue(self, issue: str, value: float, timestamp: datetime = None):
        """
        Register a detected issue and track its history
        
        Args:
            issue: Issue type (e.g., "TEMP_HIGH")
            value: Current sensor value
            timestamp: When the issue was detected (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Track when issue was first detected
        if issue not in self._issue_history:
            self._issue_history[issue] = timestamp
            self._logger.info(f"New issue detected: {issue} (value: {value})")
        
        # Update active issues
        self._active_issues[issue] = {
            "value": value,
            "first_detected": self._issue_history[issue],
            "last_updated": timestamp
        }
        
        # Calculate priority with starvation
        priority = self._calculate_priority(issue, value)
        self._issue_priority[issue] = priority
        
        # Check for starvation
        self._check_starvation(issue)

    def _calculate_priority(self, issue: str, value: float) -> int:
        """
        Calculate priority for an issue based on base priority and severity
        
        Args:
            issue: Issue type
            value: Current sensor value
            
        Returns:
            Priority score (higher = more urgent)
        """
        base_priority = self.ISSUE_PRIORITIES.get(issue, 5)
        
        # Calculate severity multiplier based on how far from threshold
        severity_multiplier = 1.0
        
        if issue == "TEMP_HIGH":
            max_temp = self._thresholds.get("temperature", {}).get("max", 28.0)
            if value > max_temp:
                # How much above threshold (e.g., 30°C vs 28°C = 1.071x)
                severity_multiplier = 1.0 + ((value - max_temp) / max_temp) * 0.5
                
        elif issue == "TEMP_LOW":
            min_temp = self._thresholds.get("temperature", {}).get("min", 20.0)
            if value < min_temp:
                # How much below threshold
                severity_multiplier = 1.0 + ((min_temp - value) / min_temp) * 0.5
                
        elif issue == "AIR_QUALITY_BAD":
            max_ammonia = self._thresholds.get("ammonia", {}).get("max", 25.0)
            if value > max_ammonia:
                severity_multiplier = 1.0 + ((value - max_ammonia) / max_ammonia) * 0.5
                
        elif issue in ["FEED_LOW", "WATER_LOW"]:
            min_level = self._thresholds.get(issue.lower().replace("_low", "_level"), {}).get("min", 20.0)
            if value < min_level:
                # Lower level = higher priority
                severity_multiplier = 1.0 + ((min_level - value) / min_level) * 0.3
        
        # Apply starvation penalty
        if issue in self._issue_history:
            time_since_first = (datetime.now() - self._issue_history[issue]).total_seconds()
            if time_since_first > self._starvation_threshold:
                # Starvation penalty increases priority
                starvation_factor = min(1.5, 1.0 + (time_since_first - self._starvation_threshold) / 600)  # Max 1.5x
                severity_multiplier *= starvation_factor
        
        return int(base_priority * severity_multiplier)

    def _check_starvation(self, issue: str):
        """
        Check if an issue is starved (not addressed for too long)
        and add to starvation queue if needed
        """
        if issue not in self._issue_history:
            return
        
        time_since_first = (datetime.now() - self._issue_history[issue]).total_seconds()
        
        if time_since_first >= self._starvation_threshold:
            if issue not in self._starvation_queue:
                self._starvation_queue.append(issue)
                self._logger.warning(f"Issue {issue} is starved (unaddressed for {time_since_first:.0f}s)")

    def is_starvation_queue_empty(self) -> bool:
        """Check if starvation queue is empty"""
        return len(self._starvation_queue) == 0

    def get_starvation_issue(self) -> tuple:
        """
        Get the highest priority issue from starvation queue
        
        Returns:
            Tuple of (issue, priority) or (None, 0) if empty
        """
        if self.is_starvation_queue_empty():
            return None, 0
        
        # Sort starvation queue by priority
        sorted_starvation = sorted(
            self._starvation_queue,
            key=lambda x: self._issue_priority.get(x, 0),
            reverse=True
        )
        
        issue = sorted_starvation[0]
        priority = self._issue_priority.get(issue, 0)
        return issue, priority

    def clear_issue(self, issue: str):
        """
        Clear an issue after it has been addressed
        
        Args:
            issue: Issue type to clear
        """
        if issue in self._issue_history:
            del self._issue_history[issue]
        if issue in self._active_issues:
            del self._active_issues[issue]
        if issue in self._issue_priority:
            del self._issue_priority[issue]
        if issue in self._starvation_queue:
            self._starvation_queue.remove(issue)
        self._logger.info(f"Issue {issue} cleared")

    def get_highest_priority_issue(self) -> tuple:
        """
        Get the highest priority issue (either from starvation queue or active issues)
        
        Returns:
            Tuple of (issue, priority, value) or (None, 0, 0)
        """
        # First check starvation queue
        starved_issue, starved_priority = self.get_starvation_issue()
        
        # Find highest priority active issue
        if self._issue_priority:
            max_priority = max(self._issue_priority.values())
            max_issue = max(self._issue_priority.items(), key=lambda x: x[1])[0]
            
            # Prefer starved issue if priority is similar (within 20%)
            if starved_issue and starved_priority >= max_priority * 0.8:
                value = self._active_issues.get(starved_issue, {}).get("value", 0)
                return starved_issue, starved_priority, value
            elif max_issue:
                value = self._active_issues.get(max_issue, {}).get("value", 0)
                return max_issue, max_priority, value
        
        if starved_issue:
            value = self._active_issues.get(starved_issue, {}).get("value", 0)
            return starved_issue, starved_priority, value
        
        return None, 0, 0

    def calculate_duration(self, issue: str, value: float, base_duration: int) -> int:
        """
        Calculate adaptive duration based on severity
        
        Args:
            issue: Issue type
            value: Current sensor value
            base_duration: Base duration from config
            
        Returns:
            Adaptive duration in seconds
        """
        multiplier = 1.0
        
        if issue == "TEMP_HIGH":
            max_temp = self._thresholds.get("temperature", {}).get("max", 28.0)
            if value > max_temp:
                # More severe = longer duration (max 2x)
                multiplier = min(2.0, 1.0 + ((value - max_temp) / max_temp))
                
        elif issue == "TEMP_LOW":
            min_temp = self._thresholds.get("temperature", {}).get("min", 20.0)
            if value < min_temp:
                multiplier = min(2.0, 1.0 + ((min_temp - value) / min_temp))
                
        elif issue == "AIR_QUALITY_BAD":
            max_ammonia = self._thresholds.get("ammonia", {}).get("max", 25.0)
            if value > max_ammonia:
                multiplier = min(2.5, 1.0 + ((value - max_ammonia) / max_ammonia) * 1.5)
                
        elif issue == "WATER_LOW":
            min_level = self._thresholds.get("water_level", {}).get("min", 20.0)
            if value < min_level:
                # Lower level = more water needed
                multiplier = min(3.0, 1.0 + ((min_level - value) / min_level) * 2.0)
        
        return int(base_duration * multiplier)

    def resolve_conflicts(self, actions: list) -> list:
        """
        Resolve conflicts between actions (e.g., heater vs fan)
        
        Args:
            actions: List of action dictionaries
            
        Returns:
            Filtered list of actions with conflicts resolved
        """
        resolved_actions = []
        action_components = set()
        
        for action in actions:
            component = action.get("component")
            
            # Check if component conflicts with already planned actions
            conflicts = self.CONFLICTS.get(component, [])
            
            for conflict_comp in conflicts:
                if conflict_comp in action_components:
                    self._logger.warning(
                        f"Conflict detected: {component} conflicts with {conflict_comp}. "
                        f"Keeping {component} due to higher priority."
                    )
                    # Remove conflicting action
                    resolved_actions = [a for a in resolved_actions if a.get("component") != conflict_comp]
                    action_components.discard(conflict_comp)
            
            # Add action if no conflict
            resolved_actions.append(action)
            action_components.add(component)
        
        return resolved_actions

    def get_actuator_state(self, actuator: str) -> bool:
        """Get current state of an actuator"""
        return self._actuator_states.get(actuator, False)

    def set_actuator_state(self, actuator: str, state: bool):
        """Update actuator state"""
        self._actuator_states[actuator] = state
        self._last_action_time[actuator] = time.time()

    def should_execute_action(self, actuator: str, min_interval: int = 30) -> bool:
        """
        Check if an action should be executed (prevent rapid toggling)
        
        Args:
            actuator: Actuator name
            min_interval: Minimum seconds between actions for same actuator
            
        Returns:
            True if action should be executed
        """
        if actuator not in self._last_action_time:
            return True
        
        time_since_last = time.time() - self._last_action_time[actuator]
        return time_since_last >= min_interval

    def plan_actions(self, issue: str, value: float) -> list:
        """
        Generate plan of actions for an issue with conflict resolution
        
        Args:
            issue: Issue type
            value: Current sensor value
            
        Returns:
            List of action dictionaries
        """
        actions = []
        
        if issue == "TEMP_HIGH":
            base_dur = self._actuator_config.get("fan", {}).get("duration", 60)
            dur = self.calculate_duration(issue, value, base_dur)
            
            if self.should_execute_action("fan"):
                actions.append({"component": "fan", "action": "ON", "duration": dur})
                self.set_actuator_state("fan", True)
            if self.should_execute_action("heater"):
                actions.append({"component": "heater", "action": "OFF", "duration": 0})
                self.set_actuator_state("heater", False)
            
        elif issue == "TEMP_LOW":
            base_dur = self._actuator_config.get("heater", {}).get("duration", 60)
            dur = self.calculate_duration(issue, value, base_dur)
            
            if self.should_execute_action("heater"):
                actions.append({"component": "heater", "action": "ON", "duration": dur})
                self.set_actuator_state("heater", True)
            if self.should_execute_action("fan"):
                actions.append({"component": "fan", "action": "OFF", "duration": 0})
                self.set_actuator_state("fan", False)

        elif issue == "AIR_QUALITY_BAD":
            base_dur = self._actuator_config.get("fan", {}).get("duration", 120)
            dur = self.calculate_duration(issue, value, base_dur)
            
            if self.should_execute_action("fan"):
                actions.append({"component": "fan", "action": "ON", "duration": dur})
                self.set_actuator_state("fan", True)

        elif issue == "FEED_LOW":
            base_amt = self._actuator_config.get("feeder", {}).get("amount", 10)
            # Increase amount based on how low the feed is
            min_level = self._thresholds.get("feed_level", {}).get("min", 20.0)
            multiplier = max(1.0, (min_level - value) / min_level * 2.0) if value < min_level else 1.0
            amt = int(base_amt * multiplier)
            
            if self.should_execute_action("feeder"):
                actions.append({"component": "feeder", "action": "DISPENSE", "amount": amt})
                self.set_actuator_state("feeder", True)

        elif issue == "WATER_LOW":
            base_dur = self._actuator_config.get("water_valve", {}).get("duration", 10)
            dur = self.calculate_duration(issue, value, base_dur)
            
            if self.should_execute_action("water_valve"):
                actions.append({"component": "water_valve", "action": "OPEN", "duration": dur})
                self.set_actuator_state("water_valve", True)
        
        # Resolve conflicts
        actions = self.resolve_conflicts(actions)
        
        return actions

    def get_multi_parameter_plan(self) -> list:
        """
        Generate plan considering multiple simultaneous issues
        
        Returns:
            List of action dictionaries addressing all high-priority issues
        """
        all_actions = []
        processed_issues = set()
        
        # Process up to 3 highest priority issues
        for _ in range(3):
            issue, priority, value = self.get_highest_priority_issue()
            
            if issue is None or issue in processed_issues:
                break
            
            actions = self.plan_actions(issue, value)
            all_actions.extend(actions)
            processed_issues.add(issue)
            
            # Clear this issue from starvation queue if it was starved
            if issue in self._starvation_queue:
                self._starvation_queue.remove(issue)
        
        # Resolve all conflicts
        all_actions = self.resolve_conflicts(all_actions)
        
        return all_actions

