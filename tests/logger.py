import atexit
import runpy
import struct
import sys
from pathlib import Path
from time import perf_counter_ns

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paes67.multicast as multicast

RECORD = struct.Struct("<HIQQ")
SAP_PORT = 9875
log_path, controller_args = sys.argv[1], sys.argv[2:]
records: list[bytes] = []


class LoggingSocket:
    def __init__(self, sock):
        self._sock = sock

    def sendto(self, data, address):
        before = perf_counter_ns()
        sent = self._sock.sendto(data, address)
        after = perf_counter_ns()
        if address[1] != SAP_PORT:  # RTP packets only
            records.append(RECORD.pack(int.from_bytes(data[2:4], "big"), int.from_bytes(data[4:8], "big"), before, after))
        return sent

    def __getattr__(self, name):
        return getattr(self._sock, name)


original_create_sender = multicast.create_sender
multicast.create_sender = lambda interface_ip: LoggingSocket(original_create_sender(interface_ip))


def write_log() -> None:
    with open(log_path, "wb") as f:
        f.write(b"".join(records))


atexit.register(write_log)
sys.argv = ["controller/main.py"] + controller_args
runpy.run_module("controller.main", run_name="__main__")
