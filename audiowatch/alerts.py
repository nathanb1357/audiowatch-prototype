"""
Event subscribers used to print out alerts (console + log file)
"""

import os
import sys
import json
from datetime import datetime
from typing import TextIO

from .events import Event, EventType

# Turn timestamp into readable string
def _timestr(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")


# Format event into a human-readable log message
def format_event(event: Event) -> str:
    stream =         f" '{event.stream}'" if event.stream else ""  # stream name
    head =           f"[{_timestr(event.time)}] ALERT {event.evtype.value:<11} {event.group}{stream}"
    iface =          f" via {event.interface}" if event.interface else ""
    vlan =           f" vlan {event.vlan}" if event.vlan else ""
    device_info =    f"    device  : {event.ip}   mac {event.mac}{vlan}" + ("  (NEW!)" if event.new_device else "")

    # Assemble lines
    lines = [head, device_info]
    if event.evtype is EventType.MAC_CHANGED:
        lines.append(f"    note    : {event.note} (possible mac spoofing)")
        return "\n".join(lines)
    
    elif event.evtype is EventType.JOIN:
        lines.append(f"    igmp    : {event.igmp}{iface}")
        lines.append(f"    group   : {event.members} member(s)")

    else:
        lines.append(f"    igmp    : {event.igmp}{iface}")
        lines.append(f"    session : member for {event.time - event.joined_at}s, {event.reports} report(s)")
        lines.append(f"    group   : {event.members} member(s) remain")
    
    if event.note:
        lines.append(f"    note    : {event.note}")
    return "\n".join(lines)


# Subscriber that logs to the console on event
class ConsoleLogger:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.out = stream or sys.stdout
        self.color = self.out.isatty() and "NO_COLOR" not in os.environ

    def __call__(self, event: Event) -> None:
        print(format_event(event), file=self.out, flush=True)


# Subscriber that logs to a JSON file on event
class JsonLogger:
    def __init__(self, path: str) -> None:
        self.file = open(path, "a", encoding="utf-8")

    def __call__(self, event: Event) -> None:
        self.file.write(json.dumps(event.to_dict()) + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()
