from argparse import ArgumentParser, Namespace
from pathlib import Path

# import SAP_GROUP_LOCAL and SAP_PORT


SDP_STREAM_NAME = "PAES67"      # Name of SDP Stream
SAMPLE_RATE = 48000             # Audio sample rate
PACKET_MS = 1.0                 # Length of audio per packet
CHANNELS = 2                    # Two channels for stereo audio
WAV_PATH = "test.wav"           # Filepath for test WAV
SAP_TTL = 1                     # Multicast TTL for SAP announcements
SAP_INTERVAL = 30.0             # Seconds between normal SAP announcements


# Define and return the program's parsed arguments
def get_args() -> Namespace:
    parser = ArgumentParser(description="Send a low-latency stream of encoded audio using pseudo-AES67 (PAES67)")
    parser.add_argument("--ip",         type=str,   help="IPv4 multicast destination")
    parser.add_argument("--sap-ip",     type=str,   help="SAP multicast group (224.2.127.254 for global scope)", default=SAP_GROUP_LOCAL)
    parser.add_argument("--port",       type=int,   help="UDP destination port")
    parser.add_argument("--sap-port",   type=int,   help="SAP UDP port", default=SAP_PORT)
    parser.add_argument("--interface",  type=str,   help="IPv4 interface address (default: auto)", default="auto")
    parser.add_argument("--time",       type=float, help="Length of run in seconds; 0 means until Ctrl-C", default=0.0)
    parser.add_argument("--wav",        type=Path,  help="Path of the WAV audio to send", default=WAV_PATH)
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

    # SETUP connection with SDP
    # ENCODE audio source
    # TRANSMIT AUDIO with RTP