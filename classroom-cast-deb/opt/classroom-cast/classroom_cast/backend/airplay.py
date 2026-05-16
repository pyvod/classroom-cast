import logging
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from .airplay_advertiser import AirPlayAdvertiser

logger = logging.getLogger(__name__)


class AirPlayManager:
    """Manage AirPlay receiver for iOS screen mirroring.

    On macOS: uses built-in AirPlay Receiver (System Settings → AirDrop & Handoff).
    On Linux: uses Uxplay for actual AirPlay protocol handling.
    Falls back to mDNS advertisement (via zeroconf) so iOS devices can at least
    discover the device in Screen Mirroring list.
    """

    UXPLAY_URL = "https://github.com/FDH2/Uxplay.git"
    UXPLAY_NAMES = ["run-uxplay", "uxplay", "Uxplay"]  # wrapper first, then binary

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._advertiser = AirPlayAdvertiser()
        self._is_macos = platform.system() == "Darwin"
        self._uxplay_binary: Optional[str] = None
        self._available = self._check_available()
        self._name = "班级投屏"
        self._status_callback = None
        self._enabled = False

    def _find_uxplay(self) -> Optional[str]:
        """Find Uxplay binary with either case."""
        for name in self.UXPLAY_NAMES:
            path = shutil.which(name)
            if path:
                return path
            for base in [
                "/usr/local/bin",
                "/usr/bin",
                "/opt/classroom-cast/uxplay-libs",
                "/opt/classroom-cast/bin",
                str(Path.home() / ".local" / "bin"),
                str(Path.home() / "Uxplay" / "build"),
            ]:
                p = Path(base) / name
                if p.exists():
                    return str(p)
        return None

    def _check_available(self) -> bool:
        """Check if AirPlay is available on this platform."""
        if self._is_macos:
            # macOS: Uxplay works, also has built-in AirPlay Receiver
            self._uxplay_binary = self._find_uxplay()
            return True
        # Linux: check for Uxplay binary
        self._uxplay_binary = self._find_uxplay()
        return self._uxplay_binary is not None

    def set_device_name(self, name: str):
        self._name = name
        self._advertiser.SERVICE_NAME = name

    def set_status_callback(self, callback):
        self._status_callback = callback

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_running(self) -> bool:
        return self._enabled

    def start(self) -> bool:
        """Start AirPlay service."""
        if self._enabled:
            return True
        if self._uxplay_binary:
            # UxPlay handles its own mDNS via Bonjour/avahi internally.
            # Starting our own advertiser alongside would create duplicate services.
            return self._start_uxplay()

        # Without UxPlay, use our mDNS advertiser (advertisement-only mode,
        # or macOS built-in AirPlay Receiver)
        self._notify_status("正在启动 mDNS 广播...")
        adv_ok = self._advertiser.start()
        if adv_ok:
            self._notify_status(f"已广播 AirPlay 服务 -> \"{self._name}\"")
        else:
            self._notify_status("mDNS 广播启动失败，请检查 zeroconf 安装")

        if self._is_macos:
            return self._start_macos_airplay(adv_ok)
        else:
            if adv_ok:
                self._enabled = True
                self._notify_status(
                    f"✓ 已广播 AirPlay 服务\n"
                    f"iPhone 控制中心 → 屏幕镜像可看到「{self._name}」\n"
                    f"(如需实际投屏请安装 Uxplay)"
                )
                return True
            return False

    def _start_macos_airplay(self, adv_ok: bool) -> bool:
        """Use macOS built-in AirPlay Receiver as fallback."""
        try:
            result = subprocess.run(
                ["defaults", "read", "/Library/Preferences/com.apple.AirPlayReceiver",
                 "AirPlayReceiverEnabled"],
                capture_output=True, text=True, timeout=3,
            )
            enabled = result.stdout.strip() == "1"
        except Exception:
            enabled = False

        self._enabled = True
        if enabled:
            self._notify_status(
                f"✓ AirPlay 已就绪\n"
                f"iPhone 控制中心 → 屏幕镜像 → 选择「{self._name}」"
            )
        else:
            self._notify_status(
                f"✓ mDNS 已广播「{self._name}」\n"
                f"请开启系统 AirPlay 接收器:\n"
                f"系统设置 → 通用 → 隔空投送与接力 →\n"
                f"打开「AirPlay 接收器」"
            )
        return True

    def _start_uxplay(self) -> bool:
        """Start the Uxplay process for actual AirPlay streaming."""
        binary = self._uxplay_binary
        if not binary:
            self._notify_status("Uxplay 未找到")
            return False

        try:
            args = [binary, "-n", self._name]
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.info("Uxplay started: %s -n %s", binary, self._name)
            self._enabled = True

            threading.Thread(
                target=self._monitor_output,
                args=(self._process,),
                daemon=True,
            ).start()

            self._notify_status(f"AirPlay 已启动（Uxplay + mDNS）")
            return True

        except Exception as e:
            logger.error("Failed to start Uxplay: %s", e)
            self._notify_status(f"Uxplay 启动失败: {e}")
            return False

    def stop(self):
        """Stop all AirPlay services."""
        self._enabled = False
        # Stop mDNS advertiser
        self._advertiser.stop()

        # Stop Uxplay
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        logger.info("AirPlay services stopped")
        self._notify_status("AirPlay 已停止")

    def _monitor_output(self, process: subprocess.Popen):
        import threading as _t

        def read_stream(stream, label):
            try:
                for line in iter(stream.readline, ""):
                    line = line.strip()
                    if line:
                        logger.debug("Uxplay %s: %s", label, line)
                        if any(w in line.lower() for w in ["error", "fail", "connect"]):
                            self._notify_status(f"AirPlay: {line[:60]}")
            except Exception:
                pass

        _t.Thread(target=read_stream, args=(process.stdout, "out"), daemon=True).start()
        _t.Thread(target=read_stream, args=(process.stderr, "err"), daemon=True).start()

    def _notify_status(self, msg: str):
        if self._status_callback:
            try:
                self._status_callback(msg)
            except Exception:
                pass

    @staticmethod
    def get_install_instructions() -> str:
        return """安装 Uxplay (AirPlay 接收器):

方法 1 - apt 安装（如可用）:
  sudo apt install uxplay

方法 2 - 源码编译:
  sudo apt install build-essential git cmake \\
    libavahi-compat-libdnssd-dev libssl-dev \\
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \\
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \\
    gstreamer1.0-plugins-ugly gstreamer1.0-libav

  git clone https://github.com/FDH2/Uxplay.git
  cd Uxplay
  mkdir build && cd build
  cmake ..
  make -j$(nproc)
  sudo make install
"""

    def __del__(self):
        self.stop()
