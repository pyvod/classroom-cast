from io import BytesIO
import logging

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QWheelEvent
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QStackedWidget, QHBoxLayout,
    QPushButton, QSizePolicy, QFrame, QGraphicsView, QGraphicsScene,
)


def _correct_orientation(image_data: bytes) -> bytes:
    """Correct image orientation based on EXIF data using Pillow."""
    try:
        from PIL import Image
        img = Image.open(BytesIO(image_data))
        try:
            orientation = img.getexif().get(0x0112, 1)
        except Exception:
            orientation = 1

        if orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 8:
            img = img.rotate(90, expand=True)

        if orientation != 1:
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=95, exif=b"")
            return buf.getvalue()
    except Exception as e:
        logging.getLogger(__name__).warning("EXIF fix failed: %s", e)
    return image_data


class PhotoViewer(QGraphicsView):
    """Zoomable/pannable photo viewer for touchscreen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = None
        self._zoom = 1.0
        self._pinch_start_dist = 0

        # Drag to pan
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setStyleSheet("background: #0d1117; border: none;")

        # Touch interaction
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.viewport().setAttribute(Qt.WA_AcceptTouchEvents, True)

    def set_photo(self, pixmap: QPixmap):
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._zoom = 1.0
        self.fit_in_view()

    def fit_in_view(self):
        """Fit photo to viewport."""
        if self._pixmap_item:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def zoom_in(self):
        self._zoom *= 1.3
        self.scale(1.3, 1.3)

    def zoom_out(self):
        self._zoom /= 1.3
        self.scale(1 / 1.3, 1 / 1.3)

    def reset_zoom(self):
        self.resetTransform()
        self._zoom = 1.0
        self.fit_in_view()

    def wheelEvent(self, event: QWheelEvent):
        """Mouse wheel zoom."""
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Auto-fit when window resizes (if zoom=1)
        if self._zoom <= 1.05 and self._pixmap_item:
            self.fit_in_view()

    def clear_photo(self):
        self._scene.clear()
        self._pixmap_item = None
        self._zoom = 1.0


class CastView(QWidget):
    """Widget that displays casted content (screen mirror or photos)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_frame = None
        self._photos = []  # list of (bytes, filename)
        self._photo_index = -1
        self._is_photo_mode = False
        self._placeholder = self._make_placeholder()
        self._setup_ui()
        self._show_placeholder()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        # Page 0: Idle / placeholder
        self._idle_page = QWidget()
        idle_layout = QVBoxLayout(self._idle_page)
        idle_layout.setAlignment(Qt.AlignCenter)
        self._idle_label = QLabel(self._idle_page)
        self._idle_label.setAlignment(Qt.AlignCenter)
        idle_layout.addWidget(self._idle_label)

        # Page 1: Cast display (screen mirror)
        self._cast_page = QWidget()
        cast_layout = QVBoxLayout(self._cast_page)
        cast_layout.setContentsMargins(0, 0, 0, 0)
        self._display_label = QLabel(self._cast_page)
        self._display_label.setAlignment(Qt.AlignCenter)
        self._display_label.setStyleSheet("background-color: black;")
        self._display_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cast_layout.addWidget(self._display_label)

        # Page 2: Photo gallery with zoom/pan
        self._photo_page = QWidget()
        photo_layout = QVBoxLayout(self._photo_page)
        photo_layout.setContentsMargins(0, 0, 0, 0)

        self._photo_viewer = PhotoViewer()
        photo_layout.addWidget(self._photo_viewer, 1)

        # Photo toolbar
        toolbar = QFrame(self._photo_page)
        toolbar.setObjectName("photoToolbar")
        toolbar.setStyleSheet("""
            #photoToolbar { background: #161b22; border-top: 1px solid #30363d; padding: 6px; }
            QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                          border-radius: 6px; padding: 8px 18px; font-size: 15px; min-width: 60px; }
            QPushButton:hover { background: #30363d; border-color: #58a6ff; }
            QLabel { color: #8b949e; font-size: 14px; }
        """)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 6, 12, 6)

        self._btn_prev = QPushButton("◀ 上一张")
        self._btn_prev.clicked.connect(self._prev_photo)
        tb_layout.addWidget(self._btn_prev)

        self._btn_zoom_out = QPushButton("−")
        self._btn_zoom_out.setFixedWidth(44)
        self._btn_zoom_out.clicked.connect(lambda: self._photo_viewer.zoom_out())
        tb_layout.addWidget(self._btn_zoom_out)

        self._btn_fit = QPushButton("适应")
        self._btn_fit.clicked.connect(lambda: self._photo_viewer.reset_zoom())
        tb_layout.addWidget(self._btn_fit)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setFixedWidth(44)
        self._btn_zoom_in.clicked.connect(lambda: self._photo_viewer.zoom_in())
        tb_layout.addWidget(self._btn_zoom_in)

        self._photo_counter = QLabel("0 / 0")
        self._photo_counter.setAlignment(Qt.AlignCenter)
        tb_layout.addWidget(self._photo_counter, 1)

        self._btn_next = QPushButton("下一张 ▶")
        self._btn_next.clicked.connect(self._next_photo)
        tb_layout.addWidget(self._btn_next)

        self._btn_clear = QPushButton("清空")
        self._btn_clear.setStyleSheet(
            "background: #21262d; color: #f85149; border: 1px solid #f85149; "
            "border-radius: 6px; padding: 8px 18px; font-size: 15px;"
        )
        self._btn_clear.clicked.connect(self._clear_photos)
        tb_layout.addWidget(self._btn_clear)

        photo_layout.addWidget(toolbar)

        self._stack.addWidget(self._idle_page)    # 0
        self._stack.addWidget(self._cast_page)     # 1
        self._stack.addWidget(self._photo_page)    # 2

        layout.addWidget(self._stack)

    def _make_placeholder(self):
        pix = QPixmap(640, 480)
        pix.fill(QColor("#1a1a2e"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Noto Sans CJK SC", 28, QFont.Bold)
        p.setFont(font)
        p.setPen(QColor("#888888"))
        p.drawText(pix.rect(), Qt.AlignCenter,
                   "等待连接\n\n请使用手机扫描二维码")
        p.end()
        return pix

    def _show_placeholder(self):
        self._idle_label.setPixmap(self._placeholder)
        self._stack.setCurrentIndex(0)

    # === Screen mirror ===

    def show_frame(self, jpeg_data: bytes):
        """Display JPEG frame from screen mirror or camera."""
        self._is_photo_mode = False
        image = QImage()
        if image.loadFromData(jpeg_data, "JPEG"):
            self._current_frame = QPixmap.fromImage(image)
            w, h = self._current_frame.width(), self._current_frame.height()
            log = logging.getLogger(__name__)
            if self._stack.currentIndex() != 1:
                log.info("Frame: %dx%d", w, h)
            self._display_label.setPixmap(self._current_frame)
            self._stack.setCurrentIndex(1)
            self._scale_frame_to_fit()

    def show_no_signal(self):
        self._is_photo_mode = False
        pix = QPixmap(640, 480)
        pix.fill(QColor("#111111"))
        p = QPainter(pix)
        font = QFont("Noto Sans CJK SC", 24, QFont.Bold)
        p.setFont(font)
        p.setPen(QColor("#ff4444"))
        p.drawText(pix.rect(), Qt.AlignCenter, "信号断开\n\n请重新连接")
        p.end()
        self._display_label.setPixmap(pix)
        self._stack.setCurrentIndex(1)

    # === Photo gallery with zoom ===

    def add_photo(self, data: bytes, filename: str = "photo.jpg"):
        corrected = _correct_orientation(data)
        self._photos.append((corrected, filename))
        self._photo_index = len(self._photos) - 1
        self._is_photo_mode = True
        self._show_current_photo()

    def _show_current_photo(self):
        if self._photo_index < 0 or not self._photos:
            return
        data, _ = self._photos[self._photo_index]
        image = QImage()
        if image.loadFromData(data):
            self._photo_viewer.set_photo(QPixmap.fromImage(image))

        total = len(self._photos)
        self._photo_counter.setText(f"{self._photo_index + 1} / {total}")
        self._btn_prev.setEnabled(self._photo_index > 0)
        self._btn_next.setEnabled(self._photo_index < total - 1)
        self._stack.setCurrentIndex(2)

    def _next_photo(self):
        if self._photo_index < len(self._photos) - 1:
            self._photo_index += 1
            self._show_current_photo()

    def _prev_photo(self):
        if self._photo_index > 0:
            self._photo_index -= 1
            self._show_current_photo()

    def _clear_photos(self):
        self._photos.clear()
        self._photo_index = -1
        self._is_photo_mode = False
        self._photo_viewer.clear_photo()
        self._show_placeholder()

    @property
    def is_photo_mode(self) -> bool:
        return self._is_photo_mode

    @property
    def photo_count(self) -> int:
        return len(self._photos)

    # === Common ===

    def _scale_frame_to_fit(self):
        """Scale current frame to fill the display label while keeping aspect ratio."""
        if not self._current_frame:
            return
        size = self._display_label.size()
        if size.width() < 10 or size.height() < 10:
            return
        scaled = self._current_frame.scaled(
            size.width(), size.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._display_label.setPixmap(scaled)

    def reset(self):
        self._current_frame = None
        self._display_label.clear()
        self._is_photo_mode = False
        self._show_placeholder()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        idx = self._stack.currentIndex()
        if idx == 1 and self._current_frame:
            self._scale_frame_to_fit()
