import argparse


def main():
    args = get_args()
    validate_args(args)

    # SETUP connection with SDP
    # ENCODE audio source
    # TRANSMIT AUDIO with RTP