""" AudioWatch Monitor

Runs on the admin device (same as controller) and is forwarded the group's IGMP messages
by a controlled switch.
"""

from argparse import ArgumentParser, Namespace


SDP_STREAM_NAME = "PAES67"                      # Name of SDP Stream


# Define and return the program's parsed arguments
def get_args() -> Namespace:
    p = ArgumentParser(description="AudioWatch: A generic monitoring system for AES67 networks")
    p.add_argument("--group",       type=str,   help="Multicast group the controller sends to")
    p.add_argument("--capture",     type=str,   help="NIC to sniff IGMP on (eth0, all, etc.)")
    p.add_argument("--mem-timeout", type=float, help="Seconds without an IGMP report before a member is declared gone", default=DEFAULT_MEMBER_TIMEOUT)
    p.add_argument("--log-file",    type=str,   help="Log file to append every alert as a JSON line")
    p.add_argument("-v", "--verbose", action="store_true", help="Print every IGMP message seen")
    return p.parse_args()


# Verify that the supplied args are valid
def verify_args(args: Namespace) -> None:
    if args.mem_timeout <= 0:
        raise SystemExit("--mem-timeout must be positive")
    if not args.group.startswith(tuple(f"{n}." for n in range(224, 240))):
        raise SystemExit(f"--group {args.group} is not an IPv4 multicast address")


def main() -> None:
    args = get_args()
    verify_args(args)

