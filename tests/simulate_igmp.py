"""
Simulate IGMP membership traffic so the monitor can be tested on ONE machine.
"""

import socket
import struct
import sys
from pathlib import Path
from argparse import ArgumentParser
from ipaddress import IPv4Address

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import audiowatch.igmp as igmp


# Multicast hosts
HOSTS = "224.0.0.1"

# Converts multicast IPv4 address into corresponding MAC address
def multicast_mac(ip: str) -> bytes:
    low = IPv4Address(ip).packed
    return bytes([0x01, 0x00, 0x5E, low[1] & 0x7F, low[2], low[3]])

# Generates a locally-administered MAC address for simulation
def default_mac(ip: str) -> str:
    return "02:00:" + ":".join(f"{b:02x}" for b in IPv4Address(ip).packed)

# Build an ethernet frame to be sent
def build_frame(src_mac: str, src_ip: str, dst_ip: str, payload: bytes) -> bytes:
    options = b"\x94\x04\x00\x00"  # router alert
    total = 24 + len(payload)
    header = struct.pack("!BBHHHBBH4s4s", 0x46, 0xC0, total, 0, 0, 1, 2, 0, IPv4Address(src_ip).packed, IPv4Address(dst_ip).packed) + options
    header = header[:10] + struct.pack("!H", igmp.checksum(header)) + header[12:]
    eth = multicast_mac(dst_ip) + bytes.fromhex(src_mac.replace(":", "")) + b"\x08\x00"
    return eth + header + payload


def main() -> None:
    p = ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("action", choices=["join", "leave", "query"])
    p.add_argument("--group", default="239.69.11.44")
    p.add_argument("--src-ip", default="10.0.0.21", help="IP of the pretend device (query: the querier)")
    p.add_argument("--src-mac", help="MAC of the pretend device (default derived from the IP)")
    p.add_argument("--igmp", type=int, choices=[2, 3], default=2, help="IGMP version to speak")
    p.add_argument("--iface", default="lo")
    args = p.parse_args()
    mac = args.src_mac or default_mac(args.src_ip)

    if args.action == "query":
        dst, data = HOSTS, igmp.build_v2_query()
    elif args.igmp == 2:
        dst, data = (args.group, igmp.build_v2_report(args.group)) if args.action == "join" else (igmp.ALL_ROUTERS, igmp.build_v2_leave(args.group))
    else:
        rtype = igmp.RecordType.CHANGE_TO_EXCLUDE if args.action == "join" else igmp.RecordType.CHANGE_TO_INCLUDE
        dst, data = igmp.V3_REPORT_GROUP, igmp.build_v3_report([(rtype, args.group, [])])

    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW) as s:
        s.bind((args.iface, 0))
        s.send(build_frame(mac, args.src_ip, dst, data))
    print(f"sent IGMPv{args.igmp if args.action != 'query' else 2} {args.action} from {args.src_ip} ({mac}) on {args.iface}")


if __name__ == "__main__":
    main()
