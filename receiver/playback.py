""" Allows the reciever to play L24 audio with LOW-LATENCY """

from __future__ import annotations
from queue import Queue, Full, Empty
from threading import Thread

from paes67.audio import samples_to_int32_bytes
import sounddevice as sd


class AudioPlayer:
    def __init__(self, sample_rate: int, quiet: bool, queue_len: int = 4) -> None:
        self.dropped_blocks = 0
        self.stream = None
        self._queue = None
        self._thread = None
        if quiet:
            return

        self.stream = sd.RawOutputStream(
            samplerate=sample_rate,
            dtype="int32",
            channels=2,
            blocksize=0,
            latency="low"
        )
        self.stream.start()
        self._queue = Queue(maxsize=max(1, queue_len))
        self._thread = Thread(target=self._worker, name="audio-playback", daemon=True)
        self._thread.start()

    # Consume queued audio blocks and write them to the output stream
    def _worker(self) -> None:
        assert self._queue is not None
        while True:
            block = self._queue.get()
            if block is None:
                return
            try:
                assert self.stream is not None
                self.stream.write(block)
            except Exception:
                return

    # Queue audio samples for playback. Drop oldest block if full
    def write(self, samples: list[int]) -> None:
        if self._queue is None:
            return
        block = samples_to_int32_bytes(samples)
        try:
            self._queue.put_nowait(block)
        except Full:
            try:
                self._queue.get_nowait()
            except Empty:
                pass
            try:
                self._queue.put_nowait(block)
            except Full:
                pass
            self.dropped_blocks += 1

    # Stop playback and release resources
    def close(self) -> None:
        if self._queue is not None:
            try:
                self._queue.put_nowait(None)
            except Full:
                try:
                    self._queue.get_nowait()
                except Empty:
                    pass
                try:
                    self._queue.put_nowait(None)
                except Full:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
