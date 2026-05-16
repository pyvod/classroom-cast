import asyncio
import logging
import ssl
from pathlib import Path
from typing import Optional, Callable

from aiohttp import web, WSMsgType

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent / "web"


class WebCastServer:
    """Web-based screen casting server using WebSocket.

    Runs inside an asyncio event loop (typically in a background thread).
    Supports both HTTP and HTTPS (self-signed cert generated at first run).
    """

    def __init__(self, on_frame_received: Optional[Callable[[bytes], None]] = None,
                 on_photo_received: Optional[Callable[[bytes, str], None]] = None,
                 on_url_received: Optional[Callable[[str], None]] = None,
                 host="0.0.0.0", port=8080, ssl_port=8443):
        self.host = host
        self.port = port
        self.ssl_port = ssl_port
        self._on_frame = on_frame_received
        self._on_photo = on_photo_received
        self._on_url = on_url_received
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._ws_connections = set()
        self._cast_session = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
        self._server_info = {
            "name": "班级投屏",
            "version": "1.0.0",
            "connected": False,
            "has_ssl": False,
        }

    # ---- HTTPS self-signed cert setup ----

    def _ensure_ssl_cert(self) -> Optional[ssl.SSLContext]:
        """Generate a self-signed certificate if one doesn't exist.

        Includes current local IPs in SAN so phones can connect via IP.
        """
        cert_dir = Path.home() / ".config" / "classroom-cast" / "ssl"
        cert_dir.mkdir(parents=True, exist_ok=True)

        cert_file = cert_dir / "cert.pem"
        key_file = cert_dir / "key.pem"

        # Collect current IPs to embed in SAN
        from .network import NetworkManager
        nm = NetworkManager()

        regenerate = not (cert_file.exists() and key_file.exists())
        if not regenerate and cert_file.exists():
            existing = cert_file.read_text()
            for ip in nm.all_ips:
                if ip not in existing:
                    regenerate = True
                    break

        if regenerate:
            logger.info("Generating self-signed SSL certificate...")
            try:
                self._generate_self_signed_cert(cert_file, key_file, nm.all_ips)
            except Exception as e:
                logger.warning("Failed to generate SSL cert: %s", e)
                return None

        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cert_file), str(key_file))
            return ctx
        except Exception as e:
            logger.warning("Failed to load SSL cert: %s", e)
            return None

    @staticmethod
    def _generate_self_signed_cert(cert_path: Path, key_path: Path,
                                    extra_ips: list = None):
        """Generate a self-signed certificate with IPs in SAN."""
        import ipaddress
        from datetime import datetime, timedelta, timezone

        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            import subprocess
            subj = "/CN=ClassroomCast"
            san = "DNS:localhost,DNS:classroom-cast"
            if extra_ips:
                san += "," + ",".join(f"IP:{ip}" for ip in extra_ips)
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key_path),
                "-out", str(cert_path),
                "-days", "3650", "-nodes",
                "-subj", subj,
                "-addext", f"subjectAltName={san}",
            ], check=True, capture_output=True)
            return

        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption,
        )
        key_path.write_bytes(key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption(),
        ))

        san_entries = [
            x509.DNSName("localhost"),
            x509.DNSName("classroom-cast"),
        ]
        if extra_ips:
            san_entries.extend(x509.IPAddress(ipaddress.IPv4Address(ip)) for ip in extra_ips)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "ClassroomCast"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .sign(key, hashes.SHA256(), backend=default_backend())
        )
        cert_path.write_bytes(cert.public_bytes(Encoding.PEM))

    # ---- HTTP routes ----

    async def _handle_index(self, request):
        index_path = ROOT / "index.html"
        if index_path.exists():
            return web.FileResponse(index_path)
        return web.Response(text="Index page not found", status=404)

    async def _handle_cast(self, request):
        cast_path = ROOT / "cast.html"
        if cast_path.exists():
            return web.FileResponse(cast_path)
        return web.Response(text="Cast page not found", status=404)

    async def _handle_static(self, request):
        filename = request.match_info["filename"]
        # Prevent directory traversal
        if ".." in filename or "/" in filename or not filename:
            return web.Response(text="Forbidden", status=403)
        # Serve APK for download (e.g., classroom-cast.apk)
        if filename.endswith(".apk"):
            apk_path = ROOT.parent / filename
            if apk_path.exists():
                return web.FileResponse(apk_path)
            return web.Response(text="APK not found", status=404)
        filepath = ROOT / filename
        if filepath.exists() and filepath.is_file():
            return web.FileResponse(filepath)
        return web.Response(text="Not found", status=404)

    async def _handle_server_info(self, request):
        from .network import NetworkManager
        nm = NetworkManager()
        ip = nm.primary_ip or "localhost"
        self._server_info["connected"] = self._cast_session is not None
        self._server_info["has_ssl"] = self._ssl_context is not None
        self._server_info["ip"] = ip
        self._server_info["http_port"] = self.port
        self._server_info["https_port"] = self.ssl_port if self._ssl_context else None
        return web.json_response(self._server_info)

    async def _handle_qr_data(self, request):
        from .network import NetworkManager
        nm = NetworkManager()
        ip = nm.primary_ip or "localhost"
        # Always use HTTP for QR — mobile clients (iOS/Android) don't support
        # HTTPS/WSS for WebSocket streaming. The SSL cert is self-signed and
        # causes connection failures on iOS. Users can manually use 8443 if needed.
        cast_url = f"http://{ip}:{self.port}/cast"
        return web.json_response({
            "url": cast_url,
            "ip": ip,
            "http_port": self.port,
            "https_port": self.ssl_port if self._ssl_context else None,
            "has_ssl": self._ssl_context is not None,
        })

    async def _handle_js(self, request):
        js_path = ROOT / "js" / "cast.js"
        if js_path.exists():
            return web.FileResponse(js_path)
        return web.Response(text="JS not found", status=404)

    # ---- Photo upload ----

    async def _handle_upload(self, request):
        """Receive a photo from the phone and display on the big screen."""
        try:
            reader = await request.multipart()
            field = await reader.next()
            if not field or field.name != "photo":
                return web.json_response({"ok": False, "error": "No photo field"}, status=400)

            data = await field.read()
            filename = field.filename or "photo.jpg"

            if not data:
                return web.json_response({"ok": False, "error": "Empty data"}, status=400)

            # Notify via callback
            if self._on_photo:
                self._on_photo(data, filename)

            logger.info("Photo received: %s (%d bytes)", filename, len(data))
            return web.json_response({"ok": True, "filename": filename, "size": len(data)})

        except Exception as e:
            logger.error("Upload error: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ---- URL push ----

    async def _handle_pushurl(self, request):
        """Receive a URL from the phone and open on the big screen."""
        try:
            body = await request.json()
            url = body.get("url", "").strip()
            if not url:
                return web.json_response({"ok": False, "error": "No URL"}, status=400)

            # Notify via callback
            if self._on_url:
                self._on_url(url)

            logger.info("URL pushed: %s", url)
            return web.json_response({"ok": True, "url": url})

        except Exception as e:
            logger.error("Push URL error: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ---- WebSocket ----

    async def _handle_ws(self, request):
        ws = web.WebSocketResponse(max_msg_size=0)
        await ws.prepare(request)
        self._ws_connections.add(ws)
        logger.info("WebSocket client connected (%d total)", len(self._ws_connections))

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    text = msg.data
                    if text == "PING":
                        await ws.send_str("PONG")
                    elif text.startswith("CAST_START"):
                        self._cast_session = ws
                        self._server_info["connected"] = True
                        logger.info("Casting session started")
                        for conn in self._ws_connections:
                            if conn != ws:
                                try:
                                    await conn.send_str("CASTING_ACTIVE")
                                except Exception:
                                    pass
                    elif text == "CAST_STOP":
                        if self._cast_session == ws:
                            self._cast_session = None
                            self._server_info["connected"] = False
                            logger.info("Casting session stopped")

                elif msg.type == WSMsgType.BINARY:
                    if self._on_frame and ws == self._cast_session:
                        try:
                            self._on_frame(msg.data)
                        except Exception as e:
                            logger.error("Frame callback error: %s", e)

                elif msg.type == WSMsgType.ERROR:
                    logger.error("WebSocket error: %s", ws.exception())

        except asyncio.CancelledError:
            pass
        finally:
            self._ws_connections.discard(ws)
            if self._cast_session == ws:
                self._cast_session = None
                self._server_info["connected"] = False
            logger.info("WebSocket disconnected (%d remaining)", len(self._ws_connections))

        return ws

    # ---- Lifecycle ----

    async def start(self):
        """Start HTTP (and optionally HTTPS) server."""
        self._loop = asyncio.get_running_loop()

        # Try to set up SSL
        self._ssl_context = self._ensure_ssl_cert()

        self._app = web.Application()
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/cast", self._handle_cast)
        self._app.router.add_get("/api/info", self._handle_server_info)
        self._app.router.add_get("/api/qr", self._handle_qr_data)
        self._app.router.add_get("/js/cast.js", self._handle_js)
        self._app.router.add_post("/api/upload", self._handle_upload)
        self._app.router.add_post("/api/pushurl", self._handle_pushurl)
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_get("/{filename}", self._handle_static)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # HTTP server
        http_site = web.TCPSite(self._runner, self.host, self.port)
        await http_site.start()
        logger.info("HTTP server started on %s:%d", self.host, self.port)

        # HTTPS server (if cert generated)
        if self._ssl_context:
            try:
                https_site = web.TCPSite(
                    self._runner, self.host, self.ssl_port,
                    ssl_context=self._ssl_context,
                )
                await https_site.start()
                logger.info("HTTPS server started on %s:%d", self.host, self.ssl_port)
            except Exception as e:
                logger.warning("Failed to start HTTPS server: %s", e)
                self._ssl_context = None

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        logger.info("Web server stopped")

    async def disconnect_client(self):
        """Send a disconnect notification to the phone and clear the session."""
        if self._cast_session:
            try:
                await self._cast_session.send_str("CLIENT_DISCONNECT")
            except Exception:
                pass
            self._ws_connections.discard(self._cast_session)
            self._cast_session = None
            self._server_info["connected"] = False

    @property
    def is_casting(self) -> bool:
        return self._cast_session is not None

    @property
    def urls(self):
        """Return connection URLs."""
        info = {
            "http": f"http://{self.host}:{self.port}/cast",
        }
        if self._ssl_context:
            info["https"] = f"https://{self.host}:{self.ssl_port}/cast"
        return info
