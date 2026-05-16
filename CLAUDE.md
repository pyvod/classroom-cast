# 班级投屏 (Classroom Cast)

## 项目说明
统信UOS班级大屏一体机手机投屏软件。支持安卓屏幕镜像、拍照上传、网址推送、AirPlay/iOS镜像。

## 构建 .deb
```bash
dpkg-deb --build --root-owner-group classroom-cast-deb classroom-cast.deb
```

## 目录结构
- `classroom-cast-deb/` — .deb 打包目录
  - `DEBIAN/postinst` — 安装脚本（自动检测 Python 版本）
  - `DEBIAN/prerm` — 卸载脚本
  - `opt/classroom-cast/` — 主程序
    - `python-wheels/` — 离线 Python 轮子（cp37 + cp311 双版本）
    - `uxplay-libs/` — 捆绑的 uxplay + glibc 运行时
    - `classroom-cast.apk` — 安卓客户端
    - `web/` — Web 前端
  - `usr/local/bin/classroom-cast` — 启动脚本
  - `usr/share/applications/` — 桌面入口

## 兼容性
- UOS V20 (Python 3.7, glibc 2.28) — 使用 cp37 轮子 + 捆绑 glibc
- UOS V23 (Python 3.11, glibc 2.38) — 使用 cp311 轮子 + 额外依赖
