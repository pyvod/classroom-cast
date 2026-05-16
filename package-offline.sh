#!/bin/bash
# ============================================
# 班级投屏 - 离线依赖打包脚本
# 在有网络的机器上运行，生成离线安装包
# ============================================
set -e

APP_NAME="班级投屏"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$APP_DIR/offline-pkg"
DEB_DIR="$OUTPUT_DIR/debs"
PYTHON_DIR="$OUTPUT_DIR/python"
UXPLAY_DIR="$OUTPUT_DIR/uxplay"
ARCH=$(uname -m)

echo "========================================"
echo "   打包 $APP_NAME 离线安装包"
echo "   架构: $ARCH"
echo "========================================"
echo ""

rm -rf "$OUTPUT_DIR"
mkdir -p "$DEB_DIR" "$PYTHON_DIR" "$UXPLAY_DIR"

# ---- 1. Download apt .deb packages ----
echo "[1/4] 下载系统依赖 (.deb)..."
DEPS=(
    python3-pyqt5
    python3-pip
    python3-venv
    python3-pil
    python3-qrcode
    libqt5widgets5
    qt5-qmake
    wpa_supplicant
    build-essential
    cmake
    git
    libavahi-compat-libdnssd-dev
    libssl-dev
    libgstreamer1.0-dev
    libgstreamer-plugins-base1.0-dev
    gstreamer1.0-plugins-good
    gstreamer1.0-plugins-bad
    gstreamer1.0-plugins-ugly
    gstreamer1.0-libav
)

# Try to download uxplay deb if available
apt-get download uxplay 2>/dev/null && mv *.deb "$DEB_DIR/" 2>/dev/null && echo "  ✓ uxplay .deb 已下载"

for pkg in "${DEPS[@]}"; do
    echo "  downloading: $pkg"
    apt-get download "$pkg" 2>/dev/null && mv *.deb "$DEB_DIR/" 2>/dev/null || echo "  ✗ $pkg 下载失败（可能已安装）"
done

# Download dependencies of these packages
apt-cache depends "${DEPS[@]}" 2>/dev/null | grep "Depends:" | awk '{print $2}' | sort -u | while read dep; do
    apt-get download "$dep" 2>/dev/null
done
mv *.deb "$DEB_DIR/" 2>/dev/null || true

# Remove duplicate debs
echo "  dedup .deb packages..."
ls -1 "$DEB_DIR/" | sort -u | wc -l | xargs echo "  total unique debs:"

# ---- 2. Download Python packages ----
echo "[2/4] 下载 Python 依赖..."
pip3 download -r "$APP_DIR/requirements.txt" -d "$PYTHON_DIR" 2>/dev/null
# Also download PyQt5 wheel for UOS
pip3 download PyQt5 PyQt5-sip -d "$PYTHON_DIR" 2>/dev/null || true
echo "  Python wheels saved to $PYTHON_DIR"

# ---- 3. Compile UxPlay and bundle binary ----
echo "[3/4] 编译 UxPlay..."
if command -v uxplay &> /dev/null; then
    UXPLAY_BIN=$(which uxplay)
    cp "$UXPLAY_BIN" "$UXPLAY_DIR/"
    echo "  ✓ UxPlay binary: $UXPLAY_BIN"
elif [ -f /usr/local/bin/uxplay ]; then
    cp /usr/local/bin/uxplay "$UXPLAY_DIR/"
elif [ -f /usr/bin/uxplay ]; then
    cp /usr/bin/uxplay "$UXPLAY_DIR/"
else
    echo "  尝试源码编译 UxPlay..."
    if [ ! -d /tmp/UxPlay ]; then
        git clone --depth=1 https://github.com/FDH2/UxPlay.git /tmp/UxPlay 2>/dev/null || {
            echo "  ✗ 无法克隆 UxPlay，跳过"
        }
    fi
    if [ -d /tmp/UxPlay ]; then
        (cd /tmp/UxPlay && mkdir -p build && cd build && \
         cmake .. -DCMAKE_BUILD_TYPE=Release && \
         make -j$(nproc) && \
         cp uxplay "$UXPLAY_DIR/")
        echo "  ✓ UxPlay 编译完成"
    fi
fi

# ---- 4. Create installation script ----
echo "[4/4] 生成离线安装脚本..."
cat > "$OUTPUT_DIR/install-offline.sh" << 'INSTALL_SCRIPT'
#!/bin/bash
# ============================================
# 班级投屏 - 离线安装脚本
# 在无网络的 UOS 机器上运行
# ============================================
set -e

APP_NAME="班级投屏"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo "   $APP_NAME 离线安装"
echo "========================================"
echo ""

# Install .deb packages
echo "[1/4] 安装系统依赖..."
sudo dpkg -i "$SCRIPT_DIR/debs/"*.deb 2>/dev/null || true
sudo apt-get install -f -y 2>/dev/null || true
echo "  系统依赖安装完成"

# Create virtual environment
echo "[2/4] 创建 Python 虚拟环境..."
python3 -m venv "$VENV_DIR"
echo "  虚拟环境已创建"

# Install Python packages from local wheels
echo "[3/4] 安装 Python 依赖..."
source "$VENV_DIR/bin/activate"
pip install --no-index --find-links "$SCRIPT_DIR/python" -r "$APP_DIR/requirements.txt" 2>/dev/null || \
pip install "$SCRIPT_DIR/python/"*.whl 2>/dev/null || true
deactivate
echo "  Python 依赖安装完成"

# Install UxPlay binary
echo "[4/4] 安装 UxPlay..."
if [ -f "$SCRIPT_DIR/uxplay/uxplay" ]; then
    sudo cp "$SCRIPT_DIR/uxplay/uxplay" /usr/local/bin/uxplay
    sudo chmod +x /usr/local/bin/uxplay
    echo "  UxPlay 已安装到 /usr/local/bin/uxplay"
else
    echo "  UxPlay 未打包，请手动安装: sudo apt install uxplay"
fi

# Create launcher
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/classroom-cast" << LAUNCHER
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec python3 "$APP_DIR/main.py"
LAUNCHER
chmod +x "$HOME/.local/bin/classroom-cast"

echo ""
echo "========================================"
echo "   离线安装完成！"
echo "========================================"
echo ""
echo "启动: ~/.local/bin/classroom-cast"
echo "或:  source venv/bin/activate && python main.py"
INSTALL_SCRIPT
chmod +x "$OUTPUT_DIR/install-offline.sh"

# Create tarball
echo ""
echo "打包离线安装包..."
cd "$APP_DIR"
tar czf "classroom-cast-offline-${ARCH}.tar.gz" \
    -C "$(dirname "$OUTPUT_DIR")" "$(basename "$OUTPUT_DIR")" \
    --exclude=".git" \
    2>/dev/null

echo ""
echo "========================================"
echo "   打包完成！"
echo "========================================"
echo ""
echo "离线包: $APP_DIR/classroom-cast-offline-${ARCH}.tar.gz"
echo ""
echo "使用方式:"
echo "  1. 拷贝离线包到 UOS 机器:"
echo "     scp classroom-cast-offline-${ARCH}.tar.gz uos-user@uos-ip:~/"
echo ""
echo "  2. 在 UOS 上解压安装:"
echo "     tar xzf classroom-cast-offline-${ARCH}.tar.gz"
echo "     cd offline-pkg"
echo "     bash install-offline.sh"
echo ""
echo "  3. 启动:"
echo "     cd classroom-cast"
echo "     source venv/bin/activate && python main.py"
echo ""
ls -lh "$APP_DIR/classroom-cast-offline-${ARCH}.tar.gz"
