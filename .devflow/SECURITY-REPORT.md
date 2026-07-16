# 安全审查报告 — compress-zip

审查依据：源码目录 + `.devflow/BRIEF.md`（含敏感面声明）。不看 git 历史、不看 `.devflow/` 其他产物、不看开发过程对话。
审查范围：`czip.py`、`zipcrypto.py`、`quickactions/*/Contents/document.wflow`、`install.command`、`requirements.txt`。

---

## 结论先行

**需修复后再发布。** 内核（czip.py / zipcrypto.py）本身干净、Zip Slip 防护到位、不联网、密码不落盘；但两个快捷操作外壳把**文件名拼进 `osascript -e` 的 AppleScript 字符串**，构成命令注入——解压别人发来的、文件名精心构造的压缩包时可执行任意代码。这一条必须先修。

---

## 致命

### C1. AppleScript 注入 → 任意代码执行（快捷操作外壳）
- **证据**：
  - `quickactions/解压.workflow/Contents/document.wflow:89` —— `osascript -e "display alert \"解压失败：$(basename "$arc")\" message \"$(cat "$ERRF")\""`
  - `quickactions/压缩.workflow/Contents/document.wflow:99` —— `osascript -e "display notification \"完成：$(basename "$OUT")\" ..."`
  - `quickactions/压缩.workflow/Contents/document.wflow:101` —— `osascript -e "display alert \"压缩失败\" message \"$(cat "$ERRF")\""`
- **人话讲危害**：这几行把文件名/输出路径直接塞进一段 AppleScript 文本里去执行。文件名里只要带一个英文双引号，就能把 AppleScript 的字符串"闭合"掉，后面接自己的 AppleScript（比如 `do shell script "..."`）。实测：一个名叫 `evil" & "X` 的包，拼出来的脚本就变成 `display alert "解压失败：evil" & "X"` —— 双引号提前闭合、`& "X"` 成了 AppleScript 拼接语法。攻击者把恶意脚本塞进文件名，做一个会"解压失败"的坏包（比如损坏包、带密码的 rar）发给受害者，受害者一右键解压，失败弹窗一弹，脚本就跑了。**解压路径的文件名完全由攻击者控制（外来下载的包），可利用性高。** 压缩路径受害面小一些（用户压自己的文件），但同样成立。
- **修法**：绝不把不可信数据拼进 `osascript -e` 字符串。改成通过 argv 传参，AppleScript 里用 `item 1 of argv` 取值，例如：
  ```zsh
  osascript - "$(basename "$arc")" "$(cat "$ERRF")" <<'EOF'
  on run argv
    display alert ("解压失败：" & (item 1 of argv)) message (item 2 of argv)
  end run
  EOF
  ```
  这样文件名/错误文本只是数据、不参与脚本解析。三处（解压 89、压缩 99/101）都要改。

---

## 重要

（无。核内 Zip Slip、密码处理、删除范围、install.command 均未发现重要级问题——见下方"核对结果"。）

---

## 建议

### S1. `_collect_members` 的 macOS 元数据跳过挡在 `..` 校验之前（czip.py:506-509）
- **证据**：`if any(_is_macos_junk(s) for s in segs): continue` 在 `if ... ".." in segs: raise` 之前。含 `__MACOSX` 或 `.DS_Store` 段的成员（如 `__MACOSX/../../evil`）会被当垃圾直接跳过，`..` 校验根本不跑。
- **人话讲危害**：对 zip/tar/rar 无害（这类成员本来就不写盘）。唯一有理论风险的是 7z——`_SevenZipSource.prepare()` 走 `self.z.extractall(self.raw)`（czip.py:396）整包解到临时目录，会解出被跳过的那个 `..` 成员。**实测 py7zr 1.1.3 自己会拦 `..`（抛 Bad7zFile），所以当前锁定版本下不可利用**；但这是靠依赖库兜底，本工具自己的校验有逻辑缝。
- **修法**：把 `..` / 绝对路径校验移到 macOS 垃圾跳过之前，让所有成员先过 Zip Slip 再谈是否是垃圾。纵深防御，别把安全红线的成立寄托在 py7zr 版本行为上。

### S2. 压缩跟随 symlink 会把树外文件内容装进包（BRIEF 已声明，提示文档化）
- **证据**：czip.py:93 `os.walk(..., followlinks=True)`、:259 `tarfile.open(..., dereference=True)`、:241 7z 对软链取 `realpath`。BRIEF §1.3.1 明确声明"symlink 跟随、存目标内容"。
- **人话讲危害**：在声明范围内、非缺陷。但用户压一个含指向 `~/.ssh/id_rsa` 之类软链的文件夹时，敏感文件内容会被静默打进包。建议在使用教程里点一句，避免用户误分享。

### S3. 密码经子进程环境变量传递，同机可被自己/ root 用 `ps -E` 看到（可接受）
- **证据**：workflow `COMPRESS_PW="$PW" "$PY" "$CORE" ...`；czip.py:653 `os.environ.pop("COMPRESS_PW")` 启动即取走。
- **人话讲危害**：密码不进 argv（`ps` 默认看不到）、不落盘、不写日志、启动即从环境删除、子进程不继承——处理得当。残留窗口只在进程环境里、且只有同一用户或 root 能读（macOS `ps eww`/`ps -E`）。对本地单机工具属可接受威胁模型，标准做法。无需改，登记备案。

---

## 核对结果（逐条对照审查清单 + BRIEF 敏感面声明）

| 项 | 结论 | 证据 |
|---|---|---|
| A1 注入（shell） | **未命中** | 内核调用走 `-- "$@"` argv 传参，文件名是参数不是命令串，无 shell 注入。czip 内部无 `os.system`/`subprocess`/shell=True |
| A1 注入（osascript） | **命中·致命** | 见 C1，三处 `osascript -e` 字符串插值 |
| A2 密钥硬编码 | **未命中** | 无写死凭证。zipcrypto.py:51 的 `0x12345678/0x23456789/0x34567890` 是 ZipCrypto 规范固定初始密钥常量，非密码。无 `.env` 文件（也就无从泄露） |
| A3 不安全解析 | **未命中** | 全目录无 `eval`/`pickle`/`yaml`/`marshal`/`os.system`。tar 不用 `extractall`（手工遍历+校验）；7z 的 `extractall` 前置全包 `..`/链接校验 |
| A4 依赖 | **未命中** | pyzipper 0.4.0 / py7zr 1.1.3 / rarfile 4.3，均主流库；rarfile 只解压、带密码 rar 直接拒（czip.py:432-435），外部 `unar` 走 argv 非 shell |
| A5 提示词注入 | **不适用** | 非 AI 应用 |
| B6 读写范围 | **合规**（1 处建议） | Zip Slip 防护：全包先拒一切软/硬链接成员（czip.py:498-500）+ 拒 `..`/绝对路径（:509）+ 写入前 `realpath` 复核仍在落地目录内（:583-585）+ 先写隔离临时目录成功才 rename（:570,595）。跟随 symlink 见 S2 |
| B7 删除操作 | **未命中** | 无 `rm -rf` 用户目录。`_rmtree`/`_cleanup` 只删本工具建的临时目录和压缩失败的半成品（czip.py:192-198,621-627）；`avoid_collision` 保证不覆盖同名（:57-73）；workflow `trap` 只删自己的 mktemp 错误文件 |
| B8 数据外发 | **未命中** | 全目录零网络代码（无 urllib/requests/socket/http）。符合 BRIEF §3"纯本地、不联网" |
| B9 日志泄露 | **未命中** | 密码不 print、不入错误文案、不写文件。czip 错误只输出 `错误: <msg>`，各文案不含密码；stderr 写入 ERRF 供弹窗但无密码。见 S3 |
| B10 凭证存储 | **未命中** | 密码不落盘、不入包元数据明文、不进 git，用完即弃 |
| **核心判据·install.command** | **未命中（干净）** | 只写 `~/tools/compress-zip`（内核）和 `~/Library/Services`（快捷操作），**均在用户家目录，未碰任何系统敏感位置，全程无 sudo**；`xattr -dr com.apple.quarantine` 仅作用于自己刚装的两个 workflow（install.command:20）；依赖只检测不自动装（:24-38）。完全符合 BRIEF 声明 |

**核心判据总评**：程序实际动的东西**未超出 BRIEF 敏感面声明**——读选中输入、写包到源目录、解压写目标目录、绝不删/覆盖原文件、不联网、密码不落盘，逐条对上。唯一越界风险来自 C1 的 osascript 注入（属外壳层缺陷，非内核越权），修掉即合规。

---

## 发布判定

**需修复后再发布** —— 阻断项仅 C1（AppleScript 注入）。修掉 C1 后可发布；S1 建议一并修（纵深防御），S2/S3 文档化即可。
