
AudioWatch is a generic monitoring program for AES67 audio-over-IP networks. This project includes pAES67, a protocol suite that mimics an AES67 network in order to act as a test environment for the program. Currently, AudioWatch prints an alert whenever a device joins or leaves the audio multicast group.


### Protocols Implemented (pAES67)

- UDP connection
- IPv4 multicasting (IGMP)
- L24 audio encoding (24-bit linear)
- Session Announcement Protocol (SAP)
- Session Description Protocol (SDP)
- Real-Time Protocol v2 (RTP)


### Structure

- `/paes67` is a package for shared network stuff
- `/audiowatch` is the package that holds the main monitor
- `/controller` is the network controller that broadcasts the audio
- `/receiver` is a basic receiver that recieves and plays back the audio
- `/tests` is the test module for measuring project performance and behaviour


### Dependencies

- Linux (sudo required for AudioWatch)
- python3 (>=3.12)
- sounddevice
- make


### Setup

1. Open a terminal in the project folder.

2. Create and activate a virtual environment (recommended).
```
python3 -m venv .venv
source .venv/bin/activate
```

3. Install the pip dependencies
```
pip install -r requirements.txt
```


### Running

AudioWatch runs on the same machine as the controller (the admin device).

#### On 1 machine
1. Terminal 1: AudioWatch, watching the loopback interface
```
make audiowatch-local
```

2. Terminal 2: controller
```
make controller-local
```

3. Terminal 3: receiver
```
make receiver-local
```

#### On 2+ machines

Computer A is the admin device (AudioWatch and controller). Computer B is a receiver. Both must be on the same subnet. If a computer has several network interfaces (Wi-Fi plus Ethernet, VPN, virtual adapters), name the interface by its IP address so multicast leaves and arrives on the right one.

1. Computer A, terminal 1: AudioWatch. Add `--capture <network card>` (for example `eth0`) if A has several network cards.
```
make audiowatch GROUP=239.69.11.44
```

2. Computer A, terminal 2: controller.
```
python3 -m controller.main --group 239.69.11.44 --port 5004 --interface 192.168.50.1
```

3. Computer B: receiver. AudioWatch alerts when it starts (JOIN) and when you stop it with Ctrl-C (LEAVE).
```
python3 -m receiver.main --interface 192.168.50.2
```


### Testing

All tests below use `GROUP=239.69.11.44`

#### Test 1: Alerts on 1 machine

1. Terminal 1:
```
make controller-local
```

2. Terminal 2: 
```
make audiowatch-local
```

3. Terminal 3, one at a time:
```
sudo python3 -m tests.simulate_igmp join  --src-ip 10.0.0.21
sudo python3 -m tests.simulate_igmp join  --src-ip 10.0.0.22 --igmp 3
sudo python3 -m tests.simulate_igmp join  --src-ip 10.0.0.21 --src-mac 02:de:ad:be:ef:01
sudo python3 -m tests.simulate_igmp leave --src-ip 10.0.0.21
sudo python3 -m tests.simulate_igmp leave --src-ip 10.0.0.22 --igmp 3
```

#### Test 2: Alerts on 2 machines

Computer A runs the controller and AudioWatch. Computer B joins and leaves. Connect them with an Ethernet cable or an unmanaged switch and give them static IPs (below: A is 192.168.50.1, B is 192.168.50.2). Wi-Fi and switches with IGMP snooping often block this traffic.

1. Computer A, terminal 1: 
```
make audiowatch
```
2. Computer A, terminal 2: 
```
python3 -m controller.main --group 239.69.11.44 --port 5004 --interface 192.168.50.1
```

3. **JOIN:** (Computer B):
```
python3 -m receiver.main --interface 192.168.50.2 -q
```

4. **MAC_CHANGED:** (Computer B):
```
sudo python3 -m tests.simulate_igmp join --iface <B's network card> --src-ip 192.168.50.2 --src-mac 02:de:ad:be:ef:01
```

5. **LEAVE:** Press Ctrl-C on B's receiver.

6. **EXPIRED:** (Computer B). Run these, then wait about 4 minutes 20 seconds:
```
sudo python3 -m tests.simulate_igmp query --iface <B's network card> --src-ip 192.168.50.254
sudo python3 -m tests.simulate_igmp join  --iface <B's network card> --src-ip 192.168.50.99
```

#### Test 3: Streaming performance with AudioWatch

Across 2 machines:

1. Computer A: 
```
make audiowatch
```

2. Computer B: 
```
python3 -m receiver.main --interface 192.168.50.2 -q
```

3. Computer A: 
```
python3 -m controller.main --group 239.69.11.44 --port 5004 --interface 192.168.50.1 --time 60
```

4. On A, while AudioWatch is running, also run the latency/loss test.
```
make latency-report SECONDS=10
```


### Future Project Steps

- Implement functionality for audio that isn't 24-bit PCM
- Persist device information between sessions and let the user name devices
- Block devices from the group and prevent re-joining
- Create a monitor dashboard for future users
