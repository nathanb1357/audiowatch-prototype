
This project prototype mimics an AES67 audio-over-IP network (pAES67) as a basis to implement the
AudioWatch monitoring software to add security to an otherwise unencrypted protocol suite.


### Protocols Implemented (pAES67)

- UDP connection
- IPv4 multicasting (IGMP)
- L24 audio encoding (24-bit linear)
- Session Announcement Protocol (SAP)
- Session Description Protocol (SDP)
- Real-Time Protocol v2 (RTP)


### Structure

- `/paes67` is a package for shared network stuff
- `/controller` is the network controller that broadcasts the audio
- `/receiver` is a basic receiver that recieves and plays back the audio
- `/tests/` is the test module for measuring success

### Dependencies

- python3
- sounddevice
- make

### Setup

1. Get the project folder and open a terminal in it.
```
cd audiowatch-prototype
```

2. Create and activate a virtual environment (recommended).
```
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

3. Install the pip dependencies
```
pip install -r requirements.txt
```

### Running

#### On 1 machine
1. Terminal 1, receiver. Start it first. It waits up to 15 seconds for a SAP announcement.
```
make receiver-local
```

2. Terminal 2, controller.
```
make controller-local
```

Or with your own file and settings:
```
python3 -m controller.main --group 239.69.11.44 --port 5004 --wav path/to/audio.wav
```
Stop the receiver with Ctrl-C after the controller finishes. It prints a summary, including Detected sequence gaps : 0 packet(s). The received audio is saved to temp/out.wav and is overwritten on every run.

#### On 2+ machines

Run the receiver on one computer and the controller on another, both on the same subnet. On a computer with several network interfaces (Wi-Fi plus Ethernet, VPN, virtual adapters), name the interface by its IP address so multicast leaves and arrives on the right one:
```
python3 -m controller.main --group 239.69.11.44 --port 5004 --interface 192.168.1.20
python3 -m receiver.main --interface 192.168.1.30
```

#### Testing

The latency/loss test suite can be run with just:
```
make latency-report
```

### Future Project Steps

- Implement SIP for connection management and maybe PTP for more accuracy
- Implement functionality for audio that isn't 24-bit PCM
