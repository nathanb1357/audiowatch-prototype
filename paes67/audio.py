from array import array
from pathlib import Path
import wave


# Utility class for WAV sources
class WavSource:
    def __init__(self, path: str):
        self.file = wave.open(path, "rb")
        self.sample_rate = self.file.getframerate()
        self.channels = self.file.getnchannels()
        self.sample_width = self.file.getsampwidth()

        if self.sample_width != 3:
            raise ValueError("WAV file must contain 24-bit PCM audio")

    def read_frames(self, count: int) -> bytes:
        return self.file.readframes(count)

    def read_block(self, frame_count: int) -> bytes | None:
        frame_bytes = self.channels * 3
        want = frame_count * frame_bytes
        data = self.read_frames(frame_count)
        if not data:
            return None
        if len(data) < want:
            data += b"\x00" * (want - len(data))
        return data

    def close(self) -> None:
        self.file.close()


# Converts 24-bit PCM samples into bytes (for playback)
def samples_to_int32_bytes(samples: list[int]) -> bytes:
    values = array("i", (sample << 8 for sample in samples))
    return values.tobytes()


# Converts 24-bit PCM samples into WAV bytes (for file)
def samples_to_wav24_bytes(samples: list[int]) -> bytes:
    out = bytearray(len(samples) * 3)
    index = 0
    for sample in samples:
        if sample < 0:
            sample += 1 << 24
        out[index] = (sample >> 16) & 0xFF
        out[index + 1] = (sample >> 8) & 0xFF
        out[index + 2] = sample & 0xFF
        index += 3
    return bytes(out)


# Open wav file
def open_wav(path: Path, sample_rate: int) -> wave.Wave_write:
    wav = wave.open(str(path), "wb")
    wav.setnchannels(2)
    wav.setsampwidth(3)
    wav.setframerate(sample_rate)
    return wav


# Convert wav to big-endian L24
def wav_to_payload(data: bytes) -> bytes:
    out = bytearray(len(data))
    out[0::3] = data[2::3]
    out[1::3] = data[1::3]
    out[2::3] = data[0::3]
    return bytes(out)
