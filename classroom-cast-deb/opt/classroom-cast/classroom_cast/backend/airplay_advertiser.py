import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class AirPlayAdvertiser:
    """Advertise AirPlay service via mDNS so iOS devices can discover us.

    This is a lightweight mDNS advertisement only. It makes the device
    appear in iOS Screen Mirroring list. Actual AirPlay streaming requires
    Uxplay to be running alongside.
    """

    SERVICE_TYPE = "_airplay._tcp.local."
    SERVICE_NAME = "Classroom Cast"  # will appear in iOS list

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._service = None
        self._zeroconf = None

    def _get_txt_records(self) -> dict:
        """Return TXT records for AirPlay advertisement."""
        import hashlib

        # Generate a deterministic fake MAC from hostname
        hostname_id = hashlib.md5(self.SERVICE_NAME.encode()).digest()[:6]
        mac = ":".join(f"{b:02x}" for b in hostname_id)

        return {
            "txtvers": b"1",
            "deviceid": mac.encode(),
            "features": b"0x4A7FF7DC,0x80",
            "flags": b"0x4",
            "srcvers": b"220.68",
            "model": b"AppleTV3,2",
            "pi": mac.encode(),
            "pk": b"0000000000000000000000000000000000000000000000000000000000000000",
            "vv": b"2",
        }

    def start(self) -> bool:
        """Start mDNS advertisement in background."""
        if self._running:
            logger.info("AirPlay advertiser already running")
            return True

        try:
            # Try zeroconf first
            return self._start_with_zeroconf()
        except ImportError:
            logger.warning("zeroconf not installed, trying CLI fallback")
            return self._start_with_cli()

    def _start_with_zeroconf(self) -> bool:
        """Start using zeroconf library."""
        try:
            from zeroconf import Zeroconf, ServiceInfo
            import socket

            local_ip = self._get_local_ip()
            if not local_ip:
                logger.error("No network IP found")
                return False

            txt = self._get_txt_records()

            self._zeroconf = Zeroconf()
            self._service = ServiceInfo(
                type_=self.SERVICE_TYPE,
                name=f"{self.SERVICE_NAME}.{self.SERVICE_TYPE}",
                addresses=[socket.inet_aton(local_ip)],
                port=7000,  # AirPlay default port
                properties=txt,
                server=f"{self.SERVICE_NAME.replace(' ', '-')}.local.",
            )

            self._zeroconf.register_service(self._service)
            self._running = True
            logger.info("AirPlay mDNS advertised (zeroconf): %s on %s:7000",
                        self.SERVICE_NAME, local_ip)
            return True

        except Exception as e:
            logger.error("Failed to start zeroconf advertiser: %s", e)
            return False

    def _start_with_cli(self) -> bool:
        """Fallback: use system dns-sd or avahi-publish."""
        import subprocess
        import shutil

        dns_sd = shutil.which("dns-sd")
        avahi = shutil.which("avahi-publish")

        if dns_sd:
            txt = self._get_txt_records()
            txt_args = []
            for k, v in txt.items():
                txt_args.append(f"{k}={v.decode()}")

            self._process = subprocess.Popen(
                [dns_sd, "-R", self.SERVICE_NAME, "_airplay._tcp", "local",
                 "7000"] + txt_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._running = True
            logger.info("AirPlay mDNS advertised (dns-sd)")
            return True

        elif avahi:
            txt = self._get_txt_records()
            txt_args = []
            for k, v in txt.items():
                txt_args.append(f"{k}={v.decode()}")

            self._process = subprocess.Popen(
                [avahi, "-s", self.SERVICE_NAME, "_airplay._tcp", "7000"] + txt_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._running = True
            logger.info("AirPlay mDNS advertised (avahi)")
            return True

        else:
            logger.error("No mDNS tool found (need zeroconf, dns-sd, or avahi)")
            return False

    def stop(self):
        """Stop mDNS advertisement."""
        self._running = False

        if self._zeroconf and self._service:
            try:
                self._zeroconf.unregister_service(self._service)
                self._zeroconf.close()
            except Exception as e:
                logger.debug("Zeroconf cleanup: %s", e)
            self._zeroconf = None
            self._service = None

        if hasattr(self, '_process') and self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        logger.info("AirPlay mDNS advertisement stopped")

    @staticmethod
    def _get_local_ip() -> Optional[str]:
        """Get primary local IP address."""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)
            s.connect(("223.5.5.5", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip if not ip.startswith("127.") else None
        except Exception:
            return None

    def __del__(self):
        self.stop()
