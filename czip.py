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


def collect_entries(inputs):
    """遍历输入，产出 [(src_path_or_None, arcname, is_dir)]。
    - 目录：递归；仅「叶子空目录」显式产出目录条目（非空目录由文件路径隐含）。
    - symlink 跟随（followlinks / 目录跟随、文件 open 跟随），存目标内容（§1.3.1）。
    - arcname 前缀 = 输入的 basename。
    """
    entries = []
    for inp in inputs:
        base = os.path.basename(os.path.normpath(inp))
        if os.path.isdir(inp):  # os.path.isdir 跟随 symlink
            for dirpath, dirnames, filenames in os.walk(inp, followlinks=True):
                rel = os.path.relpath(dirpath, inp)
                arcdir = base if rel == "." else os.path.join(base, rel)
                arcdir = arcdir.replace(os.sep, "/")
                if not dirnames and not filenames:
                    entries.append((None, arcdir + "/", True))
                for fn in sorted(filenames):
                    full = os.path.join(dirpath, fn)
                    arc = (arcdir + "/" + fn) if rel != "." else (base + "/" + fn)
                    entries.append((full, arc, False))
        else:
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
        # 所有输入都落在第一个输入的父目录内（含其子目录）→ 用该父目录名；
        # 否则（跨目录）→ 用第一个输入名（INTERFACE §1.3）
        def _under(p):
            ap = os.path.abspath(p)
            return ap == out_dir or ap.startswith(out_dir + os.sep)
        if all(_under(p) for p in inputs):
            stem = os.path.basename(out_dir)
        else:
            stem = os.path.basename(os.path.normpath(first))
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

    # 3) 输入存在性（→ 3）
    for p in args.paths:
        if not os.path.lexists(p):  # lexists：悬空 symlink 也算存在
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
            _write_zip_entries(zf, entries, encrypt_dirs=False)
        return
    # none：标准库，Windows 原生可解的 DEFLATE
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_zip_entries(zf, entries, encrypt_dirs=False)


def _write_zip_entries(zf, entries, encrypt_dirs):
    for src, arc, is_dir in entries:
        if is_dir:
            # 目录条目：空内容。pyzipper 下不给目录加密（用未加密 ZipInfo）。
            zi = zipfile.ZipInfo(arc)
            zf.writestr(zi, b"")
        else:
            zf.write(src, arc)


def _compress_7z(inputs, out, encrypt, pw):
    py7zr = _require("py7zr")
    kw = {}
    if encrypt == "aes":
        kw = {"password": pw}
    with py7zr.SevenZipFile(out, "w", **kw) as z:
        for inp in inputs:
            base = os.path.basename(os.path.normpath(inp))
            if os.path.isdir(inp):
                z.writeall(inp, arcname=base)
            else:
                z.write(inp, arcname=base)


def _compress_targz(inputs, out):
    import tarfile
    # dereference=True：跟随 symlink 存目标内容（§1.3.1）
    with tarfile.open(out, "w:gz", dereference=True) as tar:
        for inp in inputs:
            base = os.path.basename(os.path.normpath(inp))
            tar.add(inp, arcname=base)


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


def do_extract(args, pw):
    archive = args.archive
    if not os.path.lexists(archive):
        raise CzipError(EXIT_NOT_FOUND, f"找不到输入: {archive}")

    fmt = _detect_format(archive)
    if fmt is None:
        raise CzipError(EXIT_UNSUPPORTED, "不支持的压缩包格式")

    sub = _archive_basename(os.path.basename(archive))
    if args.dest is not None:
        # 显式 --dest：目标子文件夹已存在则改名避让，绝不覆盖用户已有内容（§2.3）
        target = avoid_collision(os.path.join(os.path.abspath(args.dest), sub))
    else:
        # 默认原地解压（dest = 压缩包所在目录）。同名目录通常是本工具压缩的源目录，
        # 本工具的 arcname 都带顶层前缀（<name>/...），解进 <parent>/<name>/ 只会
        # 生成 <name>/<name>/... 嵌套，不会覆盖源目录里的直接文件，故原地合并安全。
        target = os.path.join(os.path.dirname(os.path.abspath(archive)), sub)

    if fmt == "zip":
        _extract_zip(archive, target, pw)
    elif fmt == "7z":
        _extract_7z(archive, target, pw)
    elif fmt == "targz":
        _extract_targz(archive, target)
    else:
        _extract_rar(archive, target, pw)

    print(target)
    return EXIT_OK


def _assert_safe_members(names, target):
    """逐成员校验解出真实路径落在 target 内，含 ../ 或绝对路径 → 拒绝（tar-slip）。"""
    base = os.path.abspath(target)
    for name in names:
        dest = os.path.abspath(os.path.join(base, name))
        if dest != base and not dest.startswith(base + os.sep):
            raise CzipError(EXIT_INTERNAL, "压缩包含非法路径，已拒绝")


def _extract_zip(archive, target, pw):
    pyzipper = _require("pyzipper")
    try:
        zf = pyzipper.AESZipFile(archive)
    except (zipfile.BadZipFile, pyzipper.BadZipFile, OSError):
        raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
    with zf:
        encrypted = any(zi.flag_bits & 0x1 for zi in zf.infolist())
        if encrypted and not pw:
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        if pw:
            zf.setpassword(pw.encode("utf-8"))
        # zipfile/pyzipper extract 内建净化 .. 与绝对路径，无需手动 tar-slip 校验
        try:
            os.makedirs(target, exist_ok=True)
            zf.extractall(target)
        except RuntimeError:
            # pyzipper/zipfile 密码错误（ZipCrypto check-byte 或 AES 校验失败）抛 RuntimeError
            _rmtree(target)
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        except (zipfile.BadZipFile, pyzipper.BadZipFile, zlib.error, EOFError):
            _rmtree(target)
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")


def _extract_7z(archive, target, pw):
    py7zr = _require("py7zr")
    try:
        with py7zr.SevenZipFile(archive, "r", password=pw or None) as z:
            _assert_safe_members(z.getnames(), target)
            if z.needs_password() and not pw:
                raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
            os.makedirs(target, exist_ok=True)
            z.extractall(target)
    except CzipError:
        raise
    except py7zr.exceptions.PasswordRequired:
        raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
    except py7zr.exceptions.Bad7zFile:
        _rmtree(target)
        raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
    except Exception as e:  # noqa: BLE001 — 未知解压异常统一归损坏/密码
        _rmtree(target)
        if _looks_like_password_error(e):
            raise CzipError(EXIT_PASSWORD, "密码错误或压缩包已损坏")
        raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")


def _looks_like_password_error(exc):
    s = (str(exc) + type(exc).__name__).lower()
    return "password" in s or "crc" in s or "decrypt" in s or "mac" in s


def _extract_targz(archive, target):
    import tarfile
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            names += [m.linkname for m in members if m.linkname]
            _assert_safe_members(names, target)  # 校验后才落地
            os.makedirs(target, exist_ok=True)
            tar.extractall(target)
    except CzipError:
        _rmtree(target)
        raise
    except tarfile.TarError:
        _rmtree(target)
        raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
    except OSError:
        _rmtree(target)
        raise CzipError(EXIT_INTERNAL, "写入失败")


def _extract_rar(archive, target, pw):
    rarfile = _require("rarfile")
    if not shutil.which("unar") and not shutil.which("unrar") \
            and not shutil.which("bsdtar"):
        raise CzipError(EXIT_DEP,
                        "解压 rar 需要 unar，请先运行 brew install unar")
    try:
        rf = rarfile.RarFile(archive)
    except rarfile.Error:
        raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")
    with rf:
        if rf.needs_password():
            # 带密码 rar 不支持：会把密码落进 unar argv/ps（PLAN R2）
            raise CzipError(EXIT_UNSUPPORTED, "不支持带密码的 rar 解压")
        _assert_safe_members(rf.namelist(), target)
        try:
            os.makedirs(target, exist_ok=True)
            rf.extractall(target)
        except rarfile.Error:
            _rmtree(target)
            raise CzipError(EXIT_INTERNAL, "压缩包损坏或不完整")


def _rmtree(path):
    """清理本次解压建的目录（失败回滚，不碰用户已有文件——仅删我们刚建的）。"""
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
