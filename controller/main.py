from argparse import ArgumentParser, Namespace
from time import perf_counter, sleep
from pathlib import Path

from paes67.audio import WavSource, wav_to_payload
from paes67.multicast import get_multicast_interface, create_sender
from paes67.sap import SAP_GROUP_LOCAL, SAP_PORT, SapAnnouncer
from paes67.sdp import SdpSession
from paes67.rtp import RtpSenderState


SDP_STREAM_NAME = "PAES67"                      # Name of SDP Stream
SAMPLE_RATE = 48000                             # Audio sample rate
PACKET_MS = 1.0                                 # Length of audio per packet
WAV_PATH = Path(__file__).parent / "test.wav"   # Filepath for test WAV


# Define and return the program's parsed arguments
def get_args() -> Namespace:
    parser = ArgumentParser(description="Send a low-latency stream of encoded audio using pseudo-AES67 (PAES67)")
    parser.add_argument("--group",      type=str,   help="IPv4 multicast group")
    parser.add_argument("--sap-group",  type=str,   help="SAP multicast group (224.2.127.254 for global scope)", default=SAP_GROUP_LOCAL)
    parser.add_argument("--port",       type=int,   help="UDP destination port")
    parser.add_argument("--sap-port",   type=int,   help="SAP UDP port", default=SAP_PORT)
    parser.add_argument("--interface",  type=str,   help="IPv4 interface address (default: auto)", default="auto")
    parser.add_argument("--time",       type=float, help="Length of run in seconds; 0 means until Ctrl-C", default=0.0)
    parser.add_argument("--wav",        type=str,   help="Path of the WAV audio to send", default=WAV_PATH)
    return parser.parse_args()


# Verify that arguments are valid
def verify_args(args: Namespace) -> None:
    if not (1 <= args.port <= 65535):
        raise SystemExit("--port must be between 1 and 65535")
    if not (1 <= args.sap_port <= 65535):
        raise SystemExit("--sap-port must be between 1 and 65535")


def main():
    args = get_args()
    verify_args(args)

    try:
        source = WavSource(str(args.wav))
    except (OSError, EOFError, ValueError) as e:
        raise SystemExit(f"Cannot open WAV file {args.wav}: {e}")
    interface = get_multicast_interface(args.group) if args.interface == "auto" else args.interface
    frame_count = int(round(source.sample_rate * PACKET_MS / 1000.0))

    # Create RTP stream with SDP
    session = SdpSession(
        name=SDP_STREAM_NAME,
        origin_ip=interface,
        multicast_ip=args.group,
        port=args.port,
        packet_ms=PACKET_MS,
        sample_rate=source.sample_rate
    )
    sdp = session.render()
    rtp = RtpSenderState()
    sock = create_sender(interface)

    # Create SAP announcer
    sap_sock = create_sender(interface)
    announcer = SapAnnouncer(sap_sock, interface, sdp, args.sap_group, args.sap_port)
    packet_interval = frame_count / source.sample_rate
    next_deadline = perf_counter()
    start_time = next_deadline
    packets = 0
    samples = 0

    print(f"Controller/source interface: {interface}")
    print(f"Multicast                  : {args.group}:{args.port}")
    print(f"Audio                      : L24 {source.sample_rate} Hz from {args.wav}")
    print(f"Packet time                : {PACKET_MS:g} ms ({frame_count} frames)")
    print(f"SAP announcements          : {args.sap_group}:{args.sap_port}\n")
    print("Streaming... Ctrl-C to stop.")

    # Sending loop
    try:
        while True:
            announcer.poll()
            block = source.read_block(frame_count)
            if block is None:
                break
            payload = wav_to_payload(block)
            packet = rtp.packet(payload, frame_count)
            sock.sendto(packet.pack(), (args.group, args.port))
            packets += 1
            samples += frame_count

            next_deadline += packet_interval
            remaining = next_deadline - perf_counter()
            if remaining > 0.00025:
                sleep(remaining - 0.00015)
            while perf_counter() < next_deadline:
                pass

            # Check timeout
            if args.time > 0 and (perf_counter() - start_time) >= args.time:
                break

    except KeyboardInterrupt:
        pass

    finally:
        announcer.close()
        sap_sock.close()
        sock.close()
        source.close()

    elapsed = perf_counter() - start_time
    print(f"Sent {packets} RTP packets / {samples} samples in {elapsed:.3f}s ({packets / elapsed:.1f} packets/s)")


if __name__ == "__main__":
    main()
