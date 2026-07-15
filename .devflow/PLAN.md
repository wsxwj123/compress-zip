# PLAN — compress-zip 方案设计

> 定稿日期 2026-07-15。基于 BRIEF.md + 两份 RESEARCH + rules.md。
> 设计原则：最小依赖、不过度工程、优先标准库、好维护。单人自用+开源小工具，不搞企业级框架。
> 对外接口约定单列在 `INTERFACE.md`（交测试设计代理），本文件不重复其全文。

---

## 1. 总体架构（一句话）

**Python 单文件 CLI 内核 + 一个手搓 ZipCrypto 模块 + 两个 Automator 快捷操作外壳。**
osascript 弹窗全部放在快捷操作的 shell 脚本里，Python 内核是纯命令行、无 GUI、可被 pytest 直接黑盒调用。密码走环境变量 `COMPRESS_PW`。

分层职责：

```
访达右键 → Automator .workflow（zsh + osascript 弹窗选格式/加密/路径/密码）
          → 把 Chinese 选项翻译成 none/aes/zipcrypto，密码塞进 COMPRESS_PW
          → python3 czip.py compress|extract <flags> -- <files>
                └─ czip.py：argparse + 分发 + 顶层改名避让 + 解压布局(auto/flatten/folder) + Zip Slip 校验 + 三格式压/解
                     └─ zipcrypto.py：手搓 ZipCrypto 加密写入器（仅 zip+zipcrypto 用到）
```

**为什么 osascript 不放进 Python**：放 shell 里，Python 内核就零 GUI 依赖，pytest 能纯命令行跑通全部逻辑（头号验收、加解密、改名避让都不需要弹窗）。职责清晰、可测性最好。这是拍板决策。

---

## 2. 文件结构

```
compress-zip/
├── czip.py                 # CLI 内核：argparse + compress/extract + 改名避让 + zip/7z/targz 压解
├── zipcrypto.py            # 手搓 ZipCrypto 加密写入器（~40 行）+ __main__ 自检
├── requirements.txt        # pyzipper / py7zr / rarfile
├── quickactions/
│   ├── 压缩.workflow/       # Automator 快捷操作（开发阶段构建）
│   └── 解压.workflow/
├── install.command         # 一键安装：拷 workflow 到 ~/Library/Services，拷内核到 ~/tools/compress-zip
├── tests/
│   └── test_czip.py        # 黑盒测试（03 测试设计代理产出）
└── README.md               # 安装/使用/卸载教程（06 发布）
```

**为什么只有 2 个 Python 文件**（ponytail）：压/解逻辑线性、无 ≥3 次复用，塞进 `czip.py` 一个文件足够；只有 ZipCrypto 加密器是安全敏感、需独立单元自检，才单独拆 `zipcrypto.py`。改名避让是一个小函数、compress/extract 都用，留在 `czip.py` 内即可，不为它单开文件。

---

## 3. 技术选型与理由（拍板）

### 3.1 各格式用什么（来自 RESEARCH-格式选型）

| 能力 | 用什么 | 依赖 |
|---|---|---|
| zip 创建（不加密 / AES） + zip 全场景解压（普通/AES/ZipCrypto 读） | `pyzipper` | pip |
| zip 创建（ZipCrypto 加密） | **手搓 `zipcrypto.py`** | 无（标准库 `zipfile.ZipInfo`） |
| 7z 创建（含 AES）/ 解压 | `py7zr` | pip |
| tar.gz 创建 / 解压 | 标准库 `tarfile` | 无 |
| rar 解压（不创建） | `rarfile` 调度 + 系统 `unar` | pip + brew |

### 3.2 关键决策：ZipCrypto + 中文名 → 手搓，不用 pyminizip（拍板）

**背景**：没有单一现成库能做「ZipCrypto 加密 + 中文名不乱码」。pyzipper 只支持 AES 写入（ZipCrypto 写入直接抛 `AttributeError`）；系统 `/usr/bin/zip -e` 能做 ZipCrypto 但中文名必乱码（本机实测 `0x9`，bit 11 未置位）。

**选手搓，理由**：
1. **零新依赖**：ZipCrypto 算法就是 3 个 32 位 CRC 密钥流，~40 行；文件名仍走 `zipfile.ZipInfo` 的自动 UTF-8 逻辑（bit 11 自动置位），只有数据流加密部分自己实现。
2. **pyminizip 不可靠**：最后更新约 2018，新版 Python wheel 支持存疑，是 C 扩展、装机门槛高，与「最小依赖/易分发」冲突。
3. **可控可测**：自己写的 40 行有独立自检（加密后能被标准库 `zipfile` 用同密码解出、且 bit 11 置位），比赌一个不活跃 C 库的行为更稳。

**手搓边界（ponytail 注释在代码里标）**：只实现 ZipCrypto **加密写入**；解密读取继续交给 pyzipper/标准库（它们原生支持读 ZipCrypto）。不实现自己的解密器。

**手搓实现三个必须钉死的细节**（否则静默产坏包）：
- **加密位与 bit 11 共存（S2）**：给 `flag_bits` 打加密位 `0x1` 必须**按位或** `|= 0x1`，绝不整体赋值——否则清掉 UTF-8 bit 11，加密 zip 中文名又乱码。任务 C 的显式断言点。
- **12 字节加密头 check-byte 约定（S3）**：末字节用 **CRC-32 高字节**（写入前已知完整数据、能先算 CRC，用 CRC 高字节兼容性最好；不用 mod-time 高字节那种流式变体）。
- **不实现 zip64（R3）**：只写 32 位长度字段，**单成员 > 4 GiB 直接退 5 提示改用 AES**（INTERFACE §1.2）。为冷路径加 zip64 不划算；大文件加密走 pyzipper（自动 zip64）。

**自检（S3，进 `zipcrypto.py` 的 `__main__`）**：加密含中文名小文件 → 用**标准库 `zipfile`**（原生读 ZipCrypto）同密码解出、断言内容一致 + `flag_bits & 0x800` 置位 + 错误密码解失败。这三条自动兜住"别的工具解不开/解成乱数据/校验位写错"，无需人工用 7-Zip 点。**> 4GiB 退错路径**用桩（打补丁伪造 size）覆盖，不必真造 4G 文件。

### 3.3 关键事实：中文名不乱码（头号目标）

标准库 `zipfile` 的 `ZipInfo._encodeFilenameFlags` 先试 CP437、中文编不进就自动切 UTF-8 并置 bit 11（0x800），**无需手动 `flag_bits |= 0x800`**。走 `write()`/`writestr()` 即自动生效。tar 按 UTF-8 字节存名，macOS 默认环境无需处理。

**开发时必须验证的点（写进开发代理任务，不可省）**：
- pyzipper（AES 路径）是否同样继承 `_encodeFilenameFlags` 自动置位——RESEARCH 说继承同一套底层代码，但**开发时用中文名压一个 AES 包、断言 bit 11 置位后才算数**。
- 手搓 ZipCrypto 路径：确认经 `ZipInfo` 构造条目后 bit 11 仍自动置位。
- 三种加密方式（none/aes/zipcrypto）各压一个中文名包，都断言 bit 11=置位、文件名 UTF-8 可正确还原。

### 3.4 osascript 弹窗放 shell、密码走 env（拍板）

Automator「运行 Shell 脚本」传递输入设「作为自变量」，选中项直接变 `"$@"`（中文/空格路径零风险）。shell 用 osascript `choose from list` 选格式/加密、`display dialog ... hidden answer` 收密码（圆点不回显）、`choose folder` 选解压路径、`display alert/notification` 报结果。shell 把中文选项翻译成 `none/aes/zipcrypto`，密码经 `COMPRESS_PW=... python3 ...` 传入（不进 argv、不进 ps）。PATH 极简坑：脚本头 `export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"` 兼顾 Apple Silicon/Intel，解释器兜底 `command -v python3`。

### 3.5 压缩命名与包内结构（改，对齐 macOS Finder）

**命名（拍板）**：
- 单选 → 用该项名字（`foo` → `foo.zip`）。
- **多选 → 固定 `归档.zip`**（不再用父目录名）。理由：父目录名会误导——用户可能只选了目录里的部分内容，却压出个以父目录命名的包，像是"整个目录"；多选跨目录时父目录也不唯一。用中性的"归档"最不误导。（接口固化在 INTERFACE §1.3。）

**包内结构（拍板）**：**不加顶层文件夹前缀**，arcname = 所选项自身名字（选 `foo` 文件夹 → 包顶层就是 `foo/…`，不套 `foo/foo/…`），对齐 macOS Finder 的"压缩"。**不写 `.DS_Store` / `__MACOSX/`**（污染包，且会让解压端"顶层项计数"误判）。（INTERFACE §1.3.2。）

**这打破了旧的"原地解压不覆盖源目录"假设，需重新论证解压安全**：旧版靠"压缩加顶层前缀 → 原地解回 `<name>/<name>/…` 嵌套"来天然避开覆盖源目录里的直接文件。现在无前缀，`foo.zip` 原地解压的落地目标 `<dir>/foo` 会直接撞上源 `foo`。解压端的不覆盖改由**三重机制**共同保证（详见 §3.6）：
1. **Zip Slip 校验**——所有落地都被钉在目标目录内，不会写到目录外；
2. **智能默认套壳**——多顶层项自动进包名文件夹，散文件不污染当前目录；
3. **顶层同名改名**——落地顶层项若与已有同名（含撞上源 `foo`）自动改 `foo-1`，绝不覆盖。
压缩端因此可以安心不加前缀。

### 3.6 解压落地布局与安全（改，大改，对齐 The Unarchiver / Keka）

**默认解压位置** = 压缩包所在目录（省略 `--dest`）。

**"顶层项"怎么数（钉死，别数错）**：把每个成员路径反斜杠归一化 + 过滤 `.DS_Store`/`__MACOSX/` 后取**第一路径段**、去重，集合基数=顶层项数。**不能按 `namelist()` 条数数**——否则"单文件夹装 N 文件"被当成 N 项误套壳，还击穿 §3.5 自压包原地解压的不覆盖论证。要同时兼容"有显式目录条目 `foo/`"和"只有 `foo/a.txt` 无目录条目"两种包。（INTERFACE §2.3。）

**智能默认布局（`--layout auto`，默认）**：读顶层项数量决定——
- **0 项**（空包，或过滤元数据后剩 0）→ 不写任何文件，**退 1** + `压缩包为空`（显式定义，避免落进未定义行为；与"过滤元数据"联动）。
- 恰好 1 项 → **铺开**，直接落 `<dest>/`（避免 `归档/归档` 套娃）。
- ≥2 项 → **套一层包名文件夹** `<dest>/<包名>/`（避免散文件污染当前目录）。

**保留手选（拍板 CLI 形式）**：`--layout {auto,flatten,folder}` + `--dest DIR`。
- `auto` 智能默认 / `flatten` 强制铺开 / `folder` 强制套包名文件夹；`--dest` 指定解压父目录。
- 为什么用 `--layout` 枚举而非三个 bool 开关：三态互斥，一个枚举天然不会出现"既 flatten 又 folder"的非法组合，argparse `choices` 直接兜非法值→退 2。（INTERFACE §2.1/§2.3。）

**同名改名 = 顶层项级前缀重写**（不逐成员判重，否则文件夹被拆散/merge 覆盖源）：先按落地目录给顶层项定最终名（撞名 `foo`→`foo-1`），**再把该顶层项下所有成员的落地路径前缀统一从 `foo/**` 重写为 `foo-1/**` 才落盘**。铺开时逐顶层项判、套壳时只判壳文件夹名；**自动改名、不弹窗**。**严禁退化成逐成员判 `<dest>/foo/x` 是否存在**——那样会把包内 `foo/` 逐个 merge 进源 `foo/`、覆盖源里同名文件（重要修订点）。

**新增安全（安全红线，必做）**：
- **拒绝软链接/硬链接成员（致命修订）**：解压时任何成员是 symlink/hardlink → 整包退 1 `压缩包含链接成员`。原因：纯字符串 Zip Slip 校验拦不住"软链先落地、后续成员顺链写到 dest 外"的逃逸——恶意包放 `link`→`/Users/x/.ssh`（校验时 link 名在 dest 内、通过），再放 `link/authorized_keys`（解压前对字符串求 realpath 时 link 尚未落地、也通过），真解压时软链已建好 → OS 顺链把文件写到 dest 外。自用工具取最省：直接拒链接成员。压缩侧本就"跟随链接存目标内容、不存链接本身"（§1.3.1），自压包无链接成员，此拒绝只影响外部包。
- **Zip Slip 防护，逐成员在真实落点复核（不止预扫），全格式（zip/7z/targz/rar）**：每个成员归一化后不含 `..`、不以 `/` 开头，**并在即将写入前对真实落点求 `realpath` 确认仍在落地目录内**（把"解压前字符串预扫一次"改为"每写一个成员对真实落点复核一次"，配合拒链接堵死顺链逃逸）；任一越界 → 整包退 1，目录外零落地。zip/pyzipper 虽内建净化 `..` 仍统一再过一遍，7z/tar/rar 逐成员校验 + 逐成员拒链接（本机 3.10.11 无 `tarfile` 的 `filter='data'`，手动校验）。
- **反斜杠归一化**：外部包成员路径含 `\` 的先转 `/` 再建目录，避免解出带反斜杠的怪文件名；转换后同样过上面全部校验。

**错误契约摘要（详见 INTERFACE §4.2）**：损坏/截断→1 `压缩包损坏或不完整`；不支持格式→5；dest 不可写/写失败→1 `写入失败`；缺密码或密码错→4；越界成员→1；链接成员→1；空包→1。extract 各入口完整错误契约以 INTERFACE §4.2 为准。

---

## 4. 依赖清单（需用户批准安装）

### 4.1 pip（写进 requirements.txt）

| 库 | 用途 | 必须性 |
|---|---|---|
| `pyzipper` | zip 的 AES 创建 + zip 全场景解压读取（普通/AES/ZipCrypto） | 必须 |
| `py7zr` | 7z 创建（含 AES）与解压 | 必须（需求含 7z） |
| `rarfile` | rar 解压调度层（本身不含解压算法，需 unar 后端） | 必须（需求含 rar 解压） |

标准库 `zipfile` / `tarfile` 自带，无需装。ZipCrypto 手搓方案**不新增依赖**。

**带密码 rar 不支持（R2，拍板）**：rarfile 调 `unar` 子进程解密时会把密码作为命令行参数传给 unar → 落进 `ps`，违背"密码绝不进 argv/ps"承诺；无廉价的非 argv 传密码路径。故解 rar 前用 `rarfile.RarFile.needs_password()` 探测，加密 rar 直接退 5 声明不支持（INTERFACE §2.2/§4.2）。普通 rar 正常解。配合 §6.2 的启动即 `os.environ.pop('COMPRESS_PW')`，unar 子进程也不会从环境变量继承到密码。

### 4.2 brew

| 工具 | 用途 | 必须性 |
|---|---|---|
| `unar` | 给 rarfile 当 rar 解压后端；无它 rar 功能不可用 | 必须（需求含 rar 解压） |

不装：`p7zip`/`7z`（走 py7zr 纯 Python 路线）；`unrar`（Homebrew 已移除，unar 已够）。

> 安装命令（待用户批准执行）：`pip install pyzipper py7zr rarfile` + `brew install unar`。

---

## 5. 任务拆解（标注并行）

> 依赖关系：A 是地基，B/C/D/E 互不依赖可并行，F 依赖内核成型，G 靠用户本机实测。

| # | 任务 | 依赖 | 可并行 | 交付/验证 |
|---|---|---|---|---|
| A | `czip.py` 骨架：argparse 两子命令（含 `--layout` 枚举）、退出码框架、`错误:` 输出、顶层改名避让函数、Zip Slip 校验 + 反斜杠归一化工具函数 | — | 起步串行 | 非法参数/非法 `--layout`→2、不存在输入→3、改名避让单测、越界成员被拒单测 |
| B | zip 压缩：none/aes（pyzipper）+ 无顶层前缀（arcname=所选项名）+ 过滤 `.DS_Store`/`__MACOSX` + 多选命名`归档` + 中文名 bit 11 验证 | A | ∥ | 中文名压包断言 bit 11 置位、包内无前缀、无 macOS 元数据、多选名=`归档` |
| C | `zipcrypto.py` 手搓 ZipCrypto 写入器 + zip zipcrypto 压缩接入 | A | ∥ | 自检：加密包被标准库同密码解出、bit 11 置位 |
| D | 7z 压/解（py7zr，none/aes）+ targz 压/解（tarfile）；压缩侧同样无前缀/过滤元数据 | A | ∥ | 压解闭环、targz+加密→5、7z+zipcrypto→5 |
| E | 解压布局：顶层项按"第一路径段去重"计数（含 0 项空包→退1）+ `auto`（单项铺开/多项套壳）+ `flatten`/`folder` + 顶层项级前缀重写改名 + 拒链接成员 + Zip Slip 全格式逐成员真实落点复核 + 反斜杠归一化；zip（pyzipper 读三态）+ rar（rarfile+unar，缺 unar→6、带密码 rar→5） | A | ∥ | 单文件夹多文件包 auto 判 1 项铺开、空包→1 `压缩包为空`、auto/flatten/folder 三布局正确、原地解自压包（多文件文件夹）源零改动+新落 `foo-1/**`、各格式解出一致、错误密码→4、缺 unar→6、`../`/绝对路径/反斜杠越界→1、**软/硬链接成员→1 且 dest 外零落地**、空文件夹解出保留 |
| F | 两个 `.workflow` + osascript 外壳 + `install.command` | B–E 成型 | 串行 | 用户本机右键触发 |
| G | 访达右键实测（压缩/解压/中文名/加密） | F | 用户侧 | 07 收尾 |

内核黑盒测试（tests/test_czip.py）由 03 测试设计代理据 INTERFACE.md 产出，与 B–E 并行推进。

---

## 6. 风险清单

> 按 rules.md：每个非机械改动 ≥1 失败模式+缓解；高风险（安全/多文件）≥2；BRIEF 敏感面每项配一句怎么不越权/不泄露。

### 6.1 技术失败模式

| 风险点 | 失败模式 | 缓解 |
|---|---|---|
| 中文名 bit 11（头号）| pyzipper AES 路径或手搓路径没自动置位 → Windows 乱码，头号目标失守 | 三种加密方式各写中文名包、断言 `flag_bits & 0x800`；作为验收硬门槛，不过不发布 |
| **手搓 ZipCrypto（安全敏感，≥2）** | ① CRC 密钥流/字节序写错 → 生成的包别的工具解不开或解出乱数据 | 自检：标准库 `zipfile` 用同密码解密比对原文一致；再用 7-Zip/系统解压交叉验证一次 |
| | ② 加密头 12 字节校验字段写错 → 正确密码也报密码错 | 自检覆盖「正确密码解成功 + 错误密码失败」两条路径 |
| pyzipper/py7zr 行为差异 | 某库解密失败抛的异常类型与预期不符 → 错误密码没映射成退出码 4，泄成码 1 | 捕获各库解密异常统一转码 4；测试用错误密码断言退出 4 |
| rar 依赖 unar | 用户没装 unar → rarfile 抛底层异常，用户看不懂 | 解 rar 前探测 `unar` 是否在 PATH，缺失直接退 6 + 明确提示 `brew install unar` |
| **带密码 rar 泄密（R2）** | rarfile→unar 把密码放 argv → `ps` 可见，违背密钥红线 | 解 rar 前 `needs_password()` 探测，加密 rar 退 5 声明不支持；不给 unar 传密码 |
| **Zip Slip 目录穿越（S1，安全，≥2，全格式）** | ① 解他人 zip/7z/tar/rar 包，成员名含 `../`、绝对路径或反斜杠拼出的越界路径 → 文件写到 dest 外，覆盖系统文件 | 全格式统一校验：归一化后不含 `..`、不以 `/` 开头、**即将写入前对真实落点 `realpath` 复核**仍在落地目录内，逃逸成员退 1 整包拒绝；zip/pyzipper 内建净化仍再过一遍，7z/tar/rar 逐成员校验（本机 3.10.11 无 `filter='data'`，手动校验）；测试对四格式各构造恶意包断言 dest 外零落地 |
| | ② 外部包路径用 `\`（Windows 风格）→ 解出带反斜杠的怪文件名，或绕过只查 `/` 的校验 | 建目录前先把 `\` 转 `/` 归一化，再走同一套 Zip Slip 校验；测试构造反斜杠越界成员断言被拒 |
| **软/硬链接成员顺链逃逸（致命，安全）** | 恶意包放软链 `link`→dest 外目录（校验时 link 名在 dest 内、字符串预扫时 link 尚未落地，均通过），再放成员 `link/authorized_keys` → 真解压时软链已建好，OS 顺链把文件写到 dest 外 | 解压时**拒绝一切 symlink/hardlink 成员**（tar SYM/LNK、zip `S_ISLNK` 模式位、7z/rar 链接属性）→ 整包退 1 `压缩包含链接成员`；配合 realpath 逐成员真实落点复核；自压包本就无链接成员，只影响外部包；测试造经典"软链+顺链写"逃逸包断言 dest 外零落地 |
| 无顶层前缀后原地解压覆盖源（布局，安全相关） | 压缩不再加前缀，`foo.zip`（顶层单文件夹）原地解压落地 `<dir>/foo` 撞源 `foo` → 若逐成员判存在会把包内文件 merge 进源、覆盖同名 | 顶层项级前缀重写：整项定名 `foo`→`foo-1` 后统一把 `foo/**` 落地路径重写为 `foo-1/**` 才落盘，绝不逐成员 merge；测试用多文件文件夹原地解自压包，断言源 `foo/` 零改动、新落 `foo-1/**` |
| 智能布局顶层项计数误判 | ① 按 `namelist()` 条数数 → 单文件夹多文件包被当成多项误套壳、且原地解压不覆盖论证被击穿；② 外部包混入 `.DS_Store`/隐藏项 → 本该"单项铺开"被算成多项 | ① 顶层项按"成员第一路径段去重"数、兼容有无显式目录条目两种包，任务E单测"单文件夹多文件→判1项铺开"；② 计数前先过滤 `.DS_Store`/`__MACOSX`（自压包本就不写）；仍误判则套壳属偏保守（不丢不覆盖），`--layout flatten` 兜底 |
| 空包（0 项）落进未定义行为 | auto 只有"1 项"和"≥2 项"分支，空包或过滤元数据后剩 0 项无分支处理 | 显式定义 0 项 → 不写文件、退 1 `压缩包为空`；边界测试覆盖真空包与"仅含 .DS_Store"包 |
| 快捷操作 PATH 极简 | workflow 里 `python3` 找不到 → command not found | 脚本头 export homebrew+usrlocal 双路径，解释器 `command -v` 兜底；教程写明按 `which python3` 填 |
| ZIP_LZMA 兼容性 | 默认用 LZMA → Windows 自带解压不认 | zip 默认 `ZIP_DEFLATED`（Windows 原生可解），LZMA 不做默认 |

### 6.2 BRIEF 敏感面（不越权/不泄露，逐条）

| 敏感面 | 怎么守 |
|---|---|
| 碰哪些文件：读选中项、写压缩包到源目录、解压写到目标目录 | 只读输入、只写新产物；**绝不删除/覆盖原文件**——压缩包同名 `-N` 改名避让，解压落全新 `-N` 子文件夹（INTERFACE §1.4/§2.3 已固化为契约）|
| 密码 | 只走环境变量 `COMPRESS_PW`，绝不进 argv/ps；**绝不落盘、绝不写日志、绝不明文留存**，读后即用即弃；调试日志重定向也绝不打印密码。**启动即清（S5）**：内核入口第一步 `pw = os.environ.pop('COMPRESS_PW', '')` 读出即从环境删除，缩短暴露窗口，也确保后续 spawn 的子进程（如 unar）不继承密码 |
| 外发数据 | 无。纯本地，不联网、不外发；内核不含任何网络调用 |

### 6.3 失败模式说不出=没理解

以上每项都能给出具体触发条件与验证手段；开发阶段若遇到说不清失败模式的改动，按 rules.md 停下调查，不硬写。

---

## 7. 与成功标准对照

| BRIEF 成功标准 | 本方案如何满足 |
|---|---|
| ★中文名压 zip Windows 不乱码 | zipfile/pyzipper 自动 UTF-8+bit 11；三加密方式验收断言（§3.3、§6.1）|
| 访达右键触发、普通用户能装 | 两个 .workflow + install.command + README 教程（§2、任务 F）|
| 加密包正确密码解开、错误有提示 | pyzipper/py7zr/手搓均校验密码，错误统一退 4（INTERFACE §4）|
| 单/多文件混选正确打包（多选默认名 `归档`、不加顶层前缀）| argparse 收 `PATH ...`；单选用项名、多选用 `归档`、arcname 无前缀、过滤 macOS 元数据（§3.5，任务 B–D 覆盖）|
| 解压智能默认+手选、同名改名作用在顶层项、不覆盖 | `--layout auto/flatten/folder` + `--dest`；顶层同名改 `-N`（§3.6、INTERFACE §2.3）|
| Zip Slip 恶意包解压被拒、目录外零落地（安全红线，全格式）| 解压前全格式统一路径校验 + 反斜杠归一化，逃逸退 1（§3.6、§6.1、INTERFACE §2.3/§4.2）|
