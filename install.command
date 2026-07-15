#!/bin/zsh
# compress-zip 一键安装：拷两个快捷操作到 ~/Library/Services，拷内核到 ~/tools/compress-zip。
# 双击运行即可（如提示无法打开，右键→打开，或先 chmod +x install.command）。
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "compress-zip 安装开始…"

# 1) 内核（czip.py + zipcrypto.py）→ ~/tools/compress-zip（快捷操作里写死这个路径）
CORE_DIR="$HOME/tools/compress-zip"
mkdir -p "$CORE_DIR"
cp "$SRC/czip.py" "$SRC/zipcrypto.py" "$CORE_DIR/"
echo "  内核已装到 $CORE_DIR"

# 2) 两个快捷操作 → ~/Library/Services
SERVICES="$HOME/Library/Services"
mkdir -p "$SERVICES"
cp -R "$SRC/quickactions/压缩.workflow" "$SRC/quickactions/解压.workflow" "$SERVICES/"
# 清隔离属性，避免从网上下载后右键不出现（忽略失败）
xattr -dr com.apple.quarantine "$SERVICES/压缩.workflow" "$SERVICES/解压.workflow" 2>/dev/null || true
echo "  快捷操作已装到 $SERVICES"

# 3) 依赖自检（只提示，不自动装——装依赖需用户确认）
echo ""
echo "依赖检查："
PY="$(command -v python3 || echo /opt/homebrew/bin/python3)"
for mod in pyzipper py7zr rarfile; do
  if "$PY" -c "import $mod" 2>/dev/null; then
    echo "  [OK] $mod"
  else
    echo "  [缺] $mod —— 请运行: pip3 install $mod"
  fi
done
if command -v unar >/dev/null 2>&1; then
  echo "  [OK] unar"
else
  echo "  [缺] unar（rar 解压需要）—— 请运行: brew install unar"
fi

echo ""
echo "安装完成。访达里右键文件/文件夹 → 快捷操作 → 「压缩…」「解压…」。"
echo "首次运行系统会问是否允许访问文件，点「允许」。"
