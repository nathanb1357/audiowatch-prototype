"""
Main monitor class for AudioWatch (currently passive):
    - Initialize monitor
    - Notify event subscribers
    - Process packets until interrupt or pcap end
    - Run summary
"""

from typing import Iterable, Callable
from time import time

from .capture import PacketSource, examine_frame
from .events import Event, EventSub
from .igmp import parse_igmp
from .registry import Registry

class Monitor:
    def __init__(self, source: PacketSource, registry: Registry, subs: Iterable[EventSub],
                 verbose: bool = False, log: Callable[[str], None] = print):
        self.source = source
        self.registry = registry
        self.subs = list(subs)
        self.verbose = verbose
        self.log = log
        self.packets = 0

    # Notify subscribers for new events
    def notify(self, events: list[Event]) -> None:
        for e in events:
            for sub in self.subs:
                sub(e)  # notify

    # Process packets until the source ends or the caller interrupts
    def run(self) -> None:
        for item in self.source.frames():
            # Time out silent members
            if item is None:
                self.notify(self.registry.expire(time()))
                continue

            # Parse frame (IGMP or None)
            timestamp, frame, interface = item
            packet = examine_frame(timestamp, frame, interface)
            if packet is None:
                continue

            # Parse IGMP message
            message = parse_igmp(packet.payload)
            if message is None:
                if self.verbose:
                    self.log(f"[verbose] ignored malformed IGMP from {packet.src_ip}")
                continue
            self.packets += 1
            self.notify(self.registry.expire(timestamp))

            if message.query is not None:
                q = message.query
                if self.registry.note_query(packet, q.version):
                    self.log(f"IGMP querier               : {packet.src_ip} (IGMPv{q.version})")
                if self.verbose:
                    kind = "general" if q.general else q.group
                    self.log(f"[verbose] query from {packet.src_ip}: {kind}, max response {q.max_resp_s:g}s")
                continue

            if self.verbose:
                for m in message.memberships:
                    seen = "watched" if m.group == self.registry.group else "ignored"
                    self.log(f"[verbose] {m.detail} {m.group} from {packet.src_ip} ({packet.src_mac}) [{seen}]")
            self.notify(self.registry.handle(packet, message))
    
    # Print summary of monitor activity
    def summary(self) -> str:
        r = self.registry        
        lines = [f"\nIGMP packets processed     : {self.packets}"]
        if not r.members:
            lines.append(f"No devices are currently members of {r.group}.")
        else:
            lines.append(f"Members of {r.group}{f' ({r.stream})' if r.stream else ''}:")
            for m in r.members.values():
                lines.append(f"    {m.device.ip:<15} {m.device.mac}  igmp v{m.version}  {m.reports} report(s)")
        return "\n".join(lines)
