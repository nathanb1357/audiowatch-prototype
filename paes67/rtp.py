"""
RTP utilities for PAES67 L24 audio.
- Packet class that can be packed and unpacked.
- Unpack L24 payload into a list of samples.
- Pack list of samples into L24 payload.
- Sender state that is used by the controller.
"""

from __future__ import annotations
from dataclasses import dataclass
from random import getrandbits
import struct

RTP_VERSION = 2
RTP_HEADER_SIZE = 12


@dataclass(slots=True)
class RtpPacket:
    payload_type: int
    seqno: int
    timestamp: int
    ssrc: int
    payload: bytes
    marker: bool = False

    def pack(self) -> bytes:
        first = RTP_VERSION << 6
        second = ((1 if self.marker else 0) << 7) | (self.payload_type & 0x7F)
        header = struct.pack(">BBHII", first, second, self.seqno & 0xFFFF, self.timestamp & 0xFFFFFFFF, self.ssrc & 0xFFFFFFFF)
        return header + self.payload

    @classmethod
    def unpack(cls, packet: bytes) -> "RtpPacket":
        if len(packet) < RTP_HEADER_SIZE:
            raise ValueError("RTP packet is shorter than the 12-byte header")
        first, second, seqno, timestamp, ssrc = struct.unpack(">BBHII", packet[:12])

        version = first >> 6
        padding = bool(first & 0x20)
        extension = bool(first & 0x10)
        csrc_count = first & 0x0F
        offset = RTP_HEADER_SIZE + 4 * csrc_count
        if version != RTP_VERSION:
            raise ValueError(f"unsupported RTP version: {version}")
        if len(packet) < offset:
            raise ValueError("RTP packet ends inside the CSRC list")
        
        if extension:
            _, extension_words = struct.unpack(">HH", packet[offset:offset + 4])
            offset += 4 + extension_words * 4
            if len(packet) < offset:
                raise ValueError("RTP header extension exceeds packet length")

        marker = bool(second & 0x80)
        payload_type = second & 0x7F
        payload = packet[offset:]
        if padding:
            if not payload:
                raise ValueError("RTP padding bit set with empty payload")
            pad_count = payload[-1]
            if pad_count == 0 or pad_count > len(payload):
                raise ValueError("invalid RTP padding")
            payload = payload[:-pad_count]

        return cls(payload_type, seqno, timestamp, ssrc, payload, marker)


# Sender state that is used to generate packets
class RtpSenderState:
    def __init__(self, payload_type: int = 96):
        self.payload_type = payload_type
        self.ssrc = getrandbits(32)
        self.seqno = getrandbits(16) # initial value SHOULD be random (RTP)
        self.timestamp = getrandbits(32) # initial value SHOULD be random (RTP)

    def packet(self, payload: bytes, increment: int, marker: bool = False) -> RtpPacket:
        packet = RtpPacket(
            payload_type=self.payload_type,
            seqno=self.seqno,
            timestamp=self.timestamp,
            ssrc=self.ssrc,
            payload=payload,
            marker=marker
        )
        self.seqno = (self.seqno + 1) & 0xFFFF # 16-bits
        self.timestamp = (self.timestamp + increment) & 0xFFFFFFFF # 32-bits
        return packet


# Pack list of samples into L24 payload
def pack_l24(samples: list[int]) -> bytes:
    out = bytearray(len(samples) * 3)
    i = 0

    for sample in samples:
        if sample < -8388608:
            sample = -8388608 # MIN 24-bit int
        elif sample > 8388607:
            sample = 8388607 # MAX 24-bit int
        if sample < 0:
            sample += 1 << 24
        out[i] = (sample >> 16) & 0xFF
        out[i+1] = (sample >> 8) & 0xFF
        out[i+2] = sample & 0xFF
        i += 3
    return bytes(out)


# Unpack L24 payload into a list of samples
def unpack_l24(payload: bytes) -> list[int]:
    if len(payload) % 3:
        raise ValueError("L24 payload length must be divisible by three")
    
    samples = [0] * (len(payload) // 3)
    out_index = 0
    for i in range(0, len(payload), 3):
        value = (payload[i] << 16) | (payload[i+1] << 8) | payload[i+2]
        if value & 0x800000:
            value -= 1 << 24
        samples[out_index] = value
        out_index += 1
    return samples