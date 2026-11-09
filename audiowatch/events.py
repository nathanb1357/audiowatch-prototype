"""
Events produced by the monitor (given to subscribers)
"""

from enum import Enum
from typing import Callable
from dataclasses import dataclass, asdict


# Defines the possible event types
class EventType(str, Enum):
    JOIN = "JOIN"
    LEAVE = "LEAVE"
    EXPIRED = "EXPIRED"
    MAC_CHANGED = "MAC_CHANGED"


@dataclass(slots=True)
class Event:
    evtype: EventType
    time: float
    group: str
    stream: str         # stream name
    ip: str
    mac: str
    vlan: int | None
    interface: str
    igmp: str           # version + record type
    new_device: bool
    first_seen: float   # time the device was first seen
    joined_at: float    # time this membership began
    reports: int        # IGMP reports seen for this membership
    members: int        # members remaining in the group after this event
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evtype"] = self.evtype.value
        return d

# Anything that gets passed in an event
EventSubscriber = Callable[[Event], None]
