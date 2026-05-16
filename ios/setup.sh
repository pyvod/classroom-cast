cd "$(dirname "$0")"

# Install XcodeGen if not present
if ! command -v xcodegen &>/dev/null; then
    echo "正在安装 XcodeGen..."
    brew install xcodegen
fi

# Generate Xcode project
xcodegen generate

echo "项目已生成，打开 ClassroomCast.xcodeproj 即可"
open ClassroomCast.xcodeproj
