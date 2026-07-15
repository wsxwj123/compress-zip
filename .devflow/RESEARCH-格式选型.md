# RESEARCH — 格式与库技术选型

调研时间：2026-07-15
调研方式：官方文档/规范逐条核实 + 本机 Python 3.10 实测验证（非纯转述搜索结果）

---

## 一句话结论

**中文名不乱码这件事，Python 标准库 `zipfile` 自动就做对了，不用你操心**——只要用 `zipfile.ZipFile.write()`/`writestr()` 写入 `str` 类型的中文文件名，它会自动检测"这个名字能不能用旧编码 CP437 表示"，不能就自动切到 UTF-8 并打上标志位。真正的坑不在这里，而在**"加密"这个需求上**：标准库压根不能创建加密 zip，pyzipper 能做 AES 但**做不了 ZipCrypto 写入**；而 macOS 系统自带的 `zip` 命令虽然能做 ZipCrypto，却**做不对中文文件名**（本机实测已复现乱码）。这两条路径互相cover不了对方，是本项目唯一需要"手搓"的地方，下面第 1、2 节详细说明。

---

## 1. 中文名不乱码的技术根因和解法（头号目标）

### 1.1 根因：ZIP 格式的文件名编码历史包袱

一句话人话版：ZIP 格式 1989 年设计时没考虑中文，默认用一种叫 CP437 的老式英文编码存文件名，中文字符编不进去就会变成乱码。后来 ZIP 规范加了一个"开关"——通用位标志（general purpose bit flag）**第 11 位**，叫 **Language Encoding Flag (EFS)**：这一位置 1，就等于告诉解压软件"这个包里的文件名和注释请按 UTF-8 读"；不置这一位，解压软件默认按 CP437（或本地编译码，比如 Windows 上常按 GBK）去读，中文字节被错误解码，就成了乱码。

官方规范原文（PKWARE APPNOTE.TXT）：
> Bit 11: Language encoding flag (EFS). If this bit is set, the filename and comment fields for this file MUST be encoded using UTF-8.

来源：[APPNOTE.TXT - .ZIP File Format Specification](https://pkware.cachefly.net/webdocs/APPNOTE/APPNOTE-6.3.2.TXT)

Windows 解压乱码的真实链条是：某压缩工具没置 bit 11 → Windows 自带解压或老版本工具按系统本地编码（GBK）去解 UTF-8 字节 → 乱码。只要 bit 11 被正确置位，现代解压工具（Windows 10+ 自带压缩体验、7-Zip、WinRAR、Bandizip 等）都会按 UTF-8 正确还原。

### 1.2 Python 标准库 zipfile 的默认行为：自动处理，无需手动设置

**结论先行：会自动设置，不用手动干预。** 这是本项目最关键的一条代码级事实，我做了两件事核实：

**(a) 查官方文档**（[docs.python.org/3/library/zipfile.html](https://docs.python.org/3/library/zipfile.html)）：
> UTF-8 will automatically be used to write the member names if they contain any non-ASCII characters. It is not possible to write member names in any encoding other than ASCII or UTF-8.

**(b) 查 CPython 源码**（[cpython/Lib/zipfile/__init__.py](https://github.com/python/cpython/blob/main/Lib/zipfile/__init__.py)），核心逻辑在 `ZipInfo._encodeFilenameFlags`：
```python
def _encodeFilenameFlags(self):
    if self.flag_bits & _MASK_UTF_FILENAME:
        encoding = 'ascii'
    else:
        encoding = 'cp437'
    try:
        return self.filename.encode(encoding), self.flag_bits & ~_MASK_UTF_FILENAME
    except UnicodeEncodeError:
        return self.filename.encode('utf-8'), self.flag_bits | _MASK_UTF_FILENAME
```
逻辑翻译成人话：先试着用 CP437 编码文件名，中文字符编不进去必然抛 `UnicodeEncodeError`，一旦抛出就自动改用 UTF-8 编码，**同时自动把 `flag_bits` 的第 11 位（`_MASK_UTF_FILENAME = 0x800`）置上**。这个判断对每个文件名自动做，不需要你调用任何额外 API。

**(c) 我自己写代码验证了一遍**（本机 Python 3.10.11，直接跑通）：
```python
import zipfile
with zipfile.ZipFile('test.zip', 'w') as zf:
    zf.writestr('中文文件.txt', 'hello')
zf2 = zipfile.ZipFile('test.zip')
info = zf2.infolist()[0]
print(info.filename, hex(info.flag_bits), bool(info.flag_bits & 0x800))
# 输出：中文文件.txt 0x800 True
```
确认：只要走 `zipfile.ZipFile(...).write()` / `.writestr()`，中文文件名 100% 自动打上 UTF-8 标志位，**不需要手动 `flag_bits |= 0x800`**（网上一些老教程写的手动设置法是给"手动构造 ZipInfo 再用底层写入"的场景用的，正常调用路径完全不需要）。

### 1.3 反面案例：macOS 系统自带 `zip` 命令是不可靠的对照组

这条不是文档调研，是我在本机 `/usr/bin/zip`（Apple 修改版 Info-ZIP 3.0）上实测出来的，**足以说明为什么不能图省事直接 shell 出去调系统 zip 命令**：

```bash
$ zip -e -P test123 test.zip "中文文件.txt"
$ python3 -c "
import zipfile
info = zipfile.ZipFile('test.zip').infolist()[0]
print(repr(info.filename), hex(info.flag_bits))
"
# 输出：'Σ╕¡µûçµûçΣ╗╢.txt' 0x9   ← UTF-8 标志位没置，文件名已经是乱码字节
```
进一步验证：Info-ZIP 官方本该支持的 `-UN=UTF8` 参数在 macOS 的 Apple 定制版上直接报错 `short option 'N' not supported`（Apple 阉割了这个功能）。**结论：macOS 系统自带 zip 命令这条路完全走不通，必须用 Python zipfile（或同源的 pyzipper）自己写，不能 shell 出去调 `/usr/bin/zip`。**

### 1.4 遗留问题：中文名 + ZipCrypto 加密 这个组合，现成库都做不到

这是整个调研里唯一没有"一个库端到端搞定"的组合，必须说清楚：

- Python 标准库 `zipfile`：连创建加密 zip 都不支持（下面 2.1 详述），无从谈起。
- `pyzipper`：我实测了它的加密写入路径（见 2.1），**只支持 AES（`WZ_AES`），不支持传统 ZipCrypto 写入**——不调用 `setencryption()` 直接 `setpassword()` 写入会直接抛 `AttributeError`，说明它压根没实现 ZipCrypto 的加密器类。
- 系统 `zip -e`：能做 ZipCrypto，但如 1.3 所示中文文件名必乱码。

**可行方案**（留给方案阶段 02 决定，这里只列技术选项，不做最终架构决策）：
1. **手搓 ZipCrypto 写入器**：ZipCrypto 算法本身很简单（3 个 32 位 CRC 密钥流），公开算法资料很多，配合 `zipfile.ZipInfo` 手动构造条目（文件名走 1.2 的自动 UTF-8 逻辑没问题，只是数据流加密部分自己实现，写入 `writestr(zinfo, encrypted_bytes)`）——大概 30-50 行代码，无新依赖。
2. 用 `pyminizip`（C 扩展，包 minizip，支持 ZipCrypto 写入）——但该库最后更新在 2018 年左右，对新版 Python 的 wheel 支持存疑，属于不推荐但可探的备选。

方案选择留给 02 方案设计阶段做取舍，本报告先把两条路都摆出来。

---

## 2. 各格式用什么库/工具创建

### 2.1 zip + UTF-8 + 加密

| 需求 | 标准库 zipfile 能做吗 | 说明 |
|---|---|---|
| 创建 zip、写中文名（UTF-8 自动） | ✅ 能 | 见第 1 节 |
| 读取/解密 ZipCrypto 加密包 | ✅ 能 | 但纯 Python 实现，解密很慢（官方文档原话："Decryption is extremely slow as it is implemented in native Python rather than C"） |
| **创建**加密包（任何加密方式） | ❌ 不能 | 官方文档原话："it cannot create an encrypted file" |
| AES 加密 | ❌ 不能 | 同上 |

来源：[docs.python.org/3/library/zipfile.html](https://docs.python.org/3/library/zipfile.html)

**AES-256 加密 zip 用 `pyzipper`**（PyPI: [pyzipper](https://pypi.org/project/pyzipper/)，GitHub: [danifus/pyzipper](https://github.com/danifus/pyzipper)）。它是 fork 自 CPython 3.7 版 zipfile 的增强版，API 与标准库高度兼容，本机实测代码：
```python
import pyzipper
with pyzipper.AESZipFile('out.zip', 'w', compression=pyzipper.ZIP_DEFLATED,
                          encryption=pyzipper.WZ_AES) as zf:
    zf.setpassword(b'your-password')
    zf.writestr('中文文件.txt', 'hello')
```
本机实测确认它同样继承了 zipfile 的 `_encodeFilenameFlags` 自动 UTF-8 逻辑（同一套底层 ZipInfo 代码），中文名同样自动置位，不冲突。AES 强度可选 128/192/256 位，默认 256 位。

**传统 ZipCrypto 兼容加密**：见 1.4，pyzipper 不支持写入，需要手搓或用 pyminizip 兜底。

压缩算法上 `pyzipper` 支持标准库同款的 `ZIP_STORED`/`ZIP_DEFLATED`/`ZIP_BZIP2`/`ZIP_LZMA`（本机 `dir(pyzipper)` 实测确认存在）——**提醒一点**：用 `ZIP_LZMA` 压缩的包，Windows 自带的"压缩文件夹"解压体验不认识 LZMA，需要用户装 7-Zip/WinRAR 才能解；如果想让 Windows 原生解压也能开，建议默认用 `ZIP_DEFLATED`，把 LZMA 作为可选高压缩比选项而非默认值。

### 2.2 7z（含加密）

**用 `py7zr`，不调系统 7z 命令。**

理由：`py7zr` 是较为"纯 Python 生态"的实现（依赖 `PyCryptodomex` 做 AES、`PyPPMd`/`pybcj` 等做特定压缩算法，都是 pip 装的 Python 包，不依赖系统装好 `7z` 二进制），本机验证过 `which 7z` 是空的（系统没装），如果选择调系统命令还要多一道 `brew install p7zip` 的安装门槛，对单人开发者、后续要给别人发布装机教程而言不划算。

创建加密 7z 归档：
```python
import py7zr
with py7zr.SevenZipFile('out.7z', 'w', password='your-password') as z:
    z.writeall('中文目录/')
```
py7zr 支持 LZMA2/LZMA/BZip2/Deflate/ZStandard/PPMd/Delta/BCJ 等压缩filter，以及 AES 加密。Python 版本要求 ≥3.10（本机 3.10.11 满足）。

来源：[py7zr PyPI](https://pypi.org/project/py7zr/)，[py7zr GitHub](https://github.com/miurahr/py7zr)，[py7zr User Guide](https://py7zr.readthedocs.io/en/latest/user_guide.html)

### 2.3 tar.gz

**标准库 `tarfile` 完全够用，不需要第三方库。**
```python
import tarfile
with tarfile.open('out.tar.gz', 'w:gz') as tar:
    tar.add('中文目录/', arcname='中文目录')
```
tar 格式本身按字节存文件名，没有 ZIP 那套"编码标志位"机制，只要打包时用 UTF-8 环境（macOS 默认就是），文件名就是原始 UTF-8 字节，Linux/macOS 上原生按 UTF-8 解读没问题；tar.gz **不支持加密**（tar 格式本身没有加密概念），这跟需求里"tar.gz 只是压缩格式选项之一、加密只针对 zip/7z"的定位一致，故不需要额外处理。

---

## 3. 解压覆盖

| 格式 | 用什么解 | 备注 |
|---|---|---|
| zip（含 AES/ZipCrypto 加密） | `pyzipper`（统一用它就够，向下兼容标准库 zipfile 的读取能力，还多支持 AES 解密） | 不需要额外区分是否加密，`pyzipper.AESZipFile` 可以读普通 zip、ZipCrypto 加密 zip、AES 加密 zip |
| 7z（含加密） | `py7zr` | 同一个库创建/解压都能做 |
| tar.gz | 标准库 `tarfile` | 够用 |
| **rar** | `rarfile` 库（PyPI），但它本身**不解压**，只是调用外部工具做壳 | 见下 |

**rar 解压的关键点**：`rarfile` 库自己不实现 RAR 解压算法（RAR 是专利格式，没有开源实现），它是去调用系统里装好的外部工具，官方文档列出的优先级是 **"unrar (preferred), unar, 7zip or bsdtar"**（来源：[rarfile 官方文档](https://rarfile.readthedocs.io/)）。

**macOS 上怎么装**——这里有个坑要提前说清楚：
- `unrar`（官方推荐、格式支持最全）**已经从 Homebrew 主仓库（homebrew-core）移除**，原因是 unrar 是免费但非开源、许可证限制再分发，不符合 Homebrew 政策（2018 年移除，来源：[Homebrew/homebrew-core PR #66609](https://github.com/Homebrew/homebrew-core/pull/66609)，[Homebrew Discussion #285](https://github.com/orgs/Homebrew/discussions/285)）。现在要装只能用第三方 tap 或去 RARLAB 官网手动下二进制，路径不干净。
- **推荐用 `unar`**（The Unarchiver 项目出的命令行工具），Homebrew 主仓库正常可装：`brew install unar`（本机验证该 formula 存在，当前稳定版 1.10.8，[formulae.brew.sh/formula/unar](https://formulae.brew.sh/formula/unar)）。rarfile 官方文档标注 unar 的限制是"不支持 Windows、不支持 RAR2 的加锁文件"——这两条对 macOS 单人开发者场景都不构成问题。
- macOS 系统自带 `/usr/bin/bsdtar`（本机验证存在，3.5.3 版），rarfile 文档明确标注它对 RAR 格式支持有限（"Not recommended: limited RAR format support"），只能当最后兜底，不作为主力方案。

**结论：rar 解压依赖链 = `pip install rarfile` + `brew install unar`**，两者缺一不可（rarfile 只是调度层，unar 才是真正干活的）。

来源：[rarfile PyPI](https://pypi.org/project/rarfile/)，[rarfile 官方文档](https://rarfile.readthedocs.io/)

---

## 4. 依赖清单（待用户批准安装）

### 4.1 pip 装的 Python 库

| 库 | 用途 | 必须/可选 | 体积/可靠性 |
|---|---|---|---|
| `pyzipper` | zip 创建（AES 加密）+ zip 全场景解压（普通/AES/ZipCrypto 读） | **必须** | 纯 Python，无 C 扩展依赖，体积很小（几十 KB），fork 自 CPython 标准库、活跃维护，可靠性高 |
| `py7zr` | 7z 创建（含加密）+ 解压 | **必须**（需求含 7z） | 中等体积，依赖 `PyCryptodomex`（AES 实现，C 加速，成熟稳定）、`PyPPMd`、`pybcj` 等几个小依赖，社区维护活跃（[miurahr/py7zr](https://github.com/miurahr/py7zr)） |
| `rarfile` | rar 解压的调度层（本身不含解压算法） | **必须**（需求含 rar 解压） | 纯 Python，体积很小，需配合系统工具 `unar` 才能实际工作 |

**不需要装的**：`zipfile`、`tarfile` 是标准库，Python 自带，无需 pip。

**ZipCrypto 写入**如果 02 方案阶段选"手搓实现"，则**不新增任何依赖**（用标准库 `zipfile.ZipInfo` + 自己写的加密函数）；如果选 `pyminizip` 兜底方案，则多一个不推荐但可选的第三方 C 扩展依赖，体积和维护活跃度都不如前三个，建议优先选手搓方案。

### 4.2 brew 装的系统工具

| 工具 | 用途 | 必须/可选 |
|---|---|---|
| `unar` | 给 `rarfile` 库当解压后端，没有它 rar 解压功能完全不可用 | **必须**（需求含 rar 解压） |

**不需要装的**：`p7zip`/`7z` 系统命令（选了 `py7zr` 纯 Python 路线，见 2.2）；`unrar`（Homebrew 已不提供，且 `unar` 已够用，见第 3 节）。

---

## 5. 纯标准库能覆盖多少

按"最小依赖原则"给一张能不能只用标准库的清单：

| 功能 | 标准库能否覆盖 | 说明 |
|---|---|---|
| zip 创建（不加密）、中文名不乱码 | ✅ 全覆盖 | `zipfile`，见第 1 节 |
| zip 读取/解压（含读 ZipCrypto 加密包） | ✅ 全覆盖 | `zipfile` 原生支持解密读取，只是慢 |
| zip **创建**加密包（AES 或 ZipCrypto） | ❌ 不行 | 标准库明确不支持创建加密文件 |
| 7z 创建/解压 | ❌ 不行 | 标准库完全没有 7z 支持 |
| tar.gz 创建/解压 | ✅ 全覆盖 | `tarfile` |
| rar 解压 | ❌ 不行 | 标准库没有任何 RAR 支持，专利格式必须借外部工具 |

**结论**：本项目按"最小依赖"原则已经是最精简的选型了——zip 不加密和 tar.gz 两块标准库全包，剩下"zip 加密创建""7z""rar 解压"这三块是需求本身决定了必须引入第三方（分别对应 pyzipper / py7zr / rarfile+unar），不存在能进一步砍掉的依赖。

---

## 附：与 BRIEF.md 成功标准的对应关系

- 成功标准 1（中文名压 zip 在 Windows 不乱码）→ 第 1 节已给出代码级根因和验证方法，`zipfile`/`pyzipper` 默认路径自动满足，**唯一例外是 ZipCrypto 加密+中文名组合需要手搓**（1.4 节），需在 02 方案阶段拍板。
- 成功标准 3（加密包密码正确/错误行为）→ 技术选型层面 pyzipper/py7zr 均原生支持密码校验失败抛异常，可在开发阶段直接捕获转换成用户提示，不影响本报告结论。
