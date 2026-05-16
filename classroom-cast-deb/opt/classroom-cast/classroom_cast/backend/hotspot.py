import logging
import platform
import random
import string
import subprocess
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class HotspotManager:
    """Manage WiFi hotspot for direct phone connection.

    Linux:  Uses nmcli (NetworkManager) to create/start/stop a WiFi AP.
    macOS:  Uses CoreWLAN via pyobjc (requires admin privileges).
            Falls back to enabling Internet Sharing via system commands.

    When active, phones connect directly to the classroom machine's WiFi,
    bypassing any VLAN/network restrictions.

    Linux hotspot IP:  10.42.0.1 (NetworkManager shared mode)
    macOS hotspot IP:  10.0.2.1 (Internet Sharing default)
    """

    CONNECTION_NAME = "classroom-cast-hotspot"

    def __init__(self):
        self.ssid = ""
        self.password = ""
        self.is_running = False
        self.hotspot_ip = ""
        self.interface = ""
        self._monitor_thread: Optional[threading.Thread] = None
        self._status_callback: Optional[Callable] = None
        self._platform = platform.system()
        self._detected = self._detect_wifi()

    def set_status_callback(self, callback):
        self._status_callback = callback

    def _notify(self, msg: str):
        if self._status_callback:
            try:
                self._status_callback(msg)
            except Exception:
                pass

    def _detect_wifi(self) -> bool:
        """Detect WiFi interface. Works on Linux (nmcli) and macOS."""
        if self._platform == "Linux":
            return self._detect_wifi_linux()
        elif self._platform == "Darwin":
            return self._detect_wifi_macos()
        return False

    def _detect_wifi_linux(self) -> bool:
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "TYPE,DEVICE", "dev", "status"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                parts = line.split(":")
                if len(parts) == 2 and parts[0] == "wifi":
                    self.interface = parts[1]
                    logger.info("Detected WiFi interface: %s", self.interface)
                    return True
        except FileNotFoundError:
            logger.warning("nmcli not found, hotspot unavailable")
        except Exception as e:
            logger.warning("WiFi detection failed: %s", e)
        return False

    def _detect_wifi_macos(self) -> bool:
        try:
            result = subprocess.run(
                ["networksetup", "-listallhardwareports"],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.split("\n")
            for i, line in enumerate(lines):
                if "Wi-Fi" in line or "AirPort" in line:
                    if i + 1 < len(lines) and "Device:" in lines[i + 1]:
                        self.interface = lines[i + 1].split("Device:")[1].strip()
                        logger.info("Detected WiFi interface: %s", self.interface)
                        return True
        except Exception as e:
            logger.warning("WiFi detection failed on macOS: %s", e)
        return False

    @property
    def available(self) -> bool:
        return self._detected

    def set_ssid(self, name: str):
        self.ssid = name

    def _generate_password(self, length=8) -> str:
        return "".join(random.choices(string.digits, k=length))

    def start(self, ssid: str = "", password: str = "") -> bool:
        if not self._detected:
            self._notify("未检测到 WiFi 网卡")
            return False

        self.ssid = ssid or self.ssid or "班级投屏"
        self.password = password or self._generate_password()

        if self._platform == "Linux":
            return self._start_linux()
        elif self._platform == "Darwin":
            return self._start_macos()
        else:
            self._notify(f"不支持的操作系统: {self._platform}")
            return False

    def _start_linux(self) -> bool:
        """Start hotspot on Linux using nmcli."""
        try:
            subprocess.run(
                ["nmcli", "con", "delete", self.CONNECTION_NAME],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["nmcli", "con", "add", "type", "wifi",
                 "ifname", self.interface,
                 "con-name", self.CONNECTION_NAME,
                 "ssid", self.ssid],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["nmcli", "con", "modify", self.CONNECTION_NAME,
                 "802-11-wireless.mode", "ap",
                 "802-11-wireless.band", "bg",
                 "ipv4.method", "shared"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["nmcli", "con", "modify", self.CONNECTION_NAME,
                 "wifi-sec.key-mgmt", "wpa-psk",
                 "wifi-sec.psk", self.password],
                capture_output=True, timeout=5,
            )
            result = subprocess.run(
                ["nmcli", "con", "up", self.CONNECTION_NAME],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                self._notify(f"热点启动失败: {result.stderr.strip()}")
                return False

            time.sleep(2)
            self._detect_ip_linux()
            self.is_running = True
            logger.info("Hotspot started: SSID=%s IP=%s", self.ssid, self.hotspot_ip)
            self._notify_status()
            return True

        except FileNotFoundError:
            self._notify("nmcli 未安装，请安装 NetworkManager")
            return False
        except Exception as e:
            logger.error("Hotspot start failed: %s", e)
            self._notify(f"热点启动失败: {e}")
            return False

    def _start_macos(self) -> bool:
        """Start hotspot on macOS using CoreWLAN + Internet Sharing."""
        # Try CoreWLAN first
        if self._start_macos_corewlan():
            self.is_running = True
            self._notify_status()
            return True

        # Fallback: try enabling Internet Sharing via shell commands
        if self._start_macos_sharing():
            self.is_running = True
            self._notify_status()
            return True

        # Last resort: open System Settings for user
        self._notify(
            "macOS 上创建热点需要启用「互联网共享」\n"
            "请在打开的设置中开启互联网共享并选择 Wi-Fi"
        )
        self._open_sharing_settings()
        return False

    def _start_macos_corewlan(self) -> bool:
        """Attempt to start HostAP via CoreWLAN."""
        try:
            import CoreWLAN
            import Foundation
            import objc
        except ImportError:
            logger.warning("CoreWLAN not available on macOS")
            return False

        try:
            client = CoreWLAN.CWWiFiClient.sharedWiFiClient()
            iface = client.interface()

            # Disassociate from current network
            iface.disassociate()
            time.sleep(0.5)

            # Set static IP
            subprocess.run(
                ["ifconfig", self.interface, "inet", "10.42.0.1",
                 "netmask", "255.255.255.0", "alias"],
                capture_output=True, timeout=5,
            )

            # Enable HostAP mode
            iface.enableHostAPMode()
            time.sleep(0.5)

            # Start HostAP with SSID and password via NSData
            ssid_bytes = self.ssid.encode("utf-8")
            ssid_data = Foundation.NSData.dataWithBytes_length_(
                ssid_bytes, len(ssid_bytes)
            )
            success, error = iface.startHostAPModeWithSSID_securityType_channel_password_error_(
                ssid_data,
                CoreWLAN.kCWSecurityWPA2Personal,
                None,  # auto channel
                self.password,
                None,
            )
            if success:
                self.hotspot_ip = "10.42.0.1"
                logger.info("CoreWLAN HostAP started successfully")
                return True

            if error:
                logger.warning("CoreWLAN HostAP failed: %s", error.localizedDescription())
                # Clean up IP alias on failure
                subprocess.run(
                    ["ifconfig", self.interface, "inet", "10.42.0.1", "-alias"],
                    capture_output=True, timeout=5,
                )
            return False
        except Exception as e:
            logger.warning("CoreWLAN exception: %s", e)
            return False

    def _start_macos_sharing(self) -> bool:
        """Enable Internet Sharing on macOS via system commands."""
        primary_iface = self._get_primary_iface_macos()
        if not primary_iface:
            logger.warning("No primary Ethernet interface found for Internet Sharing")
            return False

        # Create NAT configuration via osascript with admin rights
        script = (
            'do shell script "'
            f'defaults write /Library/Preferences/SystemConfiguration/com.apple.nat '
            f'NAT -dict-add PrimaryInterface {primary_iface} ; '
            f'defaults write /Library/Preferences/SystemConfiguration/com.apple.nat '
            f'NAT -dict-add AirPortDevice {self.interface} ; '
            f'defaults write /Library/Preferences/SystemConfiguration/com.apple.nat '
            f'NAT -dict-add SharingNetworkNumberStart 10.0.0.0 ; '
            f'defaults write /Library/Preferences/SystemConfiguration/com.apple.nat '
            f'NAT -dict-add SharingNetworkNumberEnd 10.0.255.255 ; '
            f'defaults write /Library/Preferences/SystemConfiguration/com.apple.nat '
            f'NAT -dict-add SharingNetworkMask 255.255.0.0 ; '
            f'killall sharingd 2>/dev/null ; '
            f'sleep 3 ; '
            f'echo done'
            '" with administrator privileges'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.warning("Failed to configure Internet Sharing: %s", result.stderr)
                return False
        except subprocess.TimeoutExpired:
            logger.warning("Admin auth timed out for Internet Sharing config")
            return False
        except Exception as e:
            logger.warning("Internet Sharing enable failed: %s", e)
            return False

        # Verify hotspot is actually running by checking interface IP
        time.sleep(2)
        self._detect_ip_macos()
        if not self.hotspot_ip:
            logger.warning("Internet Sharing configured but no hotspot IP detected")
            self._cleanup_nat_config()
            return False

        logger.info("Internet Sharing enabled, IP: %s", self.hotspot_ip)
        return True

    def _cleanup_nat_config(self):
        """Remove NAT config on macOS."""
        try:
            script = (
                'do shell script "'
                'defaults delete /Library/Preferences/SystemConfiguration/com.apple.nat '
                'NAT 2>/dev/null ; '
                'killall sharingd 2>/dev/null'
                '" with administrator privileges'
            )
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    def _get_primary_iface_macos(self) -> Optional[str]:
        """Find the primary Ethernet interface (not WiFi) for NAT sharing source."""
        try:
            result = subprocess.run(
                ["networksetup", "-listallhardwareports"],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.split("\n")
            for i, line in enumerate(lines):
                # Skip Wi-Fi, Thunderbolt, Bluetooth
                if "Wi-Fi" in line or "AirPort" in line or "Thunderbolt" in line or "Bluetooth" in line:
                    continue
                if "Ethernet" in line:
                    if i + 1 < len(lines) and "Device:" in lines[i + 1]:
                        dev = lines[i + 1].split("Device:")[1].strip()
                        # Check if the interface actually exists and is active
                        check = subprocess.run(
                            ["ifconfig", dev], capture_output=True, text=True, timeout=3,
                        )
                        if check.returncode == 0 and "status: active" in check.stdout:
                            return dev
        except Exception as e:
            logger.warning("Failed to get primary interface: %s", e)
        return None

    def _open_sharing_settings(self):
        """Open System Settings to Internet Sharing pane."""
        try:
            subprocess.run(
                ["open", "x-apple.systempreferences:com.apple.Internet-Sharing-Settings.extension"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

    def _detect_ip_linux(self):
        """Detect hotspot IP on Linux."""
        try:
            ip_result = subprocess.run(
                ["ip", "-4", "addr", "show", self.interface],
                capture_output=True, text=True, timeout=5,
            )
            for line in ip_result.stdout.split("\n"):
                if "inet " in line:
                    self.hotspot_ip = line.strip().split()[1].split("/")[0]
                    return
        except Exception:
            pass
        self.hotspot_ip = "10.42.0.1"

    def _detect_ip_macos(self):
        """Detect hotspot IP on macOS. Check interface is actually active."""
        try:
            result = subprocess.run(
                ["ifconfig", self.interface],
                capture_output=True, text=True, timeout=5,
            )
            # First verify interface is active
            if "status: active" not in result.stdout:
                logger.debug("WiFi interface not active")
                return

            for line in result.stdout.split("\n"):
                if "inet " in line:
                    parts = line.strip().split()
                    ip = parts[1]
                    if ip.startswith("10.") and ip != "127.0.0.1":
                        self.hotspot_ip = ip
                        return
        except Exception:
            pass

    def _notify_status(self):
        self._notify(
            f"热点已开启\n"
            f"WiFi: {self.ssid}\n"
            f"密码: {self.password}\n"
            f"连接后扫码地址: {self.hotspot_ip}"
        )

    def stop(self):
        """Stop WiFi hotspot."""
        if not self.is_running:
            return

        if self._platform == "Linux":
            self._stop_linux()
        elif self._platform == "Darwin":
            self._stop_macos()

        self.is_running = False
        self.hotspot_ip = ""
        logger.info("Hotspot stopped")
        self._notify("热点已关闭")

    def _stop_linux(self):
        try:
            subprocess.run(
                ["nmcli", "con", "down", self.CONNECTION_NAME],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["nmcli", "con", "delete", self.CONNECTION_NAME],
                capture_output=True, timeout=5,
            )
        except Exception as e:
            logger.warning("Hotspot stop error: %s", e)

    def _stop_macos(self):
        """Stop hotspot on macOS."""
        # Try CoreWLAN cleanup
        try:
            import CoreWLAN
            client = CoreWLAN.CWWiFiClient.sharedWiFiClient()
            iface = client.interface()
            iface.stopHostAPMode()
            iface.disableHostAPMode()
            subprocess.run(
                ["ifconfig", self.interface, "inet", "10.42.0.1", "-alias"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

        self._cleanup_nat_config()

    def count_clients(self) -> int:
        """Count connected clients via ARP table."""
        try:
            if not self.hotspot_ip:
                return 0
            result = subprocess.run(
                ["arp", "-n"],
                capture_output=True, text=True, timeout=5,
            )
            subnet = ".".join(self.hotspot_ip.split(".")[:3])
            count = sum(1 for line in result.stdout.split("\n")
                       if line.strip().startswith(subnet + "."))
            return count
        except Exception:
            return 0

    def detect_active(self) -> bool:
        """Detect if hotspot/Internet Sharing is already active (macOS).

        Useful when user manually enables Internet Sharing after we opened Settings.
        On Linux, returns current is_running state since nmcli is deterministic.
        """
        if self._platform == "Darwin" and not self.is_running:
            self._detect_ip_macos()
            if self.hotspot_ip:
                self.is_running = True
                logger.info("Detected active Internet Sharing at %s", self.hotspot_ip)
                return True
            return False
        return self.is_running

    def __del__(self):
        self.stop()
