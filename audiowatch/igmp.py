"""
IGMP parsing (required) and building (for testing)
"""

from dataclasses import dataclass, field
from ipaddress import IPv4Address
from enum import IntEnum
import struct

# Protocol value
IGMP_PROTOCOL = 2

# Message types
TYPE_QUERY = 0x11
TYPE_V1_REPORT = 0x12
TYPE_V2_REPORT = 0x16
TYPE_V2_LEAVE = 0x17
TYPE_V3_REPORT = 0x22

ALL_ROUTERS = "224.0.0.2"       # IGMPv2 leaves go here
V3_REPORT_GROUP = "224.0.0.22"  # IGMPv3 reports go here


# IGMPv3 record types
class RecordType(IntEnum):
    MODE_IS_INCLUDE = 1
    MODE_IS_EXCLUDE = 2
    CHANGE_TO_INCLUDE = 3
    CHANGE_TO_EXCLUDE = 4
    ALLOW_NEW_SOURCES = 5
    BLOCK_OLD_SOURCES = 6

# Membership actions for the monitor
class Action(IntEnum):
    JOIN = 1  # Host is a member
    LEAVE = 2  # Host is no longer a member
    REFRESH = 3  # No change in membership state

# Normalized membership statement, extracted from IGMP message
@dataclass(slots=True)
class Membership:
    group: str
    action: Action
    version: int
    sources: tuple[str, ...] = ()  # IGMPv3 source list
    detail: str = ""

# IGMP membership query (sent by multicast routers)
@dataclass(slots=True)
class Query:
    group: str  # 0.0.0.0 = general query
    version: int
    max_resp_s: float

    @property
    def general(self) -> bool:
        return self.group == "0.0.0.0"

# General IGMP message
@dataclass(slots=True)
class IgmpMessage:
    memberships: list[Membership] = field(default_factory=list)
    query: Query | None = None


# Checksum for IGMP
def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


# Parses and interprets an IGMP message
def parse_igmp(data: bytes) -> IgmpMessage | None:

    # Validates the message
    if len(data) < 8 or checksum(data) != 0:
        return None
    kind, max_resp = data[0], data[1]

    # If the message is a membership query...
    if kind == TYPE_QUERY:
        group = str(IPv4Address(data[4:8]))
        if len(data) >= 12:
            code = max_resp
            if code >= 128:
                code = ((code & 0x0F) | 0x10) << (((code >> 4) & 0x07) + 3)
            return IgmpMessage(query=Query(group, 3, code / 10))
        version = 2 if max_resp else 1
        return IgmpMessage(query=Query(group, version, max_resp / 10))

    # If the message is a v1/v2 membership report...
    if kind in (TYPE_V1_REPORT, TYPE_V2_REPORT):
        version = 1 if kind == TYPE_V1_REPORT else 2
        group = str(IPv4Address(data[4:8]))
        return IgmpMessage([Membership(group, Action.JOIN, version, detail=f"v{version} report")])

    # If the message is a v3 membership report...
    if kind == TYPE_V3_REPORT:
        return parse_v3_report(data)

    # If the message is a v2 leave...
    if kind == TYPE_V2_LEAVE:
        group = str(IPv4Address(data[4:8]))
        return IgmpMessage([Membership(group, Action.LEAVE, 2, detail="v2 leave")])
    return None


# Parses IGMPv3 membership reports
# More complicated due to containing multiple group records
def parse_v3_report(data: bytes) -> IgmpMessage | None:
    (count,) = struct.unpack("!H", data[6:8])
    offset = 8
    out: list[Membership] = []
    for _ in range(count):
        if len(data) < offset + 8:
            return None
        rtype, aux_words, n_src = struct.unpack("!BBH", data[offset:offset + 4])
        group = str(IPv4Address(data[offset + 4:offset + 8]))
        end = offset + 8 + 4 * n_src + 4 * aux_words
        if len(data) < end:
            return None
        sources = tuple(str(IPv4Address(data[offset + 8 + 4 * i:offset + 12 + 4 * i])) for i in range(n_src))
        offset = end

        try:
            name = RecordType(rtype).name
        except ValueError:
            continue
        if rtype in (RecordType.MODE_IS_INCLUDE, RecordType.CHANGE_TO_INCLUDE):
            # INCLUDE with an empty list = not a member
            action = Action.JOIN if sources else Action.LEAVE
        elif rtype in (RecordType.MODE_IS_EXCLUDE, RecordType.CHANGE_TO_EXCLUDE, RecordType.ALLOW_NEW_SOURCES):
            action = Action.JOIN
        else:
            action = Action.REFRESH
        out.append(Membership(group, action, 3, sources, f"v3 {name}"))
    return IgmpMessage(out)

# |-----------------------------------------------------------|
# |                       IGMP BUILDERS                       |
# |-----------------------------------------------------------|

# Adds checksum to the IGMP data
def add_checksum(data: bytes) -> bytes:
    return data[:2] + struct.pack("!H", checksum(data)) + data[4:]

def build_v2_report(group: str) -> bytes:
    return add_checksum(struct.pack("!BBH4s", TYPE_V2_REPORT, 0, 0, IPv4Address(group).packed))

def build_v2_leave(group: str) -> bytes:
    return add_checksum(struct.pack("!BBH4s", TYPE_V2_LEAVE, 0, 0, IPv4Address(group).packed))

def build_v2_query(group: str = "0.0.0.0", max_resp_tenths: int = 100) -> bytes:
    return add_checksum(struct.pack("!BBH4s", TYPE_QUERY, max_resp_tenths, 0, IPv4Address(group).packed))

def build_v3_report(records: list[tuple[int, str, list[str]]]) -> bytes:
    body = b"".join(
        struct.pack("!BBH4s", rtype, 0, len(srcs), IPv4Address(group).packed)
        + b"".join(IPv4Address(s).packed for s in srcs)
        for rtype, group, srcs in records
    )
    return add_checksum(struct.pack("!BBHHH", TYPE_V3_REPORT, 0, 0, 0, len(records)) + body)
