import qrcode
from io import BytesIO
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel


class QRWidget(QWidget):
    """Widget to display a QR code with connection info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._url: Optional[str] = None
        self._https_url: Optional[str] = None
        self._ip: Optional[str] = None
        self._port: Optional[int] = None

        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumSize(180, 200)
        self.setMaximumWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self._qr_label = QLabel(self)
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setMinimumSize(130, 130)
        layout.addWidget(self._qr_label)

        self._url_label = QLabel("", self)
        self._url_label.setAlignment(Qt.AlignCenter)
        self._url_label.setWordWrap(True)
        layout.addWidget(self._url_label)

        self._status_label = QLabel("", self)
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._update_styles()

    def _update_styles(self):
        self._url_label.setStyleSheet("""
            QLabel { color: #58a6ff; font-size: 11px;
                     background: transparent; padding: 1px; }
        """)
        self._status_label.setStyleSheet("""
            QLabel { color: #8b949e; font-size: 11px;
                     background: transparent; }
        """)

    def set_connection_info(self, ip: str, port: int, https_port: int = None,
                            public_host: str = ""):
        self._ip = ip
        self._port = port

        host = public_host if public_host else ip

        # QR encodes active protocol: HTTPS if SSL available, HTTP otherwise
        if https_port:
            self._url = f"https://{host}:{https_port}/cast"
            self._https_url = f"http://{ip}:{port}/cast" if not public_host else None
        else:
            self._url = f"http://{host}:{port}/cast"
            self._https_url = None

        self._generate_qr()
        self._update_labels()

    def _generate_qr(self):
        if not self._url:
            return

        try:
            qr = qrcode.QRCode(
                version=3,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=4,
                border=1,
            )
            qr.add_data(self._url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue(), "PNG")
            scaled = pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._qr_label.setPixmap(scaled)
        except Exception as e:
            self._qr_label.setText(f"二维码生成失败\n{str(e)}")

    def _update_labels(self):
        if self._https_url:
            self._url_label.setText(
                f"扫码: {self._url}\nHTTP备用: {self._https_url}"
            )
        else:
            self._url_label.setText(f"打开: {self._url}")

    def set_status(self, status: str):
        self._status_label.setText(status)

    def clear(self):
        self._qr_label.clear()
        self._url_label.setText("等待连接...")
        self._status_label.setText("")
        self._url = None
        self._https_url = None
