import sys
import logging

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from .config import Config
from .ui.main_window import MainWindow


def setup_logging(config: Config):
    config.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = config.log_dir / "classroom-cast.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(str(log_file), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def create_app(argv=None) -> QApplication:
    if argv is None:
        argv = sys.argv

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(argv)
    app.setApplicationName(Config.APP_NAME)
    app.setApplicationVersion(Config.APP_VERSION)
    app.setOrganizationName(Config.ORGANIZATION)

    return app


def run():
    config = Config()
    setup_logging(config)

    app = create_app()
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec_())
