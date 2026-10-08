from argparse import ArgumentParser, Namespace

# import SAP_GROUP_LOCAL and SAP_PORT


SDP_STREAM_NAME = "PAES67"      # Name of SDP Stream
IGMP_INTERFACE = "0.0.0.0"
OUT_PATH = "temp/out.wav"       # Path of the reconstructed WAV


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


def main():
    args = get_args()
    verify_args(args)

    # Select SDP stream
    # Connect to multicast with IGMP
    # Recieve audio stream
    # Playback audio