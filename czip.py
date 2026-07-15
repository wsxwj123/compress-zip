#!/usr/bin/env python3
"""compress-zip 命令行内核。

两个子命令 compress / extract，纯命令行、无 GUI（osascript 弹窗在 Automator 外壳里）。
契约见 .devflow/INTERFACE.md：格式 zip/7z/targz、加密 none/aes/zipcrypto、
退出码 0-6、错误文案、密码走环境变量 COMPRESS_PW（启动即 pop）、不删不覆盖改名避让、
中文 UTF-8 bit11、tar-slip 防护。
"""
import argparse
import os
import shutil
import sys
import tempfile
import zipfile
import zlib

# 手搓 ZipCrypto 写入器（同目录），仅 zip+zipcrypto 用到
import zipcrypto

# 退出码（INTERFACE §3）
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2      # argparse 自己用
EXIT_NOT_FOUND = 3
EXIT_PASSWORD = 4
EXIT_UNSUPPORTED = 5
EXIT_DEP = 6


class CzipError(Exception):
    """业务错误：带退出码 + 会拼进 `错误: <msg>` 的说明。"""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# ---------- 通用工具 ----------

def _split_archive_ext(name):
    """拆出「基础名, 扩展名」，.tar.gz / .tgz 视为整体扩展名。"""
    low = name.lower()
    if low.endswith(".tar.gz"):
        return name[:-7], name[-7:]
    if low.endswith(".tgz"):
        return name[:-4], name[-4:]
    stem, ext = os.path.splitext(name)
    return stem, ext


def _archive_basename(name):
    """解压子文件夹名 = 压缩包去扩展名。"""
    return _split_archive_ext(name)[0]


def avoid_collision(path):
    """目标已存在则改名避让：name.ext → name-1.ext → name-2.ext。
    目录（无扩展名）→ name → name-1。.tar.gz 视为整体扩展名。"""
    if not os.path.exists(path):
        return path
    parent = os.path.dirname(path)
    base = os.path.basename(path)
    if os.path.isdir(path):
        stem, ext = base, ""
    else:
        stem, ext = _split_archive_ext(base)
    n = 1
    while True:
        cand = os.path.join(parent, f"{stem}-{n}{ext}")
        if not os.path.exists(cand):
            return cand
        n += 1


def _is_macos_junk(name):
    """macOS 元数据：.DS_Store（任意层）或 __MACOSX 目录（§1.3.2，不写进包）。"""
    return name == ".DS_Store" or name == "__MACOSX"


def collect_entries(inputs):
    """遍历输入，产出 [(src_path_or_None, arcname, is_dir)]。
    - 目录：递归；仅「叶子空目录」显式产出目录条目（非空目录由文件路径隐含）。
    - symlink 跟随（followlinks / 目录跟随、文件 open 跟随），存目标内容（§1.3.1）。
    - arcname 前缀 = 输入的 basename（不加额外顶层前缀）。
    - 不写 macOS 元数据 .DS_Store / __MACOSX（§1.3.2）。
    """
    entries = []
    for inp in inputs:
        base = os.path.basename(os.path.normpath(inp))
        if os.path.isdir(inp):  # os.path.isdir 跟随 symlink
            seen = set()  # 防循环 symlink 无限递归（记 (dev, ino)）
            for dirpath, dirnames, filenames in os.walk(inp, followlinks=True):
                st = os.stat(dirpath)
                key = (st.st_dev, st.st_ino)
                if key in seen:
                    dirnames[:] = []  # 已访问过的真实目录，不再深入
                    continue
                seen.add(key)
                dirnames[:] = [d for d in dirnames if not _is_macos_junk(d)]
                rel = os.path.relpath(dirpath, inp)
                arcdir = base if rel == "." else os.path.join(base, rel)
                arcdir = arcdir.replace(os.sep, "/")
                if not dirnames and not filenames:
                    entries.append((None, arcdir + "/", True))
                for fn in sorted(filenames):
                    if _is_macos_junk(fn):
                        continue
                    full = os.path.join(dirpath, fn)
                    arc = (arcdir + "/" + fn) if rel != "." else (base + "/" + fn)
                    entries.append((full, arc, False))
        else:
            if _is_macos_junk(base):
                continue
            entries.append((inp, base, False))
    return entries


# ---------- 依赖导入（缺失 → 退 6） ----------

def _require(module_name):
    try:
        return __import__(module_name)
    except ImportError:
        raise CzipError(
            EXIT_DEP,
            f"缺少依赖库 {module_name}，请先 pip install {module_name}")


# ---------- compress ----------

def derive_output_path(inputs, fmt):
    """省略 --out 时推导输出完整路径（INTERFACE §1.3）。"""
    ext = {"zip": ".zip", "7z": ".7z", "targz": ".tar.gz"}[fmt]
    first = inputs[0]
    out_dir = os.path.dirname(os.path.abspath(first))
    if len(inputs) == 1:
        stem = os.path.basename(os.path.normpath(first))
    else:
        # 多选（无论同目录/跨目录）→ 固定基础名 归档（§1.3）
        stem = "归档"
    return os.path.join(out_dir, stem + ext)


def do_compress(args, pw):
    fmt = args.format
    encrypt = args.encrypt

    # 1) 格式×加密组合合法性（→ 5），先于密码/输入校验（§3 校验顺序）
    if fmt == "targz" and encrypt != "none":
        raise CzipError(EXIT_UNSUPPORTED, "tar.gz 不支持加密")
    if fmt == "7z" and encrypt == "zipcrypto":
        raise CzipError(EXIT_UNSUPPORTED, "7z 不支持 ZipCrypto 加密")

    # 2) 密码存在性（→ 4）
    if encrypt != "none" and not pw:
        raise CzipError(EXIT_PASSWORD, "该加密方式需要密码，但未提供")

    # 3) 输入存在性（→ 3）。用 exists（跟随 symlink）：悬空软链指向的目标不存在，
    #    §1.3.1 要存目标内容却无目标可存，语义上就是「找不到输入」。
    for p in args.paths:
        if not os.path.exists(p):
            raise CzipError(EXIT_NOT_FOUND, f"找不到输入: {p}")

    # 4) 输出路径 + 改名避让
    out = args.out if args.out else derive_output_path(args.paths, fmt)
    out = os.path.abspath(out)
    out = avoid_collision(out)

    # 5) 实际压缩
    try:
        if fmt == "zip":
            _compress_zip(args.paths, out, encrypt, pw)
        elif fmt == "7z":
            _compress_7z(args.paths, out, encrypt, pw)
        else:
            _compress_targz(args.paths, out)
    except CzipError:
        raise
    except zipcrypto.Over4GiBError:
        _cleanup(out)
        raise CzipError(EXIT_UNSUPPORTED,
                        "ZipCrypto 不支持超过 4GB 的单文件，请改用 AES")
    except OSError:
        _cleanup(out)
        raise CzipError(EXIT_INTERNAL, "写入失败")

    print(out)
    return EXIT_OK


def _cleanup(path):
    """压缩失败时删掉半成品，避免留下坏包。"""
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _compress_zip(inputs, out, encrypt, pw):
    entries = collect_entries(inputs)
    if encrypt == "zipcrypto":
        zipcrypto.write_zipcrypto(out, entries, pw.encode("utf-8"))
        return
    if encrypt == "aes":
        pyzipper = _require("pyzipper")
        with pyzipper.AESZipFile(out, "w", compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(pw.encode("utf-8"))
            _write_zip_entries(zf, entries)
        return
    # none：标准库，Windows 原生可解的 DEFLATE
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_zip_entries(zf, entries)


def _write_zip_entries(zf, entries):
    for src, arc, is_dir in entries:
        if is_dir:
            zf.writestr(zipfile.ZipInfo(arc), b"")  # 空目录条目：空内容
        else:
            zf.write(src, arc)


def _compress_7z(inputs, out, encrypt, pw):
    # py7zr 默认存 symlink 本身（实测），违背 §1.3.1「三格式一致跟随链接存目标内容」，
    # 故走 collect_entries 并对软链取 realpath，与 zip/targz 的解引用行为对齐。
    py7zr = _require("py7zr")
    kw = {"password": pw} if encrypt == "aes" else {}
    entries = collect_entries(inputs)
    empty_dir = None
    try:
        with py7zr.SevenZipFile(out, "w", **kw) as z:
            for src, arc, is_dir in entries:
                if is_dir:
                    if empty_dir is None:
                        empty_dir = tempfile.mkdtemp(prefix=".czip-7z-")
                    z.write(empty_dir, arcname=arc.rstrip("/"))  # 空目录占位
                else:
                    real = os.path.realpath(src) if os.path.islink(src) else src
                    z.write(real, arcname=arc)
    finally:
        if empty_dir:
            _rmtree(empty_dir)


def _compress_targz(inputs, out):
    import tarfile

    def _filter(ti):
        # 不写 macOS 元数据（§1.3.2）
        for seg in ti.name.split("/"):
            if _is_macos_junk(seg):
                return None
        return ti

    # dereference=True：跟随 symlink 存目标内容（§1.3.1）
    with tarfile.open(out, "w:gz", dereference=True) as tar:
        for inp in inputs:
            base = os.path.basename(os.path.normpath(inp))
            tar.add(inp, arcname=base, filter=_filter)


# ---------- extract ----------

def _detect_format(archive):
    low = archive.lower()
    if low.endswith(".zip"):
        return "zip"
    if low.endswith(".7z"):
        return "7z"
    if low.endswith(".tar.gz") or low.endswith(".tgz"):
        return "targz"
    if low.endswith(".rar"):
        return "rar"
    return None


class _M:
    """规范化后的成员描述（跨格式统一）。h 为格式原生句柄，供 read 用。"""
    __slots__ = ("name", "is_dir", "is_link", "h")

    def __init__(self, name, is_dir, is_link, h):
        self.name = name
        self.is_dir = is_dir
        self.is_link = is_link
        self.h = h


def _looks_like_password_error(exc):
    """只认明确的密码/解密失败为 4；CRC/损坏类归 1（INTERFACE §4.2）。"""
    s = (str(exc) + " " + type(exc).__name__).lower()
    return "password" in s or "decrypt" in s


def _assert_safe_members(names, dest):
    """逐成员校验解出真实路径落在 dest 内，含 ../ 或绝对路径 → 拒绝（tar-slip）。
    在写盘前调用：拒绝时临时目录尚空，逃逸成员绝不落地。"""
    base = os.path.abspath(dest)
    for name in names:
        real = os.path.abspath(os.path.join(base, name))
        if real != base and not real.startswith(base + os.sep):
            raise CzipError(EXIT_INTERNAL, "压缩包含非法路径，已拒绝")


class _ZipSource:
    def __init__(self, archive, pw):
        pyzipper = _require("pyzipper")
        try:
            self.zf = pyzipper.AESZipFile(archive)
        except (zipfile.BadZipFile, pyzipper.BadZipFile, OSError):
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
        self.encrypted = any(zi.flag_bits & 0x1 for zi in self.zf.infolist())
        if self.encrypted and not pw:
            self.zf.close()
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        if pw:
            self.zf.setpassword(pw.encode("utf-8"))
        self.entries = []
        for zi in self.zf.infolist():
            mode = (zi.external_attr >> 16) & 0o170000
            self.entries.append(_M(zi.filename, zi.is_dir(),
                                   mode == 0o120000, zi))

    def prepare(self):
        pass

    def read(self, m):
        try:
            return self.zf.read(m.h)
        except RuntimeError:
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        except (zipfile.BadZipFile, zlib.error, EOFError):
            # 加密包中央目录可读、解成员失败：绝大概率密码错（ZipCrypto check-byte
            # 有 1/256 漏网），放行后解出乱数据 → 解压/CRC 失败。未加密才判损坏。
            if self.encrypted:
                raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")

    def close(self):
        self.zf.close()


class _TarSource:
    def __init__(self, archive, pw):
        import tarfile
        self._tarfile = tarfile
        try:
            self.tar = tarfile.open(archive, "r:gz")
            members = self.tar.getmembers()
        except tarfile.TarError:
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
        except OSError:
            raise CzipError(EXIT_INTERNAL, "写入失败")
        self.entries = []
        for m in members:
            is_link = m.issym() or m.islnk()
            if not (m.isreg() or m.isdir() or is_link):
                continue  # 忽略设备/管道等非常规成员
            self.entries.append(_M(m.name, m.isdir(), is_link, m))

    def prepare(self):
        pass

    def read(self, m):
        try:
            f = self.tar.extractfile(m.h)
            return f.read() if f is not None else b""
        except (self._tarfile.TarError, OSError):
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")

    def close(self):
        self.tar.close()


class _SevenZipSource:
    """py7zr 1.1.3 无逐成员读接口，先读元数据校验，通过后整体解到临时目录再取内容。"""

    def __init__(self, archive, pw):
        py7zr = _require("py7zr")
        self._py7zr = py7zr
        try:
            self.z = py7zr.SevenZipFile(archive, "r", password=pw or None)
        except py7zr.exceptions.PasswordRequired:
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        except py7zr.exceptions.Bad7zFile:
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
        try:
            need_pw = self.z.needs_password()
        except Exception:  # noqa: BLE001
            need_pw = False
        if need_pw and not pw:
            self.z.close()
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        self.entries = []
        for f in self.z.files:
            self.entries.append(_M(f.filename, f.is_directory,
                                   f.is_symlink, f))
        self.raw = None

    def prepare(self):
        # 校验已通过（无 .. / 链接），再整体解出到隔离的临时目录。
        self.raw = tempfile.mkdtemp(prefix=".czip-7z-raw-")
        try:
            self.z.extractall(self.raw)
        except self._py7zr.exceptions.PasswordRequired:
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        except self._py7zr.exceptions.Bad7zFile:
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
        except Exception as e:  # noqa: BLE001 — 未知解压异常按密码/损坏归类
            if _looks_like_password_error(e):
                raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")

    def read(self, m):
        p = os.path.join(self.raw, *m.name.split("/"))
        with open(p, "rb") as f:
            return f.read()

    def close(self):
        try:
            self.z.close()
        except Exception:  # noqa: BLE001
            pass
        if self.raw:
            _rmtree(self.raw)


class _RarSource:
    def __init__(self, archive, pw):
        rarfile = _require("rarfile")
        self._rarfile = rarfile
        if not shutil.which("unar") and not shutil.which("unrar") \
                and not shutil.which("bsdtar"):
            raise CzipError(EXIT_DEP,
                            "解压 rar 需要 unar，请先运行 brew install unar")
        try:
            self.rf = rarfile.RarFile(archive)
        except rarfile.Error:
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
        if self.rf.needs_password():
            # 带密码 rar 不支持：会把密码落进 unar argv/ps（PLAN R2）
            self.rf.close()
            raise CzipError(EXIT_UNSUPPORTED, "不支持带密码的 rar 解压")
        self.entries = []
        for ri in self.rf.infolist():
            # rarfile 自带 is_symlink()：RAR3（靠 mode&0xF000==0xA000）与 RAR5
            # （file_redir，含 junction/hardlink）两个子类都正确实现，别自己判 file_redir
            self.entries.append(_M(ri.filename, ri.isdir(),
                                   ri.is_symlink(), ri))

    def prepare(self):
        pass

    def read(self, m):
        try:
            return self.rf.read(m.h)
        except self._rarfile.Error:
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")

    def close(self):
        self.rf.close()


_SOURCES = {"zip": _ZipSource, "7z": _SevenZipSource,
            "targz": _TarSource, "rar": _RarSource}


def _norm_member(name):
    """成员名规范化：反斜杠（Windows 风格）统一转 /，再解析层级。
    转换后同样过 Zip Slip 全部校验（§2.3）。"""
    return name.replace("\\", "/")


def _member_segments(name):
    """规范化成员名 → 干净的路径段列表（去掉空段/单点）。"""
    return [s for s in _norm_member(name).split("/") if s and s != "."]


def do_extract(args, pw):
    archive = args.archive
    if not os.path.lexists(archive):
        raise CzipError(EXIT_NOT_FOUND, f"找不到输入: {archive}")

    fmt = _detect_format(archive)
    if fmt is None:
        raise CzipError(EXIT_UNSUPPORTED, "不支持的压缩包格式")

    dest = (os.path.abspath(args.dest) if args.dest
            else os.path.dirname(os.path.abspath(archive)))
    pkgname = _archive_basename(os.path.basename(archive))

    source = _SOURCES[fmt](archive, pw)
    try:
        landed = _place_members(source, dest, args.layout, pkgname)
    finally:
        source.close()

    print(landed)
    return EXIT_OK


def _collect_members(source):
    """过滤 macOS 元数据、拒绝链接成员、校验路径合法性，返回 [(segments, is_dir, m)]。"""
    # 先整包扫描拒绝一切软/硬链接成员（§2.3 安全红线）：链接可先落一条指向 dest
    # 外的链，后续成员顺链被 OS 写到目录外，纯字符串校验拦不住。拒绝须早于任何写入。
    for m in source.entries:
        if m.is_link:
            raise CzipError(EXIT_INTERNAL, "压缩包含链接成员，已拒绝")
    result = []
    for m in source.entries:
        segs = _member_segments(m.name)
        if not segs:
            continue  # 根条目/空名
        if any(_is_macos_junk(s) for s in segs):
            continue  # 不落地 macOS 元数据（§1.3.2/§2.3）
        # Zip Slip：规范化后不得含 .. 或以 / 开头（绝对路径）
        if _norm_member(m.name).startswith("/") or ".." in segs:
            raise CzipError(EXIT_INTERNAL, "压缩包含非法路径，已拒绝")
        result.append((segs, m.is_dir, m))
    return result


def _top_items(members):
    """按第一路径段去重，保持出现顺序（§2.3 顶层项判据）。"""
    tops = []
    for segs, _, _ in members:
        top = segs[0]
        if top not in tops:
            tops.append(top)
    return tops


def _flatten_rename_map(dest, tops):
    """铺开布局：为每个顶层项在 dest 下定最终名（撞名 foo→foo-1），整项前缀重写。"""
    taken = set()
    mapping = {}
    for t in tops:
        cand = os.path.basename(avoid_collision(os.path.join(dest, t)))
        if cand in taken:  # 与本批已定名撞车（极少见），继续插 -N 到唯一
            stem, ext = _split_archive_ext(t)
            i = 1
            while True:
                cand = f"{stem}-{i}{ext}"
                if cand not in taken and \
                        not os.path.exists(os.path.join(dest, cand)):
                    break
                i += 1
        taken.add(cand)
        mapping[t] = cand
    return mapping


def _place_members(source, dest, layout, pkgname):
    """按 §2.3 落地：顶层项计数 → 布局 → 顶层项级前缀重写 → 写入。
    全程先写隔离临时目录，成功才 rename/move 进 dest；失败只删临时目录，
    绝不删除/覆盖 dest 已有内容。"""
    members = _collect_members(source)
    tops = _top_items(members)
    if not tops:
        raise CzipError(EXIT_INTERNAL, "压缩包为空")

    n = len(tops)
    wrap = (layout == "folder") or (layout == "auto" and n >= 2)

    try:
        os.makedirs(dest, exist_ok=True)
    except OSError:
        raise CzipError(EXIT_INTERNAL, "写入失败")

    if wrap:
        landing = avoid_collision(os.path.join(dest, pkgname))
        rename_map = None  # 套壳内为全新目录，顶层项无需再改名
    else:
        landing = dest
        rename_map = _flatten_rename_map(dest, tops)

    try:
        staging = tempfile.mkdtemp(prefix=".czip-extract-", dir=dest)
        base_real = os.path.realpath(staging)
    except OSError:  # dest 不可写等 → 别让裸 OSError 冒到 main 打 traceback
        raise CzipError(EXIT_INTERNAL, "写入失败")
    try:
        source.prepare()
        for segs, is_dir, m in members:
            out_segs = list(segs)
            if rename_map is not None:
                out_segs[0] = rename_map[segs[0]]
            target = os.path.join(staging, *out_segs)
            # 即将写入前对真实落点复核仍以落地目录为前缀（§2.3）：配合上面拒链接，
            # 堵住「链接先落地、后续成员顺链逃逸」——纯预扫拦不住的路径。
            real = os.path.realpath(target)
            if real != base_real and not real.startswith(base_real + os.sep):
                raise CzipError(EXIT_INTERNAL, "压缩包含非法路径，已拒绝")
            if is_dir:
                _safe_makedirs(target)
            else:
                _safe_makedirs(os.path.dirname(target))
                data = source.read(m)
                with open(target, "wb") as f:
                    f.write(data)

        if wrap:
            os.rename(staging, landing)          # 整壳一次改名（廉价原子）
        else:
            for t in tops:                        # 逐顶层项移入 dest
                os.rename(os.path.join(staging, rename_map[t]),
                          os.path.join(dest, rename_map[t]))
            os.rmdir(staging)
    except CzipError:
        _rmtree(staging)
        raise
    except OSError:
        _rmtree(staging)
        raise CzipError(EXIT_INTERNAL, "写入失败")
    except BaseException:
        _rmtree(staging)
        raise

    return landing


def _safe_makedirs(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        raise CzipError(EXIT_INTERNAL, "写入失败")


def _rmtree(path):
    """删掉我们建的临时目录（仅删本工具产物，不碰用户已有文件）。"""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
    except OSError:
        pass


# ---------- 入口 ----------

def build_parser():
    p = argparse.ArgumentParser(prog="czip.py", description="compress-zip 内核")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compress", help="压缩")
    c.add_argument("--format", required=True, choices=["zip", "7z", "targz"])
    c.add_argument("--encrypt", required=True,
                   choices=["none", "aes", "zipcrypto"])
    c.add_argument("--out")
    c.add_argument("paths", nargs="+")

    e = sub.add_parser("extract", help="解压")
    e.add_argument("--layout", choices=["auto", "flatten", "folder"],
                   default="auto")
    e.add_argument("--dest")
    e.add_argument("archive")
    return p


def main(argv=None):
    # S5：启动即从环境变量取密码并删除，缩短暴露窗口，且 spawn 的子进程不继承
    pw = os.environ.pop("COMPRESS_PW", None)

    parser = build_parser()
    args = parser.parse_args(argv)  # 用法错误由 argparse 退 2

    try:
        if args.cmd == "compress":
            return do_compress(args, pw)
        return do_extract(args, pw)
    except CzipError as e:
        print(f"错误: {e.msg}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
