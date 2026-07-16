#!/bin/zsh
# compress-zip 一键安装。双击运行即可（若提示无法打开：右键→打开）。
# 做两件事：
#   1) 内核 + 脚本 → ~/tools/compress-zip
#   2) 构建一个后台小 App（CompressZip.app），用 macOS「服务」机制把压缩/解压
#      加进访达右键。选服务而非 Finder Sync 扩展，是因为只有服务能在 OneDrive/
#      iCloud 等云盘文件夹里照常出现（云盘目录被系统 File Provider 独占，第三方
#      Finder Sync 扩展在里面一律失效）。
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
echo "compress-zip 安装开始…"

# --- 1) 内核 + 脚本 → ~/tools/compress-zip ---
CORE_DIR="$HOME/tools/compress-zip"
mkdir -p "$CORE_DIR"
cp "$SRC/czip.py" "$SRC/zipcrypto.py" \
   "$SRC/quickactions/scripts/czip-menu.sh" "$CORE_DIR/"
chmod +x "$CORE_DIR"/*.sh
echo "  内核+脚本已装到 $CORE_DIR"

# --- 2) 构建并注册 NSService 壳 App ---
if ! xcrun -f swiftc >/dev/null 2>&1; then
  echo "  [缺] 需要 Xcode 命令行工具来编译。请先运行: xcode-select --install，装好后重跑本脚本。"
  exit 1
fi
APP="$HOME/Applications/CompressZip.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp "$SRC/quickactions/app/Info.plist" "$APP/Contents/Info.plist"
xcrun swiftc "$SRC/quickactions/app/main.swift" \
  -o "$APP/Contents/MacOS/CompressZip" -framework Cocoa
codesign -s - --force "$APP" 2>/dev/null || true   # ad-hoc 签名，无需开发者账号（--deep 已弃用，单可执行 App 用不上）
LSREG="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
"$LSREG" -f "$APP" 2>/dev/null || true
/System/Library/CoreServices/pbs -update 2>/dev/null || true
/System/Library/CoreServices/pbs -flush  2>/dev/null || true
open -g "$APP"   # 启动一次让服务上线（LSUIElement，后台运行、不占程序坞）
echo "  右键服务 App 已装到 $APP 并注册"

# --- 3) 依赖自检（只提示，装依赖需你确认）---
# 用和运行时 find_py 一致的探测：找一个三件依赖齐全的 python，别被没装依赖的默认 python3 误导。
echo ""
echo "依赖检查："
setopt null_glob   # 没装 pyenv 时 ~/.pyenv/versions/* 无匹配，别让 set -e 脚本在此中止
PY=""
for c in "$HOME/.pyenv/versions"/*/bin/python3 "$(pyenv which python3 2>/dev/null)" \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [ -x "$c" ] && "$c" -c 'import pyzipper,py7zr,rarfile' 2>/dev/null && { PY="$c"; break; }
done
if [ -n "$PY" ]; then
  echo "  [OK] pyzipper / py7zr / rarfile 均已就绪（$PY）"
else
  echo "  [缺] pyzipper/py7zr/rarfile 未在同一个 python 里凑齐 —— 在你日常用的 python 里跑: pip3 install pyzipper py7zr rarfile"
fi
command -v unar >/dev/null 2>&1 && echo "  [OK] unar" || echo "  [缺] unar（rar 解压需要）—— 请运行: brew install unar"

echo ""
echo "安装完成。访达里右键文件/文件夹 → 最下方「服务」→「压缩…（compress-zip）」「解压…（compress-zip）」。"
echo "嫌菜单深？去 系统设置→键盘→键盘快捷键→服务 给它俩绑快捷键，任何文件夹（含 OneDrive）按键即用。"
echo "首次运行会问是否允许访问文件/控制 Finder，点「允许」。"
