from dataclasses import dataclass
from ipaddress import ip_address
from struct import pack, unpack
from socket import socket
from time import perf_counter
import zlib



SAP_PORT = 9875
SAP_GROUP_GLOBAL = "224.2.127.254"  # global scope
SAP_GROUP_LOCAL = "239.255.255.255" # administratively scoped
SDP_TYPE = "application/sdp"

_FLAG_VER = 1
_FLAG_IPV6 = 0x10
_FLAG_DELETE = 0x04
_FLAG_ENCRYPTED = 0x02
_FLAG_COMPRESSED = 0x01


# 16-bit hash calculated for each new SDP announcement
def msg_id_hash(sdp: str) -> int:
    return zlib.crc32(sdp.encode("utf-8")) & 0xFFFF


@dataclass(slots=True)
class SapPacket:
    origin: str
    msg_id_hash: int
    payload: str
    deletion: bool = False
    payload_type: str = SDP_TYPE

    # Pack SDP data into packet
    def pack(self, compress: bool = False) -> bytes:
        origin = ip_address(self.origin)
        flags = _FLAG_VER << 5
        if origin.version == 6:
            flags |= _FLAG_IPV6
        if self.deletion:
            flags |= _FLAG_DELETE
        body = self.payload.encode("utf-8")
        if compress:
            flags |= _FLAG_COMPRESSED
            body = zlib.compress(body)
        header = pack("!BBH", flags, 0, self.msg_id_hash & 0xFFFF) + origin.packed
        return header + self.payload_type.encode("ascii") + b"\x00" + body

    @classmethod
    def unpack(cls, data: bytes) -> SapPacket:
        if len(data) < 8:
            raise ValueError("SAP packet too short")
        flags, auth_len, msg_id = unpack("!BBH", data[:4])
        if flags >> 5 != _FLAG_VER:
            raise ValueError("unsupported SAP version")
        if flags & _FLAG_ENCRYPTED:
            raise ValueError("encrypted SAP packets are not supported")
        addr_len = 16 if flags & _FLAG_IPV6 else 4
        offset = 4 + addr_len
        if len(data) < offset:
            raise ValueError("truncated SAP header")
        origin = str(ip_address(data[4:offset]))
        offset += auth_len * 4  # authentication data is ignored
        rest = data[offset:]
        if len(rest) < 1:
            raise ValueError("empty SAP payload")

        # Payload type is optional: a bare SDP starts with "v=0".
        if rest.startswith(b"v=0"):
            payload_type = SDP_TYPE
            body = rest
        else:
            end = rest.find(b"\x00")
            if end < 0:
                raise ValueError("unterminated SAP payload type")
            payload_type = rest[:end].decode("ascii", "replace")
            body = rest[end + 1:]
        if flags & _FLAG_COMPRESSED:
            try:
                body = zlib.decompress(body)
            except zlib.error as exc:
                raise ValueError("bad compressed SAP payload") from exc
        return cls(
            origin=origin,
            msg_id_hash=msg_id,
            payload=body.decode("utf-8", "replace"),
            deletion=bool(flags & _FLAG_DELETE),
            payload_type=payload_type.strip().lower(),
        )


class SapAnnouncer:
    # Periodically announce SDP. Call poll()
    # Begins with announcement burst. Then settle into interval.
    # Send deletion packet with close()

    def __init__(
        self,
        sock: socket,
        origin_ip: str,
        packet: str,
        group: str = SAP_GROUP_LOCAL,
        port: int = SAP_PORT,
        interval: float = 15.0
    ) -> None:
        self._sock = sock
        self._destination = (group, port)
        self._packet = SapPacket(origin_ip, msg_id_hash(packet), packet)
        self._interval = max(1.0, interval)
        self._startup = [4.0, 2.0, 1.0] # Announcement burst timings
        self._next = perf_counter()

    # Check if its time to send another announcement
    def poll(self, now: float | None = None) -> None:
        now = perf_counter() if now is None else now
        if now < self._next:
            return
        self.send(self._packet)
        delay = self._startup.pop() if self._startup else self._interval
        self._next = now + delay

    def send(self, packet: SapPacket) -> None:
        try:
            self._sock.sendto(packet.pack(), self._dest)
        except OSError:
            pass

    def close(self) -> None:
        delete_packet = SapPacket(self._packet.origin, self._packet.msg_id_hash, self._packet.payload, deletion=True)
        for _ in range(2):
            self.send(delete_packet)
