from argparse import ArgumentParser, Namespace
from time import perf_counter

# import SAP_GROUP_LOCAL and SAP_PORT
from paes67.audio import open_wav
from paes67.multicast import create_receiver, leave_multicast
from paes67.sap import SDP_TYPE, SapPacket
from paes67.sdp import SdpSession, parse_sdp


SDP_STREAM_NAME = "PAES67"      # Name of SDP Stream
IGMP_INTERFACE = "0.0.0.0"
OUT_PATH = "temp/out.wav"       # Path of the reconstructed WAV
SAP_TIMEOUT = 30.0              # Seconds to wait for matching announcement


# Define and return the program's parsed arguments
def get_args() -> Namespace:
    parser = ArgumentParser(description="Send a low-latency stream of encoded audio using pseudo-AES67 (PAES67)")
    parser.add_argument("--sap-group",  type=str,   help="SAP multicast group to listen on", default=SAP_GROUP_LOCAL)
    parser.add_argument("--sap-port",   type=int,   help="SAP listen port", default=SAP_PORT)
    parser.add_argument("--interface",  type=str,   help="IPv4 interface address", default=IGMP_INTERFACE)
    parser.add_argument("--time",       type=float, help="Receive duration in seconds; 0 means until Ctrl-C", default=0.0)
    parser.add_argument("--quiet", "-q",type=bool,  help="Disable live playback", action='store_true')
    return parser.parse_args()


# Verify that arguments are valid
def verify_args(args: Namespace) -> None:
    if not (1 <= args.sap_port <= 65535):
        raise SystemExit("--sap-port must be between 1 and 65535")


# Listen on the SAP group until an expected announcement arrives
def discover_stream(args: Namespace) -> SdpSession:
    sap_socket = create_receiver(args.sap_group, args.sap_port, args.interface)
    sap_socket.settimeout(0.25)

    deadline = perf_counter() + SAP_TIMEOUT
    heard: dict[tuple[str, str, int], SdpSession] = {}
    print(f"Listening for SAP          : {args.sap_group}:{args.sap_port}")

    try:
        while perf_counter() < deadline:
            try:
                data, _ = sap_socket.recvfrom(64 * 1024)
                announcement = SapPacket.unpack(data)
            except (TimeoutError, ValueError):
                continue
            if announcement.deletion or announcement.payload_type != SDP_TYPE:
                continue
            try:
                session = parse_sdp(announcement.payload)
            except (ValueError, IndexError):
                continue  # not an L24 IPv4 RTP/AVP stream we can play

            key = (session.name, session.multicast_ip, session.port)
            if key not in heard:
                heard[key] = session
                print(f"Heard stream               : '{session.name}' {session.multicast_ip}:{session.port}")

            if args.stream_name and session.name.lower() != args.stream_name.lower():
                continue
            if args.group and session.multicast_ip != args.group:
                continue
            if args.port and session.port != args.port:
                continue
            return session
    
    finally:
        leave_multicast(sap_socket, args.sap_group, args.interface)
        sap_socket.close()

    if heard:
        names = ", ".join(f"'{name}'" for name, _, _ in heard)
        raise SystemExit(f"No SAP announcement matched the filters; heard: {names}")
    raise SystemExit("No SAP announcements received before the discovery timeout")


def main():
    args = get_args()
    verify_args(args)

    # Select SDP session
    session = discover_stream(args)
    group = session.multicast_ip
    port = session.port

    recv_socket = create_receiver(group, port, args.interface)
    wav = open_wav(OUT_PATH, session.sample_rate)

    # Create playback object
    # Recieve audio stream
    # Playback audio