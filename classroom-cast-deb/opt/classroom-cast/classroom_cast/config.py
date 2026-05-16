import json
import logging
from pathlib import Path


class Config:
    APP_NAME = "班级投屏"
    APP_VERSION = "1.0.0"
    ORGANIZATION = "ClassroomCast"

    DEFAULT_PORT = 8080
    DEFAULT_SSL_PORT = 8443
    MAX_CAST_CLIENTS = 1

    @property
    def config_dir(self) -> Path:
        return Path.home() / ".config" / "classroom-cast"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def log_dir(self) -> Path:
        return self.config_dir / "logs"

    def __init__(self):
        self.port = self.DEFAULT_PORT
        self.ssl_port = self.DEFAULT_SSL_PORT
        self.auto_start_web = True
        self.language = "zh_CN"
        self.public_host = ""  # e.g., "example.com" or public IP for internet access
        self._load()

    def _load(self):
        try:
            cfg_file = self.config_file
            if cfg_file.exists():
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                self.port = data.get("port", self.DEFAULT_PORT)
                self.ssl_port = data.get("ssl_port", self.DEFAULT_SSL_PORT)
                self.auto_start_web = data.get("auto_start_web", True)
                self.language = data.get("language", "zh_CN")
                self.public_host = data.get("public_host", "")
        except Exception as e:
            logging.getLogger(__name__).warning("Failed to load config: %s", e)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "port": self.port,
            "ssl_port": self.ssl_port,
            "auto_start_web": self.auto_start_web,
            "language": self.language,
            "public_host": self.public_host,
        }
        self.config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
