from socket import *


# Return the interface IP determinined automatically by the OS.
def get_multicast_interface(group: str) -> str:
    sock = socket(AF_INET, SOCK_DGRAM)
    try:
        sock.connect((group, 80))
        return sock.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        sock.close()


# Create a multicast UDP sender socket.
def create_sender(interface_ip: str | None) -> socket:
    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
    sock.setsockopt(IPPROTO_IP, IP_MULTICAST_LOOP, 1)
    if interface_ip and interface_ip != "0.0.0.0":
        sock.setsockopt(IPPROTO_IP, IP_MULTICAST_IF, inet_aton(interface_ip))
    return sock


# Create a multicast UDP receiver socket.
def create_receiver(group: str, port: int, interface_ip: str | None) -> socket:
    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(("", port))

    iface = interface_ip or "0.0.0.0"
    membership = inet_aton(group) + inet_aton(iface)
    sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, membership)
    return sock


# Leave the multicast group.
def leave_multicast(sock: socket, group: str, interface_ip: str | None) -> None:
    iface = interface_ip or "0.0.0.0"
    membership = inet_aton(group) + inet_aton(iface)
    try:
        sock.setsockopt(IPPROTO_IP, IP_DROP_MEMBERSHIP, membership)
    except OSError:
        pass
