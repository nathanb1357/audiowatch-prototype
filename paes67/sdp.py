"""
I need a data class to store an SDP Session.
I need a function that returns an SDP Session from payload string.
"""

from dataclasses import dataclass
from ipaddress import ip_address
from time import time


@dataclass(slots=True)
class SdpSession:
    name: str
    origin_ip: str
    multicast_ip: str
    port: int
    packet_ms: float
    sample_rate: int
    payload_type: int = 96  # L24 has dynamic type
    ttl: int = 1

    # Convert to string
    def render(self) -> str:
        session_id = int(time())
        address = ip_address(self.multicast_ip)
        if address.version != 4 or not address.is_multicast:
            raise ValueError("multicast_ip must be an IPv4 multicast address")
        if not 0 <= self.ttl <= 255:
            raise ValueError("TTL must be between 0 and 255")
        if not 1 <= self.port <= 65535:
            raise ValueError("RTP port must be between 1 and 65535")
        return (
            "v=0\n"
            f"o=- {session_id} {session_id} IN IP4 {self.origin_ip}\n"
            f"s={self.name}\n"
            f"c=IN IP4 {self.multicast_ip}/{self.ttl}\n"
            "t=0 0\n"
            f"m=audio {self.port} RTP/AVP {self.payload_type}\n"
            f"a=rtpmap:{self.payload_type} L24/{self.sample_rate}\n"
            f"a=ptime:{self.packet_ms:g}\n"
            "a=recvonly\n"
        )


def parse_sdp(text: str) -> SdpSession:
    values: dict[str, str] = {}
    ptime = 1.0

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("a=rtpmap:"):
            rtpmap = line[len("a=rtpmap:"):]
            _, codec = rtpmap.split(None, 1)
            values["rtp"] = codec
        elif line.startswith("a=ptime"):
            ptime = float(line[len("a=ptime:"):])
        elif len(line) >= 2 and line[1] == "=":
            values[line[0]] = line[2:]

    if "c" not in values or "m" not in values or "s" not in values or "o" not in values:
        raise ValueError("SDP is missing required c=, o=, m=, or s= fields")

    connection = values["c"].split()
    if len(connection) != 3 or connection[0] != "IN" or connection[1] != "IP4":
        raise ValueError("only IPv4 multicast SDP is supported")
    address_parts = connection[2].split("/")
    multicast_ip = address_parts[0]
    ttl = int(address_parts[1]) if len(address_parts) > 1 else 1

    media = values["m"].split()
    if len(media) < 4 or media[0] != "audio" or media[2] != "RTP/AVP":
        raise ValueError("only RTP/AVP audio SDP is supported")
    port = int(media[1])
    payload_type = int(media[3])

    codec = rtpmap.get(payload_type)
    if not codec:
        raise ValueError("SDP is missing the RTP codec mapping")
    encoding, rate = codec.split("/")
    if encoding.upper() != "L24":
        raise ValueError(f"unsupported RTP encoding: {encoding}")

    origin_ip = values["o"].split()[-1]
    return SdpSession(
        name=values["s"],
        origin_ip=origin_ip,
        multicast_ip=multicast_ip,
        port=port,
        sample_rate=int(rate),
        payload_type=payload_type,
        packet_ms=ptime,
        ttl=ttl,
    )