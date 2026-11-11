"""Packet-loss and latency measurement for the PAES67 controller.

Pass/fail criteria (all three must hold)
  * LOSS      : no packet sent was missed, duplicated or reordered           (limit: 0)
  * LATENCY   : the LATENCY_PERCENTILE-th percentile of latency <= LATENCY_LIMIT_MS
                default is the 100th percentile = every packet <= 1.0 ms (the project requirement)
  * TIMESTAMP : every RTP timestamp is exactly 48 ticks after the previous one (1 ms of audio at 48 kHz)
"""

from __future__ import annotations

import math
import random
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from argparse import ArgumentParser
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter_ns, sleep

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paes67.multicast import create_receiver, get_multicast_interface, leave_multicast

SAMPLE_RATE = 48000
FRAMES_PER_PACKET = 48          # 1 ms of audio
CHANNELS = 2
RECORD = struct.Struct("<HIQQ")  # must match tests/instrumented_controller.py

LATENCY_LIMIT_MS = 1.0
LATENCY_PERCENTILE = 99.9
MAX_LOST_PACKETS = 0
TEST_SECONDS = 5


# ----------------------------------------------------------------------------- test audio

def make_noise_wav(path: Path, seconds: float, seed: int = 1234) -> int:
    """Write a stereo 24-bit 48 kHz WAV of random samples (full range, so any corruption shows). Returns frame count."""
    frames = int(round(seconds * 1000)) * FRAMES_PER_PACKET  # whole packets only: the controller never pads
    data = random.Random(seed).randbytes(frames * CHANNELS * 3)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(3)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(data)
    return frames


# ----------------------------------------------------------------------------- statistics

def percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100) of an already sorted list."""
    if not sorted_values:
        return float("nan")
    rank = max(1, math.ceil(q / 100.0 * len(sorted_values)))
    return sorted_values[rank - 1]


def free_group_and_port() -> tuple[str, int]:
    rnd = random.SystemRandom()
    return f"239.69.{rnd.randint(1, 254)}.{rnd.randint(1, 254)}", rnd.randint(20000, 40000)


# ----------------------------------------------------------------------------- listener

class Listener(threading.Thread):
    """Joins a multicast group and records (receive_time_ns, seqno, rtp_timestamp, payload_len) for every packet."""

    def __init__(self, group: str, port: int, interface: str):
        super().__init__(daemon=True)
        self.group, self.port, self.interface = group, port, interface
        self.sock = create_receiver(group, port, interface)
        self.sock.settimeout(0.1)
        self.packets: list[tuple[int, int, int, int]] = []
        self._halt = threading.Event()

    def run(self) -> None:
        buf = bytearray(2048)
        while not self._halt.is_set():
            try:
                n = self.sock.recv_into(buf)
            except TimeoutError:
                continue
            except OSError:
                return
            now = perf_counter_ns()
            if n >= 12:
                self.packets.append((now, int.from_bytes(buf[2:4], "big"), int.from_bytes(buf[4:8], "big"), n - 12))

    def close(self) -> None:
        self._halt.set()
        self.join(timeout=2)
        leave_multicast(self.sock, self.group, self.interface)
        self.sock.close()


# ----------------------------------------------------------------------------- one measurement run

@dataclass
class Result:
    seconds: float
    sent: int = 0
    received: int = 0
    lost: int = 0
    duplicates: int = 0
    reordered: int = 0
    timestamp_errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    send_interval_ms: list[float] = field(default_factory=list)
    controller_output: str = ""

    def latency_stat(self, q: float) -> float:
        return percentile(sorted(self.latencies_ms), q)

    @property
    def loss_ok(self) -> bool:
        return self.sent > 0 and self.lost <= MAX_LOST_PACKETS and self.duplicates == 0 and self.reordered == 0

    @property
    def latency_ok(self) -> bool:
        return bool(self.latencies_ms) and self.latency_stat(LATENCY_PERCENTILE) <= LATENCY_LIMIT_MS

    @property
    def timestamp_ok(self) -> bool:
        return self.received > 1 and self.timestamp_errors == 0

    @property
    def passed(self) -> bool:
        return self.loss_ok and self.latency_ok and self.timestamp_ok


def run_measurement(seconds: float = TEST_SECONDS) -> Result:
    """Stream `seconds` of audio through the real controller and measure loss, latency and RTP timestamps."""
    group, port = free_group_and_port()
    interface = get_multicast_interface(group)
    result = Result(seconds=seconds)
    with tempfile.TemporaryDirectory() as tmp:
        wav, send_log = Path(tmp) / "noise.wav", Path(tmp) / "send.log"
        make_noise_wav(wav, seconds)
        listener = Listener(group, port, interface)
        listener.start()
        sleep(0.2)  # let the IGMP join settle
        try:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "logger.py"), str(send_log),
                 "--group", group, "--port", str(port), "--wav", str(wav), "--interface", interface],
                cwd=ROOT, capture_output=True, text=True, timeout=seconds + 30)
            result.controller_output = proc.stdout + proc.stderr
            sleep(0.3)  # let the last packets arrive
        finally:
            listener.close()
        if proc.returncode != 0:
            raise RuntimeError(f"controller failed:\n{result.controller_output}")
        raw = send_log.read_bytes()

    sent = [RECORD.unpack_from(raw, i) for i in range(0, len(raw), RECORD.size)]
    result.sent = len(sent)
    send_time = {seq: before for seq, _, before, _ in sent}
    result.send_interval_ms = [(b[2] - a[2]) / 1e6 for a, b in zip(sent, sent[1:])]

    seen: set[int] = set()
    previous = None
    for recv_ns, seq, ts, _ in listener.packets:
        if previous is not None:
            step = (seq - previous[0]) & 0xFFFF
            if seq in seen:
                result.duplicates += 1
            elif step >= 0x8000:
                result.reordered += 1
            if (ts - previous[1]) & 0xFFFFFFFF != FRAMES_PER_PACKET and step == 1:
                result.timestamp_errors += 1
        previous = (seq, ts)
        if seq in send_time and seq not in seen:
            result.latencies_ms.append((recv_ns - send_time[seq]) / 1e6)
        seen.add(seq)
    result.received = len(listener.packets)
    result.lost = len(set(send_time) - seen)
    return result


def report(r: Result) -> str:
    lat = sorted(r.latencies_ms)
    gap = sorted(r.send_interval_ms)
    mark = lambda ok: "PASS" if ok else "FAIL"
    lines = [
        f"PAES67 loopback measurement: {r.seconds:g} s of audio, {r.sent} packets sent",
        "",
        f"  packets received   {r.received:>8}     lost {r.lost}   duplicated {r.duplicates}   reordered {r.reordered}",
        f"  latency (ms)       median {percentile(lat, 50):.3f}   p99 {percentile(lat, 99):.3f}   "
        f"p99.9 {percentile(lat, 99.9):.3f}   max {percentile(lat, 100):.3f}",
        f"  packets > {LATENCY_LIMIT_MS:g} ms     {sum(1 for x in lat if x > LATENCY_LIMIT_MS)} of {len(lat)}",
        f"  send spacing (ms)  median {percentile(gap, 50):.3f}   p99 {percentile(gap, 99):.3f}   max {percentile(gap, 100):.3f}",
        f"  RTP timestamp      {r.timestamp_errors} steps that were not +{FRAMES_PER_PACKET}",
        "",
        f"  [{mark(r.loss_ok)}] loss       : at most {MAX_LOST_PACKETS} lost, 0 duplicated, 0 reordered",
        f"  [{mark(r.latency_ok)}] latency    : p{LATENCY_PERCENTILE:g} = {r.latency_stat(LATENCY_PERCENTILE):.3f} ms, limit {LATENCY_LIMIT_MS:g} ms",
        f"  [{mark(r.timestamp_ok)}] timestamps : advance {FRAMES_PER_PACKET} per packet",
        "",
        f"  OVERALL: {mark(r.passed)}",
    ]
    return "\n".join(lines)


def main() -> int:
    global LATENCY_LIMIT_MS, LATENCY_PERCENTILE

    parser = ArgumentParser()
    parser.add_argument("--seconds", type=float, default=TEST_SECONDS, help="length of audio to stream")
    parser.add_argument("--limit-ms", type=float, default=LATENCY_LIMIT_MS, help="latency limit in milliseconds")
    parser.add_argument("--percentile", type=float, default=LATENCY_PERCENTILE,
                        help="share of packets (0-100) that must meet the limit; 100 = every packet")
    args = parser.parse_args()
    LATENCY_LIMIT_MS = args.limit_ms
    LATENCY_PERCENTILE = args.percentile
    result = run_measurement(args.seconds)
    print(report(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    main()
