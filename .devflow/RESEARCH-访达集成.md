# 调研报告：把 Python 压缩/解压脚本接到访达（Finder）右键菜单

> 场景：macOS 15.7.3 Sequoia，单人开发者，不做签名/公证的原生 App。底层压缩解压已经是一个 Python 命令行脚本，本报告只解决「怎么把它挂到访达右键 + 运行中怎么弹原生窗口交互」。
>
> 一句话结论：**用 Automator「快捷操作」(Quick Action) 包一个 `Run Shell Script`，调你的 Python 脚本；运行中用 `osascript` 弹原生对话框选格式/加密/路径。** 这是最省事、无签名门槛、多文件传递最干净的方案。Shortcuts.app 能做到同样效果但摩擦更多（分发时要开「允许不受信任的快捷指令」、还多一道 shell 授权），不推荐作主力。

---

## 0. 结论速览（先看这张表）

| 维度 | Automator 快捷操作（推荐） | Shortcuts.app 快捷指令 |
|---|---|---|
| 接管访达右键 | ✅ 原生「快捷操作」菜单 | ✅ 勾选「用作快捷操作」后同样进右键 |
| 包 shell/CLI 脚本 | ✅ 天生就是干这个的 | ⚠️ 有 `Run Shell Script`，但每台机器首次要点「允许运行 shell 脚本」 |
| 多选文件传给脚本 | ✅ 直接变成 `"$@"` 位置参数，最干净 | ✅ 走「快捷指令输入」，但要在图形界面里搭 |
| 中文/空格路径 | ✅ 每个文件是独立 argv 元素，引号包住就零风险 | ✅ 同理 |
| 弹窗交互 | 用 `osascript`（本报告主力方案） | 有原生积木（询问输入/从菜单选择），也可调 osascript |
| 沙箱/权限摩擦 | 低：非沙箱，仅首次访问桌面/文稿等触发一次隐私授权 | 高：不受信任快捷指令默认禁止导入，要手动开开关 |
| 分发给别人 | 拷 `.workflow` 到 `~/Library/Services` 或双击安装 | 导出 `.shortcut` / iCloud 链接，对方要先开「允许不受信任」 |
| 需要签名/开发者账号吗 | ❌ 都不需要 | ❌ 都不需要 |

来源：[Apple 官方 · 在访达中执行快捷操作](https://support.apple.com/guide/mac-help/perform-quick-actions-in-the-finder-on-mac-mchl97ff9142/mac)、[Apple 官方 · Automator 快捷操作工作流程](https://support.apple.com/guide/automator/use-quick-action-workflows-aut73234890a/mac)、[MacRumors · Finder Quick Actions](https://www.macrumors.com/how-to/use-finder-quick-actions/)。

---

## 1. 接入访达右键的方案对比

### 1.1 Automator「快捷操作」(Quick Action / Service) —— 推荐

**本质**：快捷操作就是一个 Automator 工作流程，文稿类型选「快捷操作」。它编译成一个 `.workflow` 包（其实是个文件夹），放进 `~/Library/Services/`，系统就把它挂到访达右键的「快捷操作」子菜单里（超过 4 个会收进「服务」子菜单）。

**怎么做（一次成型）**：
1. 打开 Automator → 新建 →「快捷操作」。
2. 顶部设「工作流程收到当前的**文件或文件夹**，位于**访达.app**」。这一步就等于声明「我接收用户在访达里选中的东西」，**不需要再拖一个「获取所选访达项目」动作**——选中项已经是输入了。
3. 拖入「运行 Shell 脚本」动作：
   - Shell 选 `/bin/zsh`（或 bash 都行）；
   - **「传递输入」选「作为自变量 (as arguments)」** ← 关键，见第 2 节；
   - 脚本体里调你的 Python（见下面的坑，解释器要写全路径）。
4. ⌘S 保存，取个名字比如「压缩…」。保存后自动落到 `~/Library/Services/压缩….workflow`，右键立刻可用。

**装在哪 / 卸载**：
- 装：`~/Library/Services/<名字>.workflow`（当前用户）。全局所有用户是 `/Library/Services/`（需管理员）。
- 卸载：把那个 `.workflow` 从 `~/Library/Services/` 删掉即可（丢废纸篓就行，不是危险操作）。
- 开关/隐藏但不删：System Settings → Privacy & Security → Extensions → **Finder**，勾选框控制哪些快捷操作出现在右键里；第三方服务的总控在 Keyboard → Keyboard Shortcuts → **Services**。（[MacRumors](https://www.macrumors.com/how-to/use-finder-quick-actions/)、[MacMost](https://macmost.com/customizing-the-mac-context-menu.html)）

### 1.2 Shortcuts.app「快捷指令」—— Sequoia 上能接管右键，但作主力更麻烦

- **能不能进访达右键**：能。做法：在快捷指令里勾「用作快捷操作」，并让它「接收 文件/文件夹」作为输入；然后 Control-点击访达里的文件 →「快捷操作」→ 你的指令。也可以把指令从 All Shortcuts 拖到侧栏的「Quick Actions」。（[Apple 官方 · 从其他 App 启动快捷指令](https://support.apple.com/guide/shortcuts-mac/launch-a-shortcut-from-another-app-apd163eb9f95/mac)、[iMore](https://www.imore.com/how-use-quick-actions-shortcuts-mac)）
- **和 Automator 的关系**：Shortcuts 是 Apple 力推的「继任者」，但到 Sequoia，Automator 依旧完整可用，且对「包一个 CLI 脚本」这种活儿更直接。Shortcuts 里也有 `Run Shell Script` 积木，但它每台机器首次运行要弹「允许运行 shell 脚本」确认，且指令内部搭 shell 逻辑不如 Automator 顺手。
- **为什么不推荐作主力**：见 1.3 的分发摩擦——别人导入你的 `.shortcut` 前，必须先在设置里打开「允许不受信任的快捷指令」，对「给普通用户装」是硬伤。它的长处（原生的「询问输入」「从菜单选择」积木）我们用 `osascript` 也能拿到，不值得为此吃分发摩擦。

### 1.3 签名 / 开发者账号 / 分发

- **两种方案都不用签名、不用开发者账号、不用公证**——它们跑的是「用户自己的本地脚本」，不是要上架的 App，Gatekeeper 那套签名公证要求不落在这里。
- 分发差异：
  - **Automator**：把 `.workflow` 压成 zip 发给对方，对方解压后**双击 → Sequoia 弹「安装/添加快捷操作」**，或手动拖进 `~/Library/Services/`。若是从网上下载的，可能带 `com.apple.quarantine` 隔离属性，装完右键不出现时，`xattr -dr com.apple.quarantine <路径>` 清一下即可。
  - **Shortcuts**：导出 `.shortcut` 文件或生成 iCloud 分享链接；对方导入前要在 Shortcuts → 设置 → 隐私里打开「允许不受信任的快捷指令 (Allow Untrusted Shortcuts)」，否则直接拒绝导入。这一步是分发给非技术用户的最大障碍。

**方案推荐**：**Automator 快捷操作**。理由三条——(1) 天生就是「把 shell/CLI 脚本挂右键」的工具，选中的多文件直接变 `"$@"`；(2) 分发无「不受信任」这道坎，拷进 `~/Library/Services` 就完事；(3) 非沙箱，配 `osascript` 弹窗即可拿到全部原生交互。Shortcuts 留作备选/给已经在用快捷指令生态的人。

---

## 2. 多文件怎么传给脚本（中文 / 空格路径不出错）

**核心机制**：在「运行 Shell 脚本」里把「传递输入」设为 **「作为自变量 (as arguments)」**，Automator 会把用户选中的**每一个文件/文件夹作为一个独立的位置参数**塞进来。所以脚本里：

```bash
#!/bin/zsh
# Automator「运行 Shell 脚本」·「传递输入：作为自变量」
# 选中的每个 Finder 项 = 一个独立的 $1 $2 ... ，用 "$@" 遍历
for f in "$@"; do
    /usr/local/bin/python3 "$HOME/tools/compress.py" "$f"
done
```

- **中文 / 空格 / emoji 路径为什么不乱**：因为每个文件是独立的 argv 元素（不是拼成一个字符串再拆），你只要**始终给变量加双引号**（`"$@"`、`"$f"`），shell 就不会按空格切词，中文/空格/特殊字符原样进 Python 的 `sys.argv`。这是「按参数传」相对「按字符串拼」的根本优势。
- **一次把所有文件交给脚本**（压缩多选打成一个包时常用）：别循环，直接把 `"$@"` 整个丢给 Python，让 Python 端用 `sys.argv[1:]` 收全部路径：
  ```bash
  /usr/local/bin/python3 "$HOME/tools/compress.py" "$@"
  ```
- **另一种传法「作为 stdin (to stdin)」**：文件路径按行喂给脚本的标准输入。多文件时用 `while IFS= read -r f` 逐行读。缺点：路径里若含换行符会出错（极罕见），且不如 argv 直观。**首选「作为自变量」**。
- 环境变量方式：Automator 不走 `$@` 之外的专用环境变量传选中项，无需考虑。

Python 端配套（保证按字节拿到路径，不被本地化编码坑）：`sys.argv` 里已是 UTF-8 字符串，直接 `pathlib.Path(arg)` 即可；对文件系统操作用 `os`/`pathlib` 原生接口，别自己去 encode/decode 文件名。

来源：[Automators Talk · Run Shell Script Quick Action 传文件给 CLI](https://talk.automators.fm/t/run-shell-script-quick-action-need-help-scripting-input-file-for-cli-program/5390)、[Apple Discussions · passing filename to shell script](https://discussions.apple.com/thread/2284476)。

---

## 3. 运行中弹原生对话框（选格式 / 加密 / 路径）

脚本运行时用 `osascript` 调 AppleScript 的标准附加命令，全是系统原生窗口。可以在 shell 里弹、也可以在 Python 里用 `subprocess` 调——**建议放在 Python 脚本里调 `osascript`**，逻辑集中、好维护。

### 3.1 选格式（列表单选）—— `choose from list`

```bash
fmt=$(osascript -e 'set r to choose from list {"zip","7z","tar.gz"} with prompt "选择压缩格式" default items {"zip"}' -e 'if r is false then return "CANCEL"' -e 'return item 1 of r')
[ "$fmt" = "CANCEL" ] && exit 0   # 用户点了取消
```
`choose from list` 用户取消时返回 `false`；上面把它转成 `CANCEL` 好判断。

### 3.2 选加密方式（列表）+ 输入密码（隐藏输入）—— `display dialog ... hidden answer`

```bash
enc=$(osascript -e 'set r to choose from list {"AES-256 强加密","ZipCrypto 兼容加密","不加密"} with prompt "选择加密方式" default items {"不加密"}' -e 'if r is false then return "CANCEL"' -e 'return item 1 of r')
[ "$enc" = "CANCEL" ] && exit 0

if [ "$enc" != "不加密" ]; then
    pw=$(osascript -e 'text returned of (display dialog "输入压缩密码" default answer "" with hidden answer buttons {"取消","确定"} default button "确定")')
    # 用户点取消：display dialog 会以错误 -128 退出，$? 非 0
    [ -z "$pw" ] && { osascript -e 'display alert "密码为空，已取消"'; exit 0; }
fi
```
- `with hidden answer` = 密码框显示圆点，不回显明文。**密码只在内存/变量里，别写日志、别落盘**（符合 BRIEF 的密钥红线）。
- 用户点「取消」按钮时 `display dialog` 抛 AppleScript 错误 `-128`，`osascript` 以非 0 退出——脚本里可用 `|| exit 0` 拦掉，避免报错弹窗。

### 3.3 选解压目标路径 —— `choose folder`

```bash
dest=$(osascript -e 'set d to choose folder with prompt "选择解压到哪个文件夹"' -e 'return POSIX path of d')
[ -z "$dest" ] && exit 0   # 取消
# dest 形如 /Users/xxx/Desktop/  ，末尾带斜杠
```
`choose folder` 返回的是 AppleScript 别名，`POSIX path of` 转成 `/Users/...` 这种普通路径给 Python 用。想给个默认起始目录加 `default location (path to desktop folder)`。

### 3.4 结果/错误提示 —— `display alert` / `display notification`

```bash
osascript -e 'display notification "压缩完成：archive.zip" with title "compress-zip"'   # 轻提示，右上角横幅
osascript -e 'display alert "解压失败" message "密码错误或包已损坏"'                      # 重提示，模态弹窗要点确认
```

Python 里等价写法（推荐用这个组织交互）：
```python
import subprocess
def osa(script: str) -> str:
    return subprocess.run(["osascript", "-e", script],
                          capture_output=True, text=True).stdout.strip()

fmt = osa('set r to choose from list {"zip","7z","tar.gz"} with prompt "选择压缩格式" default items {"zip"}\n'
          'if r is false then return "CANCEL"\nreturn item 1 of r')
if fmt == "CANCEL":
    raise SystemExit(0)
```

来源：[Apple 开发者 · Mac 自动化脚本指南：从列表选择](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/PromptforaChoicefromaList.html)、[Apple 开发者 · 提示选择文件/文件夹](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/PromptforaFileorFolder.html)。

---

## 4. 限制与坑（这一节最省你调试时间）

### 4.1 PATH 极简，找不到 python3 / 7z（最常见的坑）
快捷操作里的 shell **不加载你的 `~/.zshrc`**，PATH 只有系统默认的 `/usr/bin:/bin:/usr/sbin:/sbin`。后果：
- Homebrew 装的 `python3`（`/opt/homebrew/bin/python3`，Apple Silicon）、python.org 装的（`/usr/local/bin/python3`）、以及 `7z`/`7zz`、`gtar` 这些**都不在 PATH 里，直接写 `python3` 会「command not found」或误跑到系统占位符**。
- 系统自带的 `/usr/bin/python3` 是个占位壳，首次调用会弹「要装命令行工具」，不能依赖。

**解决（二选一，都写进脚本头部）**：
```bash
# 方案A：解释器和外部工具全写绝对路径（最稳）
/opt/homebrew/bin/python3 "$HOME/tools/compress.py" "$@"

# 方案B：脚本开头补全 PATH，让脚本内部能找到 7z/tar 等
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
```
先在终端 `which python3`、`which 7zz` 查出真实路径写死。Apple Silicon 一般 `/opt/homebrew/bin`，Intel 一般 `/usr/local/bin`——**分发给别人时两条都 export 进去兜底**。（来源：[Apple Discussions · Automator 跑 Python3](https://discussions.apple.com/thread/8392208)）

### 4.2 隐私授权（TCC）
快捷操作**非沙箱**，以当前用户权限运行；但首次访问「桌面/文稿/下载/可移动卷/网络卷」时，系统会弹一次「允许 <快捷操作/Automator> 访问这些文件」的 TCC 授权，点允许即可，之后不再问。用户若拒了会导致读不到文件——安装教程里要提醒「首次运行点允许」。彻底省事可让用户给 Automator 一次「完全磁盘访问」，但非必需，别默认要求。

### 4.3 错误怎么让用户看见
快捷操作**没有终端窗口**，脚本的 stdout/stderr 用户看不到。所以：
- 出错必须主动 `osascript -e 'display alert ...'` 弹出来（见 3.4），别指望 `print`/`echo`。
- 调试期想看日志：脚本里 `exec >> "$HOME/compress-zip.log" 2>&1` 把输出重定向到文件，自己 `tail -f`。
- 快捷操作本身崩溃时，Automator 会弹一个通用的「工作流程未能完成」框，信息量少，所以业务错误一定自己兜住并弹明确提示。

### 4.4 大文件的进度提示
`osascript`/Automator **没有现成的进度条**（AppleScript 的 `progress` 属性只在 Script Editor 里显示，从 `osascript` 调出不来）。实用做法：
- 开始时 `display notification "开始压缩，大文件请稍候…"`，结束 `display notification "完成"`——最省事，够用。
- 想要真进度条：让 Python 把进度写日志文件，另起一个轻量提示；或干脆在压缩前用 `display dialog` 告知「即将处理 N 个文件，可能耗时」。对单人工具，通知横幅足矣，别过度工程。
- 长任务期间防休眠可在脚本头 `caffeinate -i -w $$ &`（可选）。

### 4.5 其它零碎
- 快捷操作对**单个 vs 多个选中项**一视同仁，都走 `"$@"`；空选中时 `$@` 为空，脚本开头判一下 `[ $# -eq 0 ] && exit 0`。
- 「不删不覆盖、同名改名避让」是 Python 脚本内部的事，和右键接入无关，按 BRIEF 在脚本里实现即可。
- 一个 `.workflow` 只对应一个入口。**压缩和解压建议做成两个独立快捷操作**（「压缩…」「解压…」），各自逻辑清晰，也符合右键两个菜单项的直觉。

---

## 5. 给最终用户的安装 / 卸载教程该怎么写

分发建议：GitHub Release 里放两个 `.workflow`（压缩、解压）+ 一个 `install.command` 一键脚本 + Python 内核。教程写成「三步走」，越傻瓜越好：

**安装（图形手动版，写给普通用户）**
1. 下载并解压得到 `压缩….workflow` 和 `解压….workflow`。
2. 逐个**双击**，在弹出的「安装快捷操作」对话框点「安装」。（若双击无反应，手动把两个 `.workflow` 拖进「前往文件夹 `~/Library/Services`」）
3. 首次在访达里右键某个文件 → 快捷操作 → 「压缩…」，系统问是否允许访问文件，点**允许**。搞定。

**安装（一键脚本版，`install.command`，给愿意点脚本的人）**
```bash
#!/bin/zsh
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/Library/Services"
cp -R "$SRC/压缩….workflow" "$SRC/解压….workflow" "$HOME/Library/Services/"
xattr -dr com.apple.quarantine "$HOME/Library/Services/压缩….workflow" "$HOME/Library/Services/解压….workflow" 2>/dev/null || true
# 把 Python 内核也拷到固定位置，workflow 里写死这个路径
mkdir -p "$HOME/tools/compress-zip"
cp -R "$SRC/core/"* "$HOME/tools/compress-zip/"
echo "安装完成，访达右键 → 快捷操作 里已出现「压缩…」「解压…」"
```
（用户可能要先给这个 `.command` 执行权限并从「安全性」里放行，教程注明。）

**依赖前置**：教程开头明确「需要先装 Python3 和 7z」，给一行 Homebrew 命令 `brew install python 7-zip`（具体依赖以 02 方案选型为准），并说明 workflow 里解释器路径按 `which python3` 结果填。

**卸载**
1. 打开访达「前往 → 前往文件夹」输入 `~/Library/Services`，删掉 `压缩….workflow`、`解压….workflow`。
2.（可选）删 `~/tools/compress-zip` 和日志 `~/compress-zip.log`。
3. 右键菜单立即不再出现这两项（可能需重开访达窗口）。

**给别人装的注意**：Apple Silicon 和 Intel 的 Homebrew 路径不同（`/opt/homebrew` vs `/usr/local`），workflow 脚本里两条 PATH 都 export 兜底（见 4.1），能免掉大部分「装了却报 command not found」的支持成本。

---

## 附：完整可用的「压缩」快捷操作脚本骨架

放进 Automator「运行 Shell 脚本」（Shell=`/bin/zsh`，传递输入=**作为自变量**）：

```bash
#!/bin/zsh
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PY="$(command -v python3)"          # 兜底；找不到就写死 /opt/homebrew/bin/python3
CORE="$HOME/tools/compress-zip/compress.py"

[ $# -eq 0 ] && exit 0              # 没选东西直接退

# 选格式
fmt=$(osascript -e 'set r to choose from list {"zip","7z","tar.gz"} with prompt "选择压缩格式" default items {"zip"}' -e 'if r is false then return "CANCEL"' -e 'return item 1 of r')
[ "$fmt" = "CANCEL" ] && exit 0

# 选加密
enc=$(osascript -e 'set r to choose from list {"不加密","AES-256 强加密","ZipCrypto 兼容加密"} with prompt "选择加密方式" default items {"不加密"}' -e 'if r is false then return "CANCEL"' -e 'return item 1 of r')
[ "$enc" = "CANCEL" ] && exit 0

pw=""
if [ "$enc" != "不加密" ]; then
    pw=$(osascript -e 'text returned of (display dialog "输入压缩密码" default answer "" with hidden answer)' 2>/dev/null) || exit 0
    [ -z "$pw" ] && { osascript -e 'display alert "密码为空，已取消"'; exit 0; }
fi

# 把所有选中项 + 参数交给 Python 内核；密码走环境变量传（不进 argv、不进 ps 列表更稳）
osascript -e 'display notification "开始压缩…" with title "compress-zip"'
if COMPRESS_PW="$pw" "$PY" "$CORE" --format "$fmt" --encrypt "$enc" -- "$@"; then
    osascript -e 'display notification "压缩完成" with title "compress-zip"'
else
    osascript -e 'display alert "压缩失败" message "查看 ~/compress-zip.log"'
fi
```
> 密码用环境变量 `COMPRESS_PW` 传，而不是命令行参数——避免密码出现在 `ps` 进程列表里被别的用户看到。Python 端 `os.environ.get("COMPRESS_PW")` 读取，用完即弃。

---

## 参考来源
- [Apple 官方 · 在 Mac 访达中执行快捷操作](https://support.apple.com/guide/mac-help/perform-quick-actions-in-the-finder-on-mac-mchl97ff9142/mac)
- [Apple 官方 · Automator 使用快捷操作工作流程](https://support.apple.com/guide/automator/use-quick-action-workflows-aut73234890a/mac)
- [Apple 官方 · 从其他 App 启动快捷指令（Shortcuts 作快捷操作）](https://support.apple.com/guide/shortcuts-mac/launch-a-shortcut-from-another-app-apd163eb9f95/mac)
- [Apple 开发者 · Mac 自动化脚本指南：提示从列表选择](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/PromptforaChoicefromaList.html)
- [Apple 开发者 · Mac 自动化脚本指南：提示选择文件或文件夹](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/PromptforaFileorFolder.html)
- [Automators Talk · Run Shell Script Quick Action 把选中文件传给 CLI](https://talk.automators.fm/t/run-shell-script-quick-action-need-help-scripting-input-file-for-cli-program/5390)
- [Apple Discussions · Automator 传文件名给 shell 脚本](https://discussions.apple.com/thread/2284476)
- [Apple Discussions · 用 Automator 跑 Python3 的 PATH 问题](https://discussions.apple.com/thread/8392208)
- [MacRumors · 在访达里使用快捷操作与自定义右键](https://www.macrumors.com/how-to/use-finder-quick-actions/)
- [MacMost · 自定义 Mac 右键菜单](https://macmost.com/customizing-the-mac-context-menu.html)
- [iMore · 在 Mac 上用 Shortcuts 做快捷操作](https://www.imore.com/how-use-quick-actions-shortcuts-mac)
