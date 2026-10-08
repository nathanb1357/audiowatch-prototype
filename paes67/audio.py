from pathlib import Path
from array import array
import wave

# Utility class for WAV sources
class WavSource:
    def __init__(self, path: Path):
        self.file = wave.open(str(path), "rb")
        self.sample_rate = self.file.getframerate()
        self.channels = self.file.getnchannels()
        self.sample_width = self.file.getsampwidth()

        if self.sample_width != 3:
            raise ValueError("WAV file must contain 24-bit PCM audio")

    def read_frames(self, count: int) -> bytes:
        return self.file.readframes(count)

    def close(self) -> None:
        self.file.close()

# Converts 24-bit PCM samples into bytes
def samples_to_bytes(samples: list[int]) -> bytes:
    values = array("i", (sample << 8 for sample in samples))
    return values.tobytes()
