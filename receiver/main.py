from argparse import ArgumentParser, Namespace
from time import perf_counter

from .playback import AudioPlayer
from paes67.audio import open_wav, samples_to_wav24_bytes
from paes67.multicast import create_receiver, leave_multicast
from paes67.sap import SAP_GROUP_LOCAL, SAP_PORT, SDP_TYPE, SapPacket
from paes67.sdp import SdpSession, parse_sdp
from paes67.rtp import RtpPacket, unpack_l24


SDP_STREAM_NAME = "PAES67"      # Name of SDP Stream
IGMP_INTERFACE = "0.0.0.0"
OUT_PATH = "temp/out.wav"       # Path of the reconstructed WAV
SAP_TIMEOUT = 15.0              # Seconds to wait for matching announcement
CHANNELS = 2
KB = 1024                       # Size of one kilobyte (in bytes)


# Define and return the program's parsed arguments
def get_args() -> Namespace:
    parser = ArgumentParser(description="Send a low-latency stream of encoded audio using pseudo-AES67 (PAES67)")
    parser.add_argument("--sap-group",  type=str,   help="SAP multicast group to listen on", default=SAP_GROUP_LOCAL)
    parser.add_argument("--sap-port",   type=int,   help="SAP listen port", default=SAP_PORT)
    parser.add_argument("--interface",  type=str,   help="IPv4 interface address", default=IGMP_INTERFACE)
    parser.add_argument("--time",       type=float, help="Receive duration in seconds; 0 means until Ctrl-C", default=0.0)
    parser.add_argument("--quiet", "-q",help="Disable live playback", action='store_true')
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

            if session.name.upper() != SDP_STREAM_NAME:
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

    # Initialize playback variables
    sock = create_receiver(group, port, args.interface)
    wav = open_wav(OUT_PATH, session.sample_rate)
    player = AudioPlayer(session.sample_rate, args.quiet)

    # Prepare for receiving
    sock.settimeout(0.25)
    start = perf_counter()
    packets = 0
    bytes_received = 0
    samples_received = 0
    lost = 0
    last_seqno = None
    last_ssrc = None

    print(f"Receiver interface         : {args.interface}")
    print(f"Joined multicast           : {group}:{port}")
    print(f"Expected audio             : L24 {session.sample_rate} Hz")
    print(f"Playback                   : {'OFF' if args.quiet else 'ON'}\n")
    print("Receiving... Ctrl-C to stop.")

    # Actual recieving + playback
    try:
        while True:
            try:
                packet_bytes, _ = sock.recvfrom(64 * KB)
                packet = RtpPacket.unpack(packet_bytes)
            except (TimeoutError, ValueError):
                continue

            if last_ssrc is not None and packet.ssrc != last_ssrc:
                continue
            if last_seqno is not None:
                expected = (last_seqno + 1) & 0xFFFF
                gap = (packet.seqno - expected) & 0xFFFF
                if gap < 0x8000:
                    lost += gap
            last_seqno = packet.seqno
            last_ssrc = packet.ssrc

            samples = unpack_l24(packet.payload)
            if len(samples) % CHANNELS != 0:
                continue

            if wav:
                wav.writeframesraw(samples_to_wav24_bytes(samples))
            if player:
                player.write(samples)

            packets += 1
            bytes_received += len(packet.payload)
            samples_received += len(samples)
    
    except KeyboardInterrupt:
        pass

    finally:
        if player:
            player.close()
        if wav:
            wav.close()
        leave_multicast(sock, group, args.interface)
        sock.close()

    # Give session recap
    elapsed = max(perf_counter() - start, 1e-9)
    frames = samples_received // CHANNELS
    print(f"Received {packets} RTP packets, {frames} frames, {bytes_received} payload bytes in {elapsed:.3f}s")
    print(f"Observed packet rate       : {packets / elapsed:.1f} packets/s")
    print(f"Detected sequence gaps     : {lost} packet(s)")


if __name__ == "__main__":
    main()
