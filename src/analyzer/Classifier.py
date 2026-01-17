import os
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import StandardScaler
import logging

class Classifier:
    """
    Simple ML classifier for farm health classification using sensor data.
    Uses Decision Tree algorithm for interpretable classification.
    Classifies farm state based on temperature, ammonia, feed_level, and water_level.
    """
    _instance = None
    _logger = None
    _classifier = None
    _scaler = None
    _trained = False

    # Farm health states
    STATES = {
        0: "GOOD",
        1: "WARNING",
        2: "CRITICAL"
    }

    def __new__(cls):
        if not hasattr(cls, '_instance') or cls._instance is None:
            cls._instance = super(Classifier, cls).__new__(cls)
            cls._instance._logger = logging.getLogger("Classifier")
            cls._instance._init_classifier()
        return cls._instance

    def _init_classifier(self):
        """Initialize and train the classifier with knowledge-based rules"""
        # Create a simple Decision Tree classifier
        self._classifier = DecisionTreeClassifier(
            max_depth=5,
            min_samples_split=10,
            random_state=42
        )
        self._scaler = StandardScaler()
        
        # Train with knowledge-based synthetic data
        self._train_with_knowledge()
        self._trained = True
        self._logger.info("Classifier initialized and trained with sensor knowledge")

    def _train_with_knowledge(self):
        """
        Train classifier with knowledge-based rules from existing sensor thresholds.
        Creates synthetic training data based on poultry farm domain knowledge.
        """
        # Get thresholds from config (will use defaults if not available)
        config_url = os.getenv("CONFIG_SERVICE_URL", "http://configuration:5000")
        thresholds = self._load_thresholds(config_url)
        
        temp_min = thresholds.get("temperature", {}).get("min", 20.0)
        temp_max = thresholds.get("temperature", {}).get("max", 28.0)
        ammonia_max = thresholds.get("ammonia", {}).get("max", 25.0)
        feed_min = thresholds.get("feed_level", {}).get("min", 20.0)
        water_min = thresholds.get("water_level", {}).get("min", 20.0)
        
        # Generate synthetic training data based on knowledge
        # Format: [temperature, ammonia, feed_level, water_level]
        X = []
        y = []
        
        # GOOD states (all sensors within normal ranges)
        for _ in range(100):
            X.append([
                np.random.uniform(temp_min, temp_max),  # Good temperature
                np.random.uniform(0, ammonia_max * 0.8),  # Good ammonia
                np.random.uniform(feed_min, 100),  # Good feed
                np.random.uniform(water_min, 100)  # Good water
            ])
            y.append(0)  # GOOD
        
        # WARNING states (one sensor approaching limits)
        for _ in range(80):
            # Temperature warning
            X.append([
                np.random.uniform(temp_max * 0.9, temp_max * 1.05),  # Near max
                np.random.uniform(0, ammonia_max * 0.7),
                np.random.uniform(feed_min, 100),
                np.random.uniform(water_min, 100)
            ])
            y.append(1)  # WARNING
            
            # Ammonia warning
            X.append([
                np.random.uniform(temp_min, temp_max),
                np.random.uniform(ammonia_max * 0.85, ammonia_max * 1.1),
                np.random.uniform(feed_min, 100),
                np.random.uniform(water_min, 100)
            ])
            y.append(1)  # WARNING
            
            # Feed warning
            X.append([
                np.random.uniform(temp_min, temp_max),
                np.random.uniform(0, ammonia_max * 0.8),
                np.random.uniform(feed_min * 0.8, feed_min * 1.1),
                np.random.uniform(water_min, 100)
            ])
            y.append(1)  # WARNING
            
            # Water warning
            X.append([
                np.random.uniform(temp_min, temp_max),
                np.random.uniform(0, ammonia_max * 0.8),
                np.random.uniform(feed_min, 100),
                np.random.uniform(water_min * 0.8, water_min * 1.1)
            ])
            y.append(1)  # WARNING
        
        # CRITICAL states (multiple sensors out of range or severe issues)
        for _ in range(60):
            # Temperature critical
            X.append([
                np.random.uniform(temp_max * 1.05, temp_max * 1.3),  # Too high
                np.random.uniform(0, ammonia_max * 0.9),
                np.random.uniform(feed_min * 0.5, feed_min),
                np.random.uniform(water_min, 100)
            ])
            y.append(2)  # CRITICAL
            
            # Ammonia critical
            X.append([
                np.random.uniform(temp_min, temp_max),
                np.random.uniform(ammonia_max * 1.1, ammonia_max * 1.5),  # Too high
                np.random.uniform(feed_min, 100),
                np.random.uniform(water_min * 0.5, water_min)
            ])
            y.append(2)  # CRITICAL
            
            # Multiple issues critical
            X.append([
                np.random.uniform(temp_max * 1.05, temp_max * 1.2),
                np.random.uniform(ammonia_max * 1.05, ammonia_max * 1.3),
                np.random.uniform(0, feed_min * 0.9),
                np.random.uniform(0, water_min * 0.9)
            ])
            y.append(2)  # CRITICAL
        
        # Convert to numpy arrays
        X = np.array(X)
        y = np.array(y)
        
        # Scale features
        X_scaled = self._scaler.fit_transform(X)
        
        # Train classifier
        self._classifier.fit(X_scaled, y)
        
        self._logger.info(
            f"Classifier trained with {len(X)} samples: "
            f"{np.sum(y==0)} GOOD, {np.sum(y==1)} WARNING, {np.sum(y==2)} CRITICAL"
        )

    def _load_thresholds(self, config_url: str) -> dict:
        """Load thresholds from configuration service"""
        try:
            import requests
            resp = requests.get(f"{config_url}/config/thresholds", timeout=3)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self._logger.warning(f"Could not load thresholds: {e}. Using defaults.")
        
        # Default thresholds
        return {
            "temperature": {"min": 20.0, "max": 28.0},
            "ammonia": {"max": 25.0},
            "feed_level": {"min": 20.0},
            "water_level": {"min": 20.0}
        }

    def classify_farm_health(self, temperature: float, ammonia: float, 
                            feed_level: float, water_level: float) -> dict:
        """
        Classify farm health status based on sensor readings
        
        Args:
            temperature: Temperature sensor reading
            ammonia: Ammonia sensor reading
            feed_level: Feed level sensor reading
            water_level: Water level sensor reading
            
        Returns:
            Dictionary with classification results:
            {
                "state": "GOOD" | "WARNING" | "CRITICAL",
                "confidence": float (0-1),
                "features": [temp, ammonia, feed, water]
            }
        """
        if not self._trained:
            self._logger.error("Classifier not trained yet")
            return {"state": "UNKNOWN", "confidence": 0.0}
        
        # Prepare feature vector
        features = np.array([[temperature, ammonia, feed_level, water_level]])
        
        # Scale features
        features_scaled = self._scaler.transform(features)
        
        # Predict
        prediction = self._classifier.predict(features_scaled)[0]
        probabilities = self._classifier.predict_proba(features_scaled)[0]
        
        # Get state and confidence
        state = self.STATES.get(prediction, "UNKNOWN")
        confidence = float(probabilities[prediction])
        
        result = {
            "state": state,
            "confidence": round(confidence, 3),
            "features": {
                "temperature": round(temperature, 2),
                "ammonia": round(ammonia, 2),
                "feed_level": round(feed_level, 2),
                "water_level": round(water_level, 2)
            },
            "probabilities": {
                "GOOD": round(probabilities[0], 3),
                "WARNING": round(probabilities[1], 3),
                "CRITICAL": round(probabilities[2], 3)
            }
        }
        
        return result

    def classify_sensor_readings(self, readings: dict) -> dict:
        """
        Classify farm health from sensor readings dictionary
        
        Args:
            readings: Dictionary with sensor readings
                {
                    "temperature": float,
                    "ammonia": float,
                    "feed_level": float,
                    "water_level": float
                }
                
        Returns:
            Classification result dictionary
        """
        temp = readings.get("temperature", 0.0)
        ammonia = readings.get("ammonia", 0.0)
        feed = readings.get("feed_level", 0.0)
        water = readings.get("water_level", 0.0)
        
        return self.classify_farm_health(temp, ammonia, feed, water)

