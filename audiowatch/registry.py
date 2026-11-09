"""
Tracks which devices are members of the PAES67 multicast group:
"""


from dataclasses import dataclass

from .capture import IgmpPacket
from .events import Event, EventType
from .igmp import Action, IgmpMessage, Membership

# Default seconds before a member times out (IGMP default)
DEFAULT_MEMBER_TIMEOUT = 260.0


# Represents a device on the network (may or may not be member)
@dataclass(slots=True)
class Device:
    key: str  # unique key (ip address or mac)
    ip: str
    mac: str
    first_seen: float
    last_seen: float
    vlan: int | None = None
    interface: str = ""
    label: str = ""  # user-assigned name (milestone 2)

# Represents a device in the multicast group
@dataclass(slots=True)
class Member:
    device: Device
    version: int  # igmp version
    joined_at: float
    last_seen: float
    reports: int = 1
    detail: str = ""
    sources: tuple[str, ...] = ()


# Membership table for the controller's multicast group
class Registry:
    def __init__(self, group: str, stream: str = "", member_timeout: float = DEFAULT_MEMBER_TIMEOUT) -> None:
        self.group = group
        self.stream = stream
        self.member_timeout = member_timeout
        self.devices: dict[str, Device] = {}    # key -> device
        self.members: dict[str, Member] = {}    # key -> member
        self.queriers: dict[str, int] = {}      # querier ip -> igmp version

    # Handle decoded IGMP message to update membership
    def handle(self, packet: IgmpPacket, message: IgmpMessage) -> list[Event]:
        events: list[Event] = []
        for m in message.memberships:
            if m.group == self.group:
                events.extend(self._apply_update(packet, m))
        return events

    # Keep track of who is querying (True if changed)
    def note_query(self, packet: IgmpPacket, version: int) -> bool:
        changed = self.queriers.get(packet.src_ip) != version
        self.queriers[packet.src_ip] = version
        return changed

    # Remove members who have timed out
    def expire(self, now: float) -> list[Event]:
        events: list[Event] = []
        for key, member in list(self.members.items()):
            if now - member.last_seen > self.member_timeout:
                del self.members[key]
                events.append(self._event(EventType.EXPIRED, now, member, False, note=f"timeout after {now - member.last_seen:.0f}s"))
        return events


    # Update the membership from one IGMP statetement
    def _apply_update(self, packet: IgmpPacket, m: Membership) -> list[Event]:
        now = packet.timestamp
        events: list[Event] = []
        key = packet.src_ip if packet.src_ip != "0.0.0.0" else packet.src_mac
        device, new_device = self._touch_device(key, packet, events)

        # IGMPv2/v1 report suppression (reports all members, so no need to check seperately)
        if m.action is Action.JOIN and m.version < 3:
            for other in self.members.values():
                if other.version < 3:
                    other.last_seen = now

        # Actually apply the update (JOIN, LEAVE, REFRESH)
        member = self.members.get(key)
        if m.action is Action.JOIN:
            if member is None:
                member = Member(device, m.version, now, now, 1, m.detail, m.sources)
                self.members[key] = member
                events.append(self._event(EventType.JOIN, now, member, new_device))
            else:
                member.last_seen = now
                member.reports += 1
                member.version, member.detail, member.sources = m.version, m.detail, m.sources
        
        elif m.action is Action.LEAVE:
            if member is not None:
                del self.members[key]
                member.detail = m.detail
                events.append(self._event(EventType.LEAVE, now, member, False))
        
        elif member is not None:  # REFRESH
            member.last_seen = now
            member.reports += 1
        return events

    # Manages device objects to keep them up-to-date
    def _manage_device(self, key: str, packet: IgmpPacket, events: list[Event]) -> tuple[Device, bool]:
        device = self.devices.get(key)
        if device is None:
            device = Device(key, packet.src_ip, packet.src_mac, packet.timestamp, packet.timestamp, packet.vlan, packet.interface)
            self.devices[key] = device
            return device, True
        if device.mac != packet.src_mac and packet.src_ip != "0.0.0.0":
            previous, device.mac = device.mac, packet.src_mac
            ghost = Member(device, 0, packet.timestamp, packet.timestamp, 0, "mac change")
            events.append(self._event(EventType.MAC_CHANGED, packet.timestamp, ghost, False, note=f"mac changed from {previous}"))
        device.last_seen = packet.timestamp
        device.vlan = packet.vlan
        device.interface = packet.interface
        return device, False

    # Creates event object from current membership and device info
    def _event(self, evtype: EventType, now: float, member: Member, new: bool, note: str = "") -> Event:
        d = member.device
        return Event(
            evtype, time=now, group=self.group, stream=self.stream,
            ip=d.ip, mac=d.mac, vlan=d.vlan, interface=d.interface,
            igmp=member.detail, new_device=new, first_seen=d.first_seen,
            joined_at=member.joined_at, reports=member.reports,
            members=len(self.members), note=note,
        )
