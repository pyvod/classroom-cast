import logging
import subprocess
import shutil
from typing import Optional

logger = logging.getLogger(__name__)


class MiracastManager:
    """Manage Miracast/WiFi-Display receiver using system tools."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._available = self._check_available()
        self._enabled = False

    def _check_available(self) -> bool:
        """Check if miracast tools are available on the system."""
        tools = ["miraclecast", "wpa_supplicant"]
        for tool in tools:
            if shutil.which(tool):
                logger.info("Found miracast tool: %s", tool)
                return True
        return False

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> bool:
        """Start miracast receiver."""
        if not self._available:
            logger.warning("No miracast tools available")
            return False

        if self._enabled:
            logger.info("Miracast already running")
            return True

        miraclecast_bin = shutil.which("miraclecast")
        if miraclecast_bin:
            try:
                self._process = subprocess.Popen(
                    [miraclecast_bin, "-s"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._enabled = True
                logger.info("Started miraclecast receiver")
                return True
            except FileNotFoundError:
                logger.warning("miraclecast binary not found, trying wpa_supplicant")

        try:
            self._process = subprocess.Popen(
                ["wpa_supplicant", "-B", "-Dnl80211,wext", "-iwlan0",
                 "-C/var/run/wpa_supplicant"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._enabled = True
            logger.info("Started wpa_supplicant for P2P")
            return True
        except FileNotFoundError:
            logger.error("Neither miraclecast nor wpa_supplicant available")
            self._available = False
            return False
        except Exception as e:
            logger.error("Failed to start miracast: %s", e)
            return False

    def stop(self):
        """Stop miracast receiver."""
        self._enabled = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None
            logger.info("Miracast stopped")

    @property
    def is_running(self) -> bool:
        return self._enabled
