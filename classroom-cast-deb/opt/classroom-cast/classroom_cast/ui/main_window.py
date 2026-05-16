import asyncio
import logging
import webbrowser
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QMessageBox, QApplication, QScrollArea,
)

from .qr_widget import QRWidget
from .cast_view import CastView
from ..backend import NetworkManager, WebCastServer, MiracastManager, AirPlayManager, HotspotManager
from ..config import Config

logger = logging.getLogger(__name__)


class ServerThread(QThread):
    """Background thread running the aiohttp server with its own event loop."""

    frame_received = pyqtSignal(object)   # bytes (JPEG frame)
    photo_received = pyqtSignal(object, object)  # bytes data, str filename
    url_received = pyqtSignal(str)  # URL string
    server_error = pyqtSignal(str)
    server_ready = pyqtSignal(str)

    def __init__(self, port: int, ssl_port: int, parent=None):
        super().__init__(parent)
        self.port = port
        self.ssl_port = ssl_port
        self._server: Optional[WebCastServer] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_frame(self, data: bytes):
        self.frame_received.emit(data)

    def _on_photo(self, data: bytes, filename: str):
        self.photo_received.emit(data, filename)

    def _on_url(self, url: str):
        self.url_received.emit(url)

    def run(self):
        """Thread entry point: create event loop and start server."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def start():
            self._server = WebCastServer(
                on_frame_received=self._on_frame,
                on_photo_received=self._on_photo,
                on_url_received=self._on_url,
                host="0.0.0.0",
                port=self.port,
                ssl_port=self.ssl_port,
            )
            await self._server.start()
            self.server_ready.emit(f"Web 服务已启动 (端口 {self.port})")

        try:
            self._loop.run_until_complete(start())
            self._loop.run_forever()
        except Exception as e:
            self.server_error.emit(str(e))
            logger.exception("Server thread error")

    async def _stop_server(self):
        if self._server:
            await self._server.stop()
            self._server = None

    def stop(self):
        """Gracefully stop the server and event loop."""
        if self._loop and not self._loop.is_closed():
            fut = asyncio.run_coroutine_threadsafe(self._stop_server(), self._loop)
            try:
                fut.result(timeout=3)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def is_casting(self) -> bool:
        return self._server is not None and self._server.is_casting

    def disconnect_client(self):
        """Tell the phone it has been disconnected by the big screen."""
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self._server.disconnect_client(), self._loop
            )

    def wait_stopped(self, timeout: int = 3):
        self.wait(timeout * 1000)


class MainWindow(QMainWindow):
    """Main window for the classroom casting application."""

    def __init__(self, config: Config):
        super().__init__()
        self._config = config
        self._net_mgr = NetworkManager()
        self._miracast = MiracastManager()
        self._airplay = AirPlayManager()
        self._airplay.set_device_name("班级投屏")
        self._airplay.set_status_callback(self._on_airplay_status)
        self._hotspot = HotspotManager()
        self._hotspot.set_status_callback(self._on_hotspot_status)
        self._wanted_hotspot = False  # True while waiting for macOS user to enable sharing
        self._server_thread: Optional[ServerThread] = None
        self._frame_count = 0

        self._setup_ui()
        self._setup_style()
        self._setup_timers()
        self._start_server()

    def _setup_ui(self):
        self.setWindowTitle(self._config.APP_NAME)
        self.setMinimumSize(1024, 600)
        self.showMaximized()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Top bar ---
        self._top_bar = QFrame()
        self._top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(self._top_bar)
        top_layout.setContentsMargins(24, 12, 24, 12)

        title = QLabel("班级投屏系统")
        title.setObjectName("windowTitle")
        top_layout.addWidget(title)

        top_layout.addStretch()

        self._status_icon = QLabel("●")
        self._status_icon.setObjectName("statusIcon")
        top_layout.addWidget(self._status_icon)

        self._status_label = QLabel("启动中...")
        self._status_label.setObjectName("statusLabel")
        top_layout.addWidget(self._status_label)

        self._network_label = QLabel()
        self._network_label.setObjectName("networkLabel")
        top_layout.addWidget(self._network_label)

        self._btn_exit = QPushButton("退出")
        self._btn_exit.setObjectName("settingsBtn")
        self._btn_exit.clicked.connect(self.close)
        top_layout.addWidget(self._btn_exit)

        main_layout.addWidget(self._top_bar)

        # --- Content area ---
        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left: cast view (main display area)
        self._cast_view = CastView()
        content_layout.addWidget(self._cast_view, 1)

        # Right sidebar with scroll
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(340)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        sidebar_layout.addWidget(scroll)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(16, 20, 16, 20)
        scroll_layout.setSpacing(10)

        scroll_title = QLabel("投屏方式")
        scroll_title.setObjectName("sidebarTitle")
        scroll_layout.addWidget(scroll_title)

        # QR code section
        qr_section = QFrame()
        qr_section.setObjectName("qrSection")
        qr_section.setMinimumHeight(260)
        qr_layout = QVBoxLayout(qr_section)
        qr_layout.setContentsMargins(4, 6, 4, 6)
        qr_layout.setSpacing(6)
        qr_layout.setAlignment(Qt.AlignCenter)

        self._qr_widget = QRWidget()
        qr_layout.addWidget(self._qr_widget, 0, Qt.AlignCenter)

        btn_refresh_qr = QPushButton("刷新二维码")
        btn_refresh_qr.setObjectName("refreshBtn")
        btn_refresh_qr.setStyleSheet(
            "QPushButton { background: #1f6feb; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 8px 20px; font-size: 14px; min-width: 120px; }"
            "QPushButton:hover { background: #388bfd; }"
        )
        btn_refresh_qr.clicked.connect(self._refresh_qr)
        qr_layout.addWidget(btn_refresh_qr)

        scroll_layout.addWidget(qr_section)

        # Methods section
        methods_frame = QFrame()
        methods_frame.setObjectName("methodsFrame")
        methods_layout = QVBoxLayout(methods_frame)
        methods_layout.setContentsMargins(0, 0, 0, 0)
        methods_layout.setSpacing(10)

        methods_title = QLabel("其他方式")
        methods_title.setObjectName("sidebarTitle")
        methods_layout.addWidget(methods_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_miracast = QPushButton("📱 安卓投屏")
        self._btn_miracast.setObjectName("methodBtn")
        self._btn_miracast.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 6px; padding: 10px 8px; font-size: 13px; }"
            "QPushButton:hover { background: #30363d; border-color: #58a6ff; }"
            "QPushButton:disabled { color: #484f58; background: #161b22; }"
        )
        self._btn_miracast.clicked.connect(self._toggle_miracast)
        self._btn_miracast.setEnabled(self._miracast.available)
        self._btn_miracast.setToolTip(
            "安卓手机请使用「班级投屏」APK 客户端\n"
            "连接热点后浏览器打开大屏 IP 下载"
        )
        btn_row.addWidget(self._btn_miracast)

        self._btn_airplay = QPushButton("📲 苹果投屏")
        self._btn_airplay.setObjectName("methodBtn")
        self._btn_airplay.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 6px; padding: 10px 8px; font-size: 13px; }"
            "QPushButton:hover { background: #30363d; border-color: #58a6ff; }"
            "QPushButton:disabled { color: #484f58; background: #161b22; }"
        )
        self._btn_airplay.clicked.connect(self._toggle_airplay)
        self._btn_airplay.setToolTip(
            "需要安装 Uxplay\n"
            "iPhone 控制中心 → 屏幕镜像 → 选择「班级投屏」"
        )
        btn_row.addWidget(self._btn_airplay)

        methods_layout.addLayout(btn_row)

        # WiFi hotspot section
        hotspot_frame = QFrame()
        hotspot_frame.setObjectName("qrSection")
        hotspot_layout = QVBoxLayout(hotspot_frame)

        self._btn_hotspot = QPushButton("WiFi 热点")
        self._btn_hotspot.setObjectName("methodBtn")
        self._btn_hotspot.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 6px; padding: 10px 8px; font-size: 14px; }"
            "QPushButton:hover { background: #30363d; border-color: #58a6ff; }"
        )
        self._btn_hotspot.clicked.connect(self._toggle_hotspot)
        self._btn_hotspot.setEnabled(self._hotspot.available)
        hotspot_layout.addWidget(self._btn_hotspot)

        self._hotspot_info = QLabel("")
        self._hotspot_info.setObjectName("deviceLabel")
        self._hotspot_info.setWordWrap(True)
        self._hotspot_info.setAlignment(Qt.AlignCenter)
        hotspot_layout.addWidget(self._hotspot_info)

        self._hotspot_clients = QLabel("")
        self._hotspot_clients.setObjectName("deviceLabel")
        self._hotspot_clients.setAlignment(Qt.AlignCenter)
        hotspot_layout.addWidget(self._hotspot_clients)

        methods_layout.addWidget(hotspot_frame)
        scroll_layout.addWidget(methods_frame)

        scroll_layout.addStretch()

        # Status section
        status_frame = QFrame()
        status_frame.setObjectName("qrSection")
        status_layout = QVBoxLayout(status_frame)

        self._device_label = QLabel("📡 已连接设备: 无")
        self._device_label.setObjectName("deviceLabel")
        status_layout.addWidget(self._device_label)

        self._fps_label = QLabel("")
        self._fps_label.setObjectName("deviceLabel")
        status_layout.addWidget(self._fps_label)

        btn_disconnect = QPushButton("断开连接")
        btn_disconnect.setObjectName("disconnectBtn")
        btn_disconnect.clicked.connect(self._disconnect)
        status_layout.addWidget(btn_disconnect)

        scroll_layout.addWidget(status_frame)

        scroll.setWidget(scroll_content)
        content_layout.addWidget(sidebar)
        main_layout.addWidget(content, 1)

        # --- Bottom status bar ---
        self._bottom_bar = QFrame()
        self._bottom_bar.setObjectName("bottomBar")
        bottom_layout = QHBoxLayout(self._bottom_bar)
        bottom_layout.setContentsMargins(16, 4, 16, 4)

        self._bottom_status = QLabel("系统就绪 | 等待投屏连接")
        self._bottom_status.setObjectName("bottomStatus")
        bottom_layout.addWidget(self._bottom_status)

        bottom_layout.addStretch()

        main_layout.addWidget(self._bottom_bar)

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0d1117;
                color: #c9d1d9;
                font-family: "Noto Sans CJK SC", "Microsoft YaHei", "Source Han Sans", sans-serif;
            }
            #topBar {
                background-color: #161b22;
                border-bottom: 1px solid #30363d;
                min-height: 56px;
            }
            #windowTitle {
                font-size: 22px;
                font-weight: bold;
                color: #f0f6fc;
            }
            #statusIcon { color: #3fb950; font-size: 14px; }
            #statusLabel { color: #8b949e; font-size: 14px; }
            #networkLabel {
                color: #58a6ff; font-size: 13px; padding: 4px 12px;
                background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
            }
            #settingsBtn {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 6px; padding: 6px 20px; font-size: 13px;
            }
            #settingsBtn:hover { background: #30363d; }
            #sidebar {
                background-color: #161b22;
                border-left: 1px solid #30363d;
            }
            #sidebarTitle {
                font-size: 16px; font-weight: bold; color: #f0f6fc; padding: 8px 0 4px 0;
            }
            #qrSection {
                background: #0d1117; border: 1px solid #30363d;
                border-radius: 8px;
            }
            #qrTitle {
                font-size: 15px; font-weight: bold; color: #f0f6fc; padding: 4px;
            }
            #refreshBtn {
                background: #1f6feb; color: #ffffff; border: none; border-radius: 6px;
                padding: 8px 20px; font-size: 14px; min-width: 120px;
            }
            #refreshBtn:hover { background: #388bfd; }
            #methodBtn {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 6px; padding: 10px 16px; font-size: 14px; text-align: left;
            }
            #methodBtn:hover { background: #30363d; border-color: #58a6ff; }
            #methodBtn:disabled { color: #484f58; background: #161b22; }
            #deviceLabel { color: #8b949e; font-size: 13px; padding: 2px 0; }
            #disconnectBtn {
                background: #21262d; color: #f85149; border: 1px solid #f85149;
                border-radius: 6px; padding: 8px 16px; font-size: 14px;
            }
            #disconnectBtn:hover { background: #f85149; color: #ffffff; }
            #bottomBar {
                background-color: #161b22; border-top: 1px solid #30363d; min-height: 32px;
            }
            #bottomStatus { color: #8b949e; font-size: 12px; }
        """)

    def _setup_timers(self):
        # Periodically update network info
        self._net_timer = QTimer(self)
        self._net_timer.timeout.connect(self._update_network_info)
        self._net_timer.start(5000)

        # Check casting timeout
        self._timeout_timer = QTimer(self)
        self._timeout_timer.timeout.connect(self._check_cast_status)
        self._timeout_timer.start(2000)

    def _start_server(self):
        """Start the web casting server in a background thread."""
        port = self._config.port
        ssl_port = self._config.ssl_port
        nm = NetworkManager()

        # Find an available port if the default is busy
        if not nm.check_port_available(port):
            port = nm.find_free_port(port)
            if port == 0:
                self._update_status("错误: 无法找到可用端口，请检查网络", error=True)
                return

        # Update QR code with connection info
        ip = nm.primary_ip or "未知"
        public_host = self._config.public_host
        display_ip = public_host if public_host else ip
        self._network_label.setText(f"IP: {display_ip}")
        self._qr_widget.set_connection_info(ip, port, ssl_port, public_host)

        # Start server in background thread
        self._server_thread = ServerThread(port, ssl_port)
        self._server_thread.frame_received.connect(self._on_frame_received)
        self._server_thread.photo_received.connect(self._on_photo_received)
        self._server_thread.url_received.connect(self._on_url_received)
        self._server_thread.server_error.connect(lambda e: self._update_status(f"服务器错误: {e}", error=True))
        self._server_thread.server_ready.connect(lambda m: self._update_status(m))
        self._server_thread.start()

        self._update_status(f"服务启动中... (端口 {port})")

    def _on_frame_received(self, jpeg_data: bytes):
        """Slot called from the server thread via signal when a frame arrives."""
        self._cast_view.show_frame(jpeg_data)
        self._frame_count += 1
        if self._frame_count < 5:
            self._update_status("投屏已连接，正在接收画面...")
            self._device_label.setText("📡 已连接设备: 1")

    def _on_photo_received(self, data: bytes, filename: str):
        """Add a received photo to the gallery and display it."""
        self._cast_view.add_photo(data, filename)
        count = self._cast_view.photo_count
        self._update_status(f"📷 照片已接收 ({count}张): {filename}")
        self._device_label.setText(f"📷 照片模式 ({count}张)")

    def _on_url_received(self, url: str):
        """Handle a URL pushed from the phone - open in system browser."""
        self._update_status(f"🌐 收到网址: {url}")
        webbrowser.open(url)
        logger.info("Opening URL: %s", url)

    def _refresh_qr(self):
        """Refresh the QR code display."""
        if self._hotspot.is_running:
            self._update_qr_with_hotspot()
            self._update_status("二维码已刷新")
            return
        nm = NetworkManager()
        ip = nm.primary_ip or "localhost"
        port = self._config.port
        public_host = self._config.public_host
        display_ip = public_host if public_host else ip
        self._qr_widget.set_connection_info(ip, port, self._config.ssl_port, public_host)
        self._network_label.setText(f"IP: {display_ip}")
        self._update_status("二维码已刷新")

    def _toggle_miracast(self):
        """Toggle Miracast receiver — or guide user to use Android APK."""
        # If Miracast tools aren't available, guide to APK
        if not self._miracast.available:
            self._show_android_apk_guide()
            return

        if self._miracast.is_running:
            self._miracast.stop()
            self._btn_miracast.setText("📱 安卓投屏")
            self._btn_miracast.setStyleSheet("")
            self._update_status("Miracast 已停止")
        else:
            ok = self._miracast.start()
            if ok:
                self._btn_miracast.setText("⏹ 停止安卓投屏")
                self._btn_miracast.setStyleSheet(
                    "background: #1f6feb; color: white; border: none; border-radius: 6px;"
                )
                self._update_status("Miracast 已启动，等待安卓设备连接...")
            else:
                self._update_status("Miracast 启动失败（需要系统组件支持）", error=True)

    def _show_android_apk_guide(self):
        """Show guide for using the Android APK client."""
        from .network import NetworkManager
        nm = NetworkManager()
        ip = nm.primary_ip or "localhost"
        port = self._config.port
        msg = (
            "安卓手机投屏方式：\n\n"
            "1. 确保手机连接到教室 WiFi 或大屏热点\n"
            f"2. 在手机浏览器打开 http://{ip}:{port} 下载\n"
            "   或直接安装「班级投屏」APK\n"
            "3. 打开 APK，扫码或输入大屏 IP 连接\n"
            "4. 选择「屏幕镜像」即可投屏\n\n"
            "注意：Android 系统自带的「无线投屏」\n"
            "使用 Miracast 协议，与本系统不兼容。\n"
            "请使用专用的「班级投屏」APK。"
        )
        QMessageBox.information(self, "📱 安卓投屏说明", msg)

    def _toggle_airplay(self):
        """Toggle AirPlay receiver (advertiser + Uxplay if available)."""
        if self._airplay.is_running:
            self._airplay.stop()
            self._btn_airplay.setText("📲 苹果投屏")
            self._btn_airplay.setStyleSheet("")
            self._update_status("AirPlay 已停止")
            return

        # Start AirPlay (always starts mDNS advertiser, plus Uxplay if installed)
        ok = self._airplay.start()
        if ok:
            self._btn_airplay.setText("⏹ 停止苹果投屏")
            self._btn_airplay.setStyleSheet(
                "background: #1f6feb; color: white; border: none; border-radius: 6px;"
            )
            if self._airplay.available:
                self._update_status(
                    "AirPlay 已启动！\n"
                    "iPhone 控制中心 → 屏幕镜像 → 选择「班级投屏」"
                )
            else:
                self._update_status(
                    "✓ mDNS 广播已启动\n"
                    "iPhone 应能看到「班级投屏」\n"
                    "如需实际投屏，请安装 Uxplay"
                )
        else:
            self._show_airplay_install()

    def _on_airplay_status(self, msg: str):
        """Called from AirPlayManager with status updates."""
        self._update_status(msg)

    def _toggle_hotspot(self):
        """Toggle WiFi hotspot."""
        if self._hotspot.is_running:
            self._hotspot.stop()
            self._btn_hotspot.setText("WiFi 热点")
            self._btn_hotspot.setStyleSheet("")
            self._hotspot_info.setText("")
            self._hotspot_clients.setText("")
            self._wanted_hotspot = False
            self._refresh_qr()
            self._update_status("热点已关闭")
        else:
            ok = self._hotspot.start()
            if ok:
                self._btn_hotspot.setText("关闭热点")
                self._btn_hotspot.setStyleSheet(
                    "background: #1f6feb; color: white; border: none; border-radius: 6px;"
                )
                self._hotspot_info.setText(
                    f"WiFi: {self._hotspot.ssid}\n密码: {self._hotspot.password}"
                )
                self._update_qr_with_hotspot()
                self._wanted_hotspot = False
                self._update_status(f"热点已开启: {self._hotspot.ssid}")
            else:
                # On macOS, keep watching for manual Internet Sharing activation
                self._wanted_hotspot = True
                self._hotspot_info.setText(
                    f"WiFi: {self._hotspot.ssid}\n密码: {self._hotspot.password}"
                )
                self._update_status("热点启动失败，请在系统设置中开启互联网共享", error=True)

    def _on_hotspot_status(self, msg: str):
        """Called from HotspotManager with status updates."""
        self._update_status(msg)

    def _update_qr_with_hotspot(self):
        """Update QR code to use hotspot IP."""
        ip = self._hotspot.hotspot_ip or "10.42.0.1"
        port = self._config.port
        public_host = self._config.public_host
        self._qr_widget.set_connection_info(ip, port, self._config.ssl_port, public_host)
        self._network_label.setText(f"热点 IP: {ip}")

    def _show_airplay_install(self):
        """Show installation instructions for Uxplay."""
        msg = AirPlayManager.get_install_instructions()
        QMessageBox.information(self, "安装 Uxplay (AirPlay 接收器)", msg)

    def _disconnect(self):
        """Disconnect current casting session."""
        # Notify the phone that it has been disconnected
        if self._server_thread and self._server_thread.is_casting:
            self._server_thread.disconnect_client()
        self._cast_view.reset()
        self._frame_count = 0
        self._device_label.setText("📡 已连接设备: 无")
        self._update_status("已断开连接")

    def _update_network_info(self):
        """Periodically update network info."""
        # If waiting for user to enable Internet Sharing on macOS, check for it
        if self._wanted_hotspot and self._hotspot.detect_active():
            self._wanted_hotspot = False
            self._btn_hotspot.setText("关闭热点")
            self._btn_hotspot.setStyleSheet(
                "background: #1f6feb; color: white; border: none; border-radius: 6px;"
            )
            self._update_qr_with_hotspot()
            self._update_status(f"热点已开启: {self._hotspot.ssid}")
            self._on_hotspot_status(
                f"WiFi: {self._hotspot.ssid}  密码: {self._hotspot.password}"
            )

        if self._hotspot.is_running:
            clients = self._hotspot.count_clients()
            self._hotspot_clients.setText(f"已连接设备: {clients}")
            return
        nm = NetworkManager()
        ip = nm.primary_ip
        if ip:
            self._network_label.setText(f"IP: {ip}")

    def _check_cast_status(self):
        """Periodically check if casting is still active."""
        # Don't clear the display if we're in photo mode
        if self._cast_view.is_photo_mode:
            return

        if self._server_thread:
            casting = self._server_thread.is_casting
            if not casting and self._frame_count > 0:
                self._cast_view.show_no_signal()
                self._device_label.setText("📡 已连接设备: 无")
                self._frame_count = 0
                self._status_icon.setStyleSheet("color: #8b949e; font-size: 14px;")
                self._bottom_status.setText("等待投屏连接")

    def _update_status(self, msg: str, error: bool = False):
        self._bottom_status.setText(msg)
        if error:
            self._status_label.setText("错误")
            self._status_icon.setStyleSheet("color: #f85149; font-size: 14px;")
        else:
            self._status_label.setText(msg[:50])
            self._status_icon.setStyleSheet("color: #3fb950; font-size: 14px;")

    def closeEvent(self, event):
        """Clean up on close."""
        self._net_timer.stop()
        self._timeout_timer.stop()

        if self._miracast:
            self._miracast.stop()
        if self._airplay:
            self._airplay.stop()
        if self._hotspot:
            self._hotspot.stop()
        if self._server_thread:
            self._server_thread.stop()
            self._server_thread.wait_stopped()

        event.accept()
