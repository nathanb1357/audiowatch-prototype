**Milestone Goal**
- Build a passive AudioWatch monitor that creates an alert whenever a device joins or leaves the AES67 multicast that should print the info of those devices.

------------------------

## Tasks

1. Run everything with main.py
2. Testing (personal device)
3. Testing (lab devices)

-------------------------

## Monitor Functionality

A passive monitor that prints an alert, with the device's IP, MAC, VLAN and IGMP details, whenever a device joins or
leaves the audio multicast group. It runs on the admin device, the same machine as the controller, so it is simply told the controller's group (`--group`, default 239.69.11.44). It never joins the stream.

How it works: devices announce multicast membership with IGMP, so the monitor sniffs IGMP (v1/v2/v3) and keeps a
table of who is in the group.

```
make monitor                                           # same GROUP as make controller-local; needs root
sudo python3 -m audiowatch.main --group 239.69.11.44 --capture-iface eth0
python3 -m audiowatch.main --pcap capture.pcap         # replay a Wireshark capture, no root
```

Useful flags: `--capture-iface eth0`, `--log-file alerts.jsonl`, `--member-timeout`, `--name`, `-v` (print every IGMP message), `--bell`.

**Alerts**:
- `JOIN`
- `LEAVE` (explicit leave)
- `EXPIRED` (device stopped answering IGMP queries)
- `MAC_CHANGED` (a known IP appears from a new MAC)

**Manual test (one machine).** Real receivers on one host do not put IGMP on the loopback interface, so fabricate devices instead:
```
sudo python3 -m audiowatch.main --group 239.69.11.44 --capture-iface lo             # terminal 1
sudo python3 -m tests.inject_igmp join  --src-ip 10.0.0.21 --group 239.69.11.44      # terminal 2
sudo python3 -m tests.inject_igmp join  --src-ip 10.0.0.22 --group 239.69.11.44 --igmp 3
sudo python3 -m tests.inject_igmp leave --src-ip 10.0.0.21 --group 239.69.11.44
```

**Manual test (two or more machines).** Run the controller and `make monitor` on one machine, then start and Ctrl-C receivers on others; each should raise a JOIN and LEAVE alert.

Limits worth knowing:
- The monitor only sees IGMP that reaches the controller machine's NIC. Switches with IGMP snooping
  forward reports to the querier only, so on a managed switch use a mirror (SPAN) port to the controller's port.
- Devices already joined when the monitor starts are reported as `JOIN` the next time they answer an IGMP 
  query (up to ~125 s).
- With IGMPv2, hosts suppress their reports when another member has already answered, and only the last reporter
  sends a leave. The monitor refreshes all v2 members whenever any v2 report arrives, so they are not falsely expired, but a silent v2 departure is only noticed once the whole group goes quiet. IGMPv3 is tracked per device.
- Live capture is Linux only (AF_PACKET). `--backend scapy` is an untested option for Windows/macOS.

### Future Project Steps

- Persist device information between sessions and let the user name devices (`Device.label`, `JsonLogSink` are the seeds)
- Block devices from the group and prevent re-joining (add an enforcement sink that reacts to events)
- Dashboard for the monitor
