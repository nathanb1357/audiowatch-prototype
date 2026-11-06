"""
Traffic capturing utilities for AudioWatch:
- IGMP data class
- Parse IGMP frames from Ethernet
- Defines a PacketSource interface for different packet sources
    - Linux raw sockets
    - PCAP files
- Method that opens the correct source
"""

from dataclasses import dataclass
from .igmp import IGMP_PROTOCOL


# Ethernet filters
ETH_ALL = 0x0003
ETH_IP = 0x0800
ETH_VLAN_Q = 0x8100
ETH_VLAN_AD = 0x88A8
PACKET_OUTGOING = 4  # Identify outgoing packets to avoid duplicates
SO_ATTACH_FILTER = 26  # Linux default value for BPF attachment

# Defines a captured frame (timestamp, raw bytes, network interface)
Frame = tuple[float, bytes, str]

# Data class to represent an IGMP packet 
@dataclass(slots=True)
class IgmpPacket:
    timestamp: float
    interface: str
    src_mac: str
    src_ip: str
    dst_ip: str
    vlan: int | None
    payload: bytes

# Formats a MAC Address into a string
def format_mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


# Examines a frame to see if it's IGMP: If so return it, if not return None
def examine_frame() -> IgmpPacket | None:
    pass


# Interface for all packet capture sources to follow
class PacketSource():
    pass


# |-----------------------------------------------------------|
# |                     LINUX RAW SOCKETS                     |
# |-----------------------------------------------------------|

# Classic BPF: accept only IPv4 frames whose protocol is IGMP (2).
_BPF_IGMP = [
    (0x28, 0, 0, 12),               # ldh ethertype
    (0x15, 0, 3, ETH_IP),           # jeq    0x800
    (0x30, 0, 0, 23),               # ldb IP protocol
    (0x15, 0, 1, IGMP_PROTOCOL),    # jeq    IGMP
    (0x06, 0, 0, 0x40000),          # accept
    (0x06, 0, 0, 0),                # drop
]



# |-----------------------------------------------------------|
# |                         PCAP FILES                        |
# |-----------------------------------------------------------|


