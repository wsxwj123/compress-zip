#!/bin/zsh
# compress-zip 右键统一入口。
# 用法：czip-menu.sh <mode> [选中路径...]
#   mode = zip      一键压成 zip、不加密、零弹窗（最常用）
#          compress 高级压缩：弹窗选 7z/tar.gz + 加密方式 + 密码
#          here     解压到压缩包所在目录；先试无密码，只有确是加密包才弹密码框
#          to       解压：弹窗选目标文件夹（其余同 here）
#
# 选中项来源：优先用命令行参数（Automator/NSService/Menuist 若传了路径就用）；
# 没传就主动问 Finder 要当前选中项——这样不依赖各家右键增强 App 怎么传参。
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

MODE="$1"; shift

# --- 取选中项 ---
typeset -a ITEMS
if [ $# -gt 0 ]; then
  ITEMS=("$@")
else
  sel=$(osascript -e 'tell application "Finder" to set s to selection' \
    -e 'set out to ""' \
    -e 'repeat with i in s' \
    -e 'set out to out & (POSIX path of (i as alias)) & linefeed' \
    -e 'end repeat' -e 'return out' 2>/dev/null)
  while IFS= read -r line; do [ -n "$line" ] && ITEMS+=("$line"); done <<< "$sel"
fi
[ ${#ITEMS[@]} -eq 0 ] && exit 0

# --- 找一个装了依赖的 python3（右键运行时 PATH 极简，command -v 会选错）---
find_py() {
  local c
  for c in "$HOME/.pyenv/versions"/*/bin/python3 "$(pyenv which python3 2>/dev/null)" \
           /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -x "$c" ] && "$c" -c 'import pyzipper,py7zr,rarfile' 2>/dev/null && { printf '%s' "$c"; return 0; }
  done
  return 1
}
PY="$(find_py)"
if [ -z "$PY" ]; then
  osascript -e 'display alert "compress-zip：没找到装了依赖的 Python" message "请先 pip3 install pyzipper py7zr rarfile（装在你日常用的 Python 环境里）。"'
  exit 1
fi
CORE="$HOME/tools/compress-zip/czip.py"
ERRF="$(mktemp -t compresszip)"
trap 'rm -f "$ERRF"' EXIT

# 弹密码框（隐藏输入）。成功 echo 密码；用户取消返回非 0。
ask_pw() {
  osascript -e "text returned of (display dialog \"$1\" default answer \"\" with hidden answer buttons {\"取消\",\"确定\"} default button \"确定\")" 2>/dev/null
}
notify() { osascript -e 'on run a' -e 'display notification (item 1 of a) with title "compress-zip"' -e 'end run' "$1"; }
alert()  { osascript -e 'on run a' -e 'display alert (item 1 of a) message (item 2 of a)' -e 'end run' "$1" "$2"; }

case "$MODE" in

  # ---------- 一键 ZIP ----------
  zip)
    notify "开始压缩…"
    OUT=$(COMPRESS_PW="" "$PY" "$CORE" compress --format zip --encrypt none -- "${ITEMS[@]}" 2>"$ERRF")
    if [ $? -eq 0 ]; then notify "完成：$(basename "$OUT")"
    else alert "压缩失败" "$(cat "$ERRF")"; fi
    ;;

  # ---------- 高级压缩 ----------
  compress)
    fmt=$(osascript -e 'set r to choose from list {"zip","7z","tar.gz"} with prompt "选择压缩格式" default items {"zip"}' -e 'if r is false then return "CANCEL"' -e 'return item 1 of r')
    [ "$fmt" = "CANCEL" ] && exit 0
    case "$fmt" in zip) FMT=zip ;; 7z) FMT=7z ;; "tar.gz") FMT=targz ;; esac
    enc=$(osascript -e 'set r to choose from list {"不加密","AES-256 强加密","ZipCrypto 兼容加密"} with prompt "选择加密方式" default items {"不加密"}' -e 'if r is false then return "CANCEL"' -e 'return item 1 of r')
    [ "$enc" = "CANCEL" ] && exit 0
    case "$enc" in "不加密") ENC=none ;; "AES-256 强加密") ENC=aes ;; "ZipCrypto 兼容加密") ENC=zipcrypto ;; esac
    PW=""
    if [ "$ENC" != "none" ]; then
      PW=$(ask_pw "输入压缩密码") || exit 0
      [ -z "$PW" ] && { alert "密码为空，已取消" ""; exit 0; }
    fi
    notify "开始压缩…"
    OUT=$(COMPRESS_PW="$PW" "$PY" "$CORE" compress --format "$FMT" --encrypt "$ENC" -- "${ITEMS[@]}" 2>"$ERRF")
    if [ $? -eq 0 ]; then notify "完成：$(basename "$OUT")"
    else alert "压缩失败" "$(cat "$ERRF")"; fi
    ;;

  # ---------- 解压到此处 / 解压到指定文件夹 ----------
  here|to)
    DEST=""
    if [ "$MODE" = "to" ]; then
      DEST=$(osascript -e 'set d to choose folder with prompt "解压到哪个文件夹？"' -e 'return POSIX path of d' 2>/dev/null) || exit 0
    fi
    notify "开始解压…"
    fail=0
    for arc in "${ITEMS[@]}"; do
      run_extract() { # $1=密码
        if [ -n "$DEST" ]; then COMPRESS_PW="$1" "$PY" "$CORE" extract --dest "$DEST" -- "$arc" 2>"$ERRF"
        else COMPRESS_PW="$1" "$PY" "$CORE" extract -- "$arc" 2>"$ERRF"; fi
      }
      run_extract ""
      rc=$?
      if [ $rc -eq 4 ]; then          # 4 = 加密包/密码错，才弹密码框
        PW=$(ask_pw "「$(basename "$arc")」是加密包，请输入密码") || continue
        run_extract "$PW"; rc=$?
      fi
      [ $rc -ne 0 ] && { fail=1; alert "解压失败：$(basename "$arc")" "$(cat "$ERRF")"; }
    done
    [ $fail -eq 0 ] && notify "解压完成"
    ;;

  *) echo "未知 mode: $MODE" >&2; exit 2 ;;
esac
