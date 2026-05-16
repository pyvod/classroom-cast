#!/bin/bash
# 班级投屏 - 手动清理脚本
# 当 dpkg -i 失败（状态极不稳定 / 状态极为不妥）时运行此脚本，
# 然后重新执行: sudo dpkg -i classroom-cast.deb
#
# 用法:
#   sudo bash /opt/classroom-cast/cleanup.sh

set -e

PKG=classroom-cast
echo "=== 清理 $PKG 残留 ==="

# 1. 删除 dpkg 维护脚本
rm -f /var/lib/dpkg/info/${PKG}.* 2>/dev/null || true
rm -f /var/lib/dpkg/info/${PKG}-deb.* 2>/dev/null || true
echo "[1/4] dpkg info 文件已删除"

# 2. 从 dpkg 状态数据库移除包记录
if [ -f /var/lib/dpkg/status ]; then
    awk '
        BEGIN { skip = 0 }
        /^Package:/ && $2 == "'${PKG}'" { skip = 1; next }
        skip && /^$/ { skip = 0; next }
        skip { next }
        1
    ' /var/lib/dpkg/status > /tmp/dpkg-status-clean && \
    mv /tmp/dpkg-status-clean /var/lib/dpkg/status && \
    echo "[2/4] dpkg 状态记录已清除" || echo "[2/4] 跳过（无记录）"
fi

# 3. 删除安装文件
rm -rf /opt/classroom-cast 2>/dev/null || true
rm -f /usr/local/bin/classroom-cast 2>/dev/null || true
rm -f /usr/share/applications/${PKG}.desktop 2>/dev/null || true
rm -f /usr/share/icons/hicolor/scalable/apps/${PKG}.svg 2>/dev/null || true
echo "[3/4] 安装文件已删除"

# 4. 删除用户配置
for home in /home/* /root; do
    config_dir="$home/.config/${PKG}"
    [ -d "$config_dir" ] && rm -rf "$config_dir" && echo "  已清理: $config_dir" || true
done
echo "[4/4] 用户配置已清理"

echo ""
echo "=== 清理完成！现在可以重新安装 ==="
echo "  sudo dpkg -i classroom-cast.deb"
