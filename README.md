# compress-zip

macOS 通用压缩/解压工具。命令行内核 + 访达右键集成。

**头号目标**：中文名文件压缩后，在 Windows 上解压**不乱码**（ZIP 写入 UTF-8 标志位 bit 11）。

## 能做什么

- **压缩**：zip / 7z / tar.gz，可选 AES-256 或 ZipCrypto 加密
- **解压**：广覆盖，含 rar（需 `unar`）
- **原文件绝不删除/覆盖**：同名自动改名避让
- **安全**：Zip Slip 路径校验、拒绝压缩包内的软/硬链接成员、反斜杠归一化

## 安装

```
双击 install.command
```

它会：① 把内核+脚本装到 `~/tools/compress-zip`；② 编译一个后台小 App
（`CompressZip.app`）用 macOS「服务」机制注册右键菜单。

依赖（装在你日常用的 python 里）：

```
pip3 install pyzipper py7zr rarfile
brew install unar          # rar 解压需要
```

需要 Xcode 命令行工具编译壳 App：`xcode-select --install`。

## 用法

访达里右键文件/文件夹 → 最下方**「服务」**子菜单：

| 菜单项 | 行为 |
|---|---|
| 压缩…（compress-zip） | 一键压成 zip、不加密，零弹窗 |
| 解压…（compress-zip） | 解到压缩包所在目录；加密包才弹密码框 |

**嫌菜单深？** 系统设置 → 键盘 → 键盘快捷键 → 服务，给它俩绑快捷键，
选中文件按键即压/解，任何文件夹（含 OneDrive）都灵。

### 命令行

```
czip.py compress --format zip --encrypt none -- 文件1 文件2   # 多选默认输出 归档.zip
czip.py extract  [--dest 目标目录] [--layout auto|flatten|folder] -- 包.zip
```

密码走环境变量 `COMPRESS_PW`（不进命令行参数、不落盘、不进日志）。退出码：
0 成功 / 1 内部错 / 2 用法错 / 3 找不到输入 / 4 密码错或损坏 / 5 不支持 / 6 缺依赖。

## 为什么用「服务」而不是右键增强 App

Menuist、超级右键这类右键增强 App 靠 **Finder Sync 扩展**，而这类扩展在
OneDrive / iCloud 等云盘文件夹里**一律失效**——云盘目录被系统 File Provider
独占，第三方 Finder Sync 进不去（苹果官方确认的设计限制）。macOS「服务」
不受此限，跟着"选中的文件"走，云盘文件夹照常可用。代价：只能在「服务」
子菜单里，靠快捷键弥补。

## 已知局限

- 默认原地解压**外部**「无顶层目录的扁平包」到已存在同名目录时，可能覆盖同名文件（本工具自压的包无此问题）
- 带密码的 rar 不支持
- 外部非 UTF-8 编码的旧包，文件名可能仍乱码（源头信息已丢失，无法还原）
