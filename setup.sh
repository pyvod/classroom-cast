#!/bin/bash
# ============================================
# 班级投屏 - 统信UOS 安装脚本
# Classroom Cast - UOS Setup Script
# ============================================

set -e

APP_NAME="班级投屏"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
VENV_DIR="$APP_DIR/venv"
DESKTOP_FILE="$HOME/.local/share/applications/classroom-cast.desktop"
ICON_DIR="$HOME/.local/share/icons"
BIN_DIR="$HOME/.local/bin"

echo "========================================"
echo "   $APP_NAME 安装程序"
echo "   统信UOS 班级大屏投屏系统"
echo "========================================"
echo ""

# ---- Step 1: Check Python ----
echo "[1/7] 检查 Python 环境..."
if ! command -v $PYTHON &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装:"
    echo "  sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PY_VER=$($PYTHON --version)
echo "  检测到: $PY_VER"

# ---- Step 2: Install system dependencies ----
echo ""
echo "[2/7] 安装系统依赖..."
if command -v apt &> /dev/null; then
    echo "  检测到 apt 包管理器"
    echo "  以下命令可能需要 sudo 权限:"
    sudo apt update -qq
    sudo apt install -y -qq \
        python3-pyqt5 \
        python3-pip \
        python3-venv \
        qt5-qmake \
        libqt5widgets5 \
        python3-pil \
        python3-qrcode \
        wpa_supplicant \
        wireless-tools \
        2>/dev/null || echo "  (部分包可能已安装或不可用，继续...)"
elif command -v yum &> /dev/null; then
    echo "  检测到 yum 包管理器"
    sudo yum install -y python3-qt5 python3-pip wpa_supplicant 2>/dev/null || true
else
    echo "  警告: 无法识别的包管理器，请手动安装 PyQt5 等依赖"
fi

# ---- Step 3: Create virtual environment ----
echo ""
echo "[3/7] 创建 Python 虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
    echo "  虚拟环境已创建: $VENV_DIR"
else
    echo "  虚拟环境已存在，跳过"
fi

# ---- Step 4: Install Python packages ----
echo ""
echo "[4/7] 安装 Python 依赖..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$APP_DIR/requirements.txt" -q
deactivate
echo "  依赖安装完成"

# ---- Step 5: Install UxPlay (AirPlay receiver for iOS mirroring) ----
echo ""
echo "[5/7] 安装 UxPlay (AirPlay 投屏接收器)..."
UxPLAY_INSTALLED=false
if command -v uxplay &> /dev/null; then
    echo "  UxPlay 已安装，跳过"
    UxPLAY_INSTALLED=true
else
    echo "  尝试通过 apt 安装..."
    if sudo apt install -y -qq uxplay 2>/dev/null; then
        echo "  UxPlay apt 安装成功"
        UxPLAY_INSTALLED=true
    else
        echo "  apt 源中未找到 uxplay，尝试源码编译..."
        # Check if build tools are available
        if ! command -v cmake &> /dev/null; then
            echo "  安装编译工具..."
            sudo apt install -y -qq build-essential cmake git \
                libavahi-compat-libdnssd-dev libssl-dev \
                libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
                gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
                gstreamer1.0-plugins-ugly gstreamer1.0-libav 2>/dev/null
        fi
        if [ -d /tmp/UxPlay ]; then rm -rf /tmp/UxPlay; fi
        git clone --depth=1 https://github.com/FDH2/UxPlay.git /tmp/UxPlay 2>/dev/null && \
        (cd /tmp/UxPlay && mkdir -p build && cd build && \
         cmake .. && make -j$(nproc) && sudo make install) && \
        UxPLAY_INSTALLED=true && \
        echo "  UxPlay 源码编译安装成功" || \
        echo "  UxPlay 安装失败，可稍后手动安装（不影响其他功能）"
    fi
fi
if [ "$UxPLAY_INSTALLED" = true ]; then
    echo "  UxPlay 就绪！iPhone 屏幕镜像可投屏到本机"
fi

# ---- Step 6: Create desktop entry ----
echo ""
echo "[6/7] 创建桌面快捷方式..."
mkdir -p "$ICON_DIR" "$BIN_DIR"

# Create launcher script
LAUNCHER="$BIN_DIR/classroom-cast"
cat > "$LAUNCHER" << LAUNCHER_EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec $PYTHON "$APP_DIR/main.py"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

# Create .desktop file
cat > "$DESKTOP_FILE" << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Name[zh_CN]=$APP_NAME
Comment=Classroom screen casting for UOS
Comment[zh_CN]=统信UOS班级大屏手机投屏系统
Exec=$LAUNCHER
Icon=classroom-cast
Terminal=false
Categories=Education;Network;
StartupWMClass=classroom-cast
X-Deepin-CreatedBy=com.classroom.cast
X-Deepin-Version=1.0.0
DESKTOP_EOF

# Create placeholder icon (a simple SVG)
cat > "$ICON_DIR/classroom-cast.svg" << ICON_EOF
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <rect width="128" height="128" rx="20" fill="#1f6feb"/>
  <rect x="20" y="16" width="88" height="64" rx="8" fill="#0d1117"/>
  <rect x="28" y="24" width="72" height="48" rx="4" fill="#161b22"/>
  <text x="64" y="56" text-anchor="middle" fill="#58a6ff" font-size="28" font-family="sans-serif">投屏</text>
  <path d="M44 88 L64 112 L84 88 Z" fill="#1f6feb"/>
  <rect x="58" y="16" width="12" height="8" rx="2" fill="#3fb950"/>
  <circle cx="64" cy="44" r="6" fill="#3fb950" opacity="0.2"/>
  <circle cx="64" cy="44" r="3" fill="#3fb950" opacity="0.5"/>
</svg>
ICON_EOF

chmod +x "$DESKTOP_FILE"
echo "  快捷方式已创建: $DESKTOP_FILE"

# ---- Step 7: Verify UxPlay ----
echo ""
echo "[7/7] 检查 UxPlay 状态..."
if command -v uxplay &> /dev/null; then
    echo "  ✓ UxPlay 可用，iPhone 屏幕镜像功能正常"
else
    echo "  ○ UxPlay 未安装，iPhone 屏幕镜像不可用"
    echo "    可稍后运行以下命令安装:"
    echo "    sudo apt install uxplay"
    echo "    或参考: https://github.com/FDH2/UxPlay"
fi

# ---- Done ----
echo ""
echo "========================================"
echo "   安装完成！"
echo "========================================"
echo ""
echo "启动方式:"
echo "  1. 在应用菜单中搜索「$APP_NAME」"
echo "  2. 或运行: $LAUNCHER"
echo ""
echo "使用说明:"
echo "  1. 打开软件后，大屏会显示二维码"
echo "  2. 手机使用浏览器扫描二维码"
echo "  3. 点击「开始投屏」并允许屏幕录制"
echo ""
echo "要求:"
echo "  - 手机与大屏连接同一WiFi网络"
echo "  - 安卓/iOS 均支持"
echo ""
echo "iPhone 投屏:"
echo "  1. 安装 UxPlay 后，点击软件侧边栏「AirPlay」按钮"
echo "  2. iPhone 控制中心 → 屏幕镜像 → 选择「班级投屏」"
echo ""
