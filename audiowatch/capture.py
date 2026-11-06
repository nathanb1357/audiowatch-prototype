"""
Traffic capturing utilities for AudioWatch:
- IGMP data class
- Parse IGMP frames from Ethernet
- Defines a PacketSource interface for different packet sources
    - Linux raw sockets
    - PCAP files
- Method that opens the correct source
"""

import struct
import socket
import time
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Iterator, Protocol

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

# Interface for all packet capture sources to follow
class PacketSource(Protocol):
    def frames(self) -> Iterator[Frame | None]: ...
    def close(self) -> None: ...

# Formats a MAC Address into a string
def format_mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


# Examines a frame to see if it's IGMP: If so return it, if not return None
def examine_frame(timestamp: float, frame: bytes, interface: str = "") -> IgmpPacket | None:
    if len(frame) < 14:
        return None

    # Parse Ethernet header
    src_mac = format_mac(frame[6:12])
    ethertype = struct.unpack("!H", frame[12:14])[0]
    offset = 14
    vlan = None
    while ethertype in (ETH_VLAN_Q, ETH_VLAN_AD):
        if len(frame) < offset + 4:
            return None
        tci, ethertype = struct.unpack("!HH", frame[offset:offset + 4])
        vlan = tci & 0x0FFF
        offset += 4
    if ethertype != ETH_IP or len(frame) < offset + 20:
        return None

    # Parse IPv4 header
    ip = frame[offset:]
    if ip[0] >> 4 != 4:  # check version
        return None
    head_len = (ip[0] & 0x0F) * 4
    total_len = struct.unpack("!H", ip[2:4])[0]
    if ip[9] != IGMP_PROTOCOL or head_len < 20 or total_len < head_len or len(ip) < head_len or total_len <= len(ip):
        return None
    payload = ip[head_len:total_len]
    return IgmpPacket(
        timestamp=timestamp,
        interface=interface,
        src_mac=src_mac,
        src_ip=str(IPv4Address(ip[12:16])),
        dst_ip=str(IPv4Address(ip[16:20])),
        vlan=vlan,
        payload=payload,
    )


# |-----------------------------------------------------------|
# |                     LINUX RAW SOCKETS                     |
# |-----------------------------------------------------------|

# Live packet capture using Linux Raw Sockets
class RawSocketSource:
    def __init__(self, interface: str | None = None, idle_s: float = 0.5) -> None:
        if not hasattr(socket, "AF_PACKET"):
            raise OSError("AF_PACKET capture needs Linux; use --pcap instead")
        
        try:
            self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_ALL))
        except PermissionError as exc:
            raise PermissionError("raw capture needs root (try sudo) or CAP_NET_RAW") from exc
        
        if interface:
            self.sock.bind((interface, 0))
        self.sock.settimeout(idle_s)

    # Returns a stream of frames to yield from
    def frames(self) -> Iterator[Frame | None]:
        while True:
            try:
                data, addr = self.sock.recvfrom(65535)
            except TimeoutError:
                yield None
                continue
            ifname, pkttype = addr[0], addr[2]
            # Ignore outgoing loopback packets to avoid duplicates.
            if ifname == "lo" and pkttype == PACKET_OUTGOING:
                continue
            yield (time.time(), data, ifname)

    # Close the raw socket
    def close(self) -> None:
        self.sock.close()


# |-----------------------------------------------------------|
# |                         PCAP FILES                        |
# |-----------------------------------------------------------|

# Packet capture from a libpcap file
class PcapFileSource:
    def __init__(self, path: str) -> None:
        self._path = path

    # Returns a stream of frames to yield from
    def frames(self) -> Iterator[Frame | None]:
        with open(self._path, "rb") as f:
            magic = f.read(4)
            formats = {
                b"\xd4\xc3\xb2\xa1": ("<", 1e-6), b"\xa1\xb2\xc3\xd4": (">", 1e-6),
                b"\x4d\x3c\xb2\xa1": ("<", 1e-9), b"\xa1\xb2\x3c\x4d": (">", 1e-9),
            }
            if magic not in formats:
                raise ValueError(f"{self._path}: not a pcap file")
            endian, unit = formats[magic]
            header = f.read(20)
            if len(header) < 20 or struct.unpack(endian + "I", header[16:20])[0] != 1:
                raise ValueError(f"{self._path}: only Ethernet captures are supported")
            record = struct.Struct(endian + "IIII")
            while True:
                head = f.read(record.size)
                if len(head) < record.size:
                    return
                sec, frac, caplen, _ = record.unpack(head)

                data = f.read(caplen)
                if len(data) < caplen:
                    raise ValueError("Truncated PCAP packet")
                yield (sec + frac * unit, data, "pcap")
    
    # Close the packet source (does nothing here)
    def close(self) -> None:
        pass


# Return specific PacketSource from arguments
def open_source(interface: str | None, pcap: str | None) -> PacketSource:
    if pcap:
        return PcapFileSource(pcap)
    return RawSocketSource(interface)
