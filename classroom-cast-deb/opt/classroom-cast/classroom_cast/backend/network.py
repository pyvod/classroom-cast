import os
import socket
import logging
import struct
import fcntl
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class NetworkManager:
    """Manage network detection and hotspot functionality."""

    def __init__(self):
        self._primary_ip: Optional[str] = None
        self._all_ips: List[str] = []
        self._refresh()

    def _refresh(self):
        self._all_ips = self._get_local_ips()
        self._primary_ip = self._get_primary_ip()

    @staticmethod
    def _get_ips_from_sysfs() -> List[str]:
        """Read IPv4 addresses from /sys/class/net (Linux, no deps)."""
        ips = []
        try:
            for iface in os.listdir("/sys/class/net"):
                if iface == "lo":
                    continue
                try:
                    state = Path(f"/sys/class/net/{iface}/operstate").read_text().strip()
                    if state not in ("up", "unknown"):
                        continue
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        ifr = struct.pack("16sH14s", iface.encode()[:16],
                                          socket.AF_INET, b"\x00" * 14)
                        result = fcntl.ioctl(s.fileno(), 0x8915, ifr)  # SIOCGIFADDR
                        ip = socket.inet_ntoa(result[20:24])
                        if not ip.startswith("127.") and not ip.startswith("169.254."):
                            ips.append(ip)
                    except OSError:
                        pass
                    finally:
                        s.close()
                except OSError:
                    continue
        except Exception:
            pass
        return ips

    @staticmethod
    def _get_ips_from_hostname() -> List[str]:
        """Fallback: use gethostname + getaddrinfo."""
        ips = []
        try:
            hostname = socket.gethostname()
            infos = socket.getaddrinfo(
                hostname, None, socket.AF_INET, socket.SOCK_STREAM
            )
            seen = set()
            for info in infos:
                ip = info[4][0]
                if not ip.startswith("127.") and ip not in seen:
                    ips.append(ip)
                    seen.add(ip)
        except Exception:
            pass
        return ips

    @staticmethod
    def _get_local_ips() -> List[str]:
        """Get all non-loopback IPv4 addresses."""
        ips = []
        try:
            import netifaces
            for iface in netifaces.interfaces():
                try:
                    addrs = netifaces.ifaddresses(iface)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr["addr"]
                            if not ip.startswith("127.") and not ip.startswith("169.254."):
                                ips.append(ip)
                except (ValueError, OSError):
                    continue
            return ips if ips else ["127.0.0.1"]
        except ImportError:
            pass

        # Linux: read /sys/class/net directly (netifaces alternative)
        ips = NetworkManager._get_ips_from_sysfs()
        if ips:
            return ips

        # Cross-platform fallback
        ips = NetworkManager._get_ips_from_hostname()
        return ips if ips else ["127.0.0.1"]

    @staticmethod
    def _get_primary_ip() -> Optional[str]:
        """Get primary LAN IP — the one clients should connect to."""
        # Method 1: try connecting to external IP to find the kernel-preferred interface
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)
            s.connect(("223.5.5.5", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

        # Method 2: read default route from /proc/net/route (Linux hotspot)
        try:
            with open("/proc/net/route") as f:
                for line in f.readlines()[1:]:  # skip header
                    parts = line.strip().split()
                    if len(parts) >= 4 and parts[1] == "00000000":  # dest = 0.0.0.0
                        iface = parts[0]
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        try:
                            ifr = struct.pack("16sH14s", iface.encode()[:16],
                                              socket.AF_INET, b"\x00" * 14)
                            result = fcntl.ioctl(s.fileno(), 0x8915, ifr)
                            ip = socket.inet_ntoa(result[20:24])
                            if ip and not ip.startswith("127."):
                                return ip
                        except OSError:
                            pass
                        finally:
                            s.close()
        except Exception:
            pass

        # Method 3: prefer hotspot-like or private IPs from local list
        ips = NetworkManager._get_local_ips()
        for pref in ("10.42.", "10.0.", "192.168.", "10.", "172."):
            for ip in ips:
                if ip.startswith(pref):
                    return ip
        return ips[0] if ips else None

    @property
    def primary_ip(self) -> Optional[str]:
        return self._primary_ip

    @property
    def all_ips(self) -> List[str]:
        return self._all_ips

    @staticmethod
    def check_port_available(port: int, host="0.0.0.0") -> bool:
        """Check if a TCP port is available."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            s.close()
            return True
        except OSError:
            return False

    @staticmethod
    def find_free_port(start: int = 8080, max_attempts: int = 100) -> int:
        """Find a free port starting from `start`."""
        for port in range(start, start + max_attempts):
            if NetworkManager.check_port_available(port):
                return port
        return 0

    @property
    def network_info(self) -> str:
        self._refresh()
        if not self._all_ips or self._all_ips == ["127.0.0.1"]:
            return "未检测到网络连接"
        return f"IP: {self._primary_ip or '未知'}"
