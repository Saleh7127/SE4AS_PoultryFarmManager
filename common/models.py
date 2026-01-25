from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class ZoneStatus:
    zone: str
    temperature_c: Optional[float]
    nh3_ppm: Optional[float]
    feed_kg: Optional[float]
    water_l: Optional[float]
    activity: Optional[float]

    temp_ok: bool
    nh3_ok: bool
    feed_ok: bool
    water_ok: bool
    activity_ok: bool
    alert: str

@dataclass
class Action:
    actuator: str                  # 'fan', 'heater', etc.
    priority: int                  # lower = higher priority
    command: Dict[str, Any]        # JSON-serializable payload

@dataclass
class Plan:
    zone: str
    actions: List[Action]
