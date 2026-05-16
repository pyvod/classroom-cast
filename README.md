# 班级投屏 (Classroom Cast)

**统信UOS班级大屏一体机手机投屏软件**

## 功能特点

- **扫码投屏** - 手机扫描二维码，浏览器打开即可投屏，无需安装 App
- **跨平台** - 支持 Android 和 iOS 手机
- **实时屏幕镜像** - 低延迟手机屏幕实时投射到班级大屏
- **精美界面** - 为班级大屏优化的深色 UI，支持触控操作
- **多种投屏方式** - Web 扫码投屏 + Miracast（安卓原生）

## 系统要求

- **操作系统**: 统信UOS 20/1060 及以上版本
- **屏幕**: 班级大屏一体机（1024×768 以上分辨率）
- **网络**: 支持 WiFi 或有线网络
- **Python**: 3.8 及以上

## 快速安装

### 方法一：一键安装

```bash
git clone <项目地址>
cd classroom-cast
chmod +x setup.sh
./setup.sh
```

### 方法二：手动安装

```bash
# 安装系统依赖
sudo apt install python3-pyqt5 python3-pip python3-pil python3-venv

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装 Python 依赖
pip install -r requirements.txt

# 运行
python main.py
```

## 使用方法

### 投屏步骤

1. **启动软件**
   - 在应用菜单中找到「班级投屏」并打开
   - 或在终端执行: `python main.py`

2. **连接网络**
   - 确保大屏和手机连接在**同一个 WiFi 网络**下
   - 软件界面右上角会显示当前 IP 地址

3. **手机扫码**
   - 使用手机浏览器（微信/支付宝扫码均可）扫描大屏上的二维码
   - 或直接在手机浏览器输入显示的 IP 地址

4. **开始投屏**
   - 在手机浏览器中点击「开始投屏」按钮
   - 选择「整个屏幕」或「应用窗口」
   - 点击「分享」或「允许」即可开始投屏

### 注意事项

- **iOS (iPhone/iPad)**: 使用 Safari 浏览器打开，支持系统屏幕录制
- **Android**: 使用 Chrome/Edge/系统浏览器均可
- 投屏过程中请保持手机亮屏（可在设置中调整自动锁屏为更长间隔）
- 建议使用 5GHz WiFi 以获得更好的投屏体验

## 投屏方式

| 方式 | 适用设备 | 特点 |
|------|---------|------|
| **扫码投屏**（推荐） | 安卓 / iOS | 无需安装App，扫码即用 |
| **Miracast** | 安卓 4.2+ | 原生投屏协议，延迟低 |
| **AirPlay** | iOS (iOS 12+) | 苹果设备原生支持（需安装 Uxplay） |

## 项目结构

```
classroom-cast/
├── main.py                    # 程序入口
├── requirements.txt           # Python 依赖
├── setup.sh                   # UOS 安装脚本
├── classroom_cast/
│   ├── app.py                 # 应用配置
│   ├── config.py              # 配置管理
│   ├── ui/
│   │   ├── main_window.py     # 主窗口
│   │   ├── cast_view.py       # 投屏画面显示
│   │   └── qr_widget.py       # 二维码组件
│   └── backend/
│       ├── webcast.py         # Web 投屏服务器
│       ├── miracast.py        # Miracast 管理
│       └── network.py         # 网络工具
└── web/
    ├── index.html             # 首页
    ├── cast.html              # 投屏页面
    └── js/cast.js             # 投屏客户端
```

## 开发说明

### 技术栈

- **GUI**: PyQt5
- **Web**: aiohttp + WebSocket
- **前端**: HTML5 + CSS3 + WebRTC (Screen Capture API)
- **二维码**: qrcode + Pillow

### 投屏原理

1. 大屏运行 Python Web 服务器
2. 手机浏览器通过扫码或输入 IP 访问投屏页面
3. 手机浏览器调用 WebRTC `getDisplayMedia()` 接口捕获屏幕
4. 通过 WebSocket 实时传输屏幕画面
5. 大屏接收并显示画面

## 常见问题

**Q: 手机扫码后无法连接？**
A: 请检查手机和大屏是否在同一 WiFi 网络，检查大屏防火墙设置。

**Q: 投屏画面卡顿？**
A: 建议使用 5GHz WiFi，减少网络干扰，关掉不必要的后台应用。

**Q: iOS 无法投屏？**
A: iOS 需要 Safari 浏览器，首次使用需在「设置 > Safari > 自动」中开启相关权限。

**Q: 投屏时手机可以息屏吗？**
A: 当前需要保持手机亮屏。可以在手机设置中将自动锁屏时间调整为 5 分钟或更长。

## License

MIT License
