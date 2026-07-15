"""安全边界（§2.3 / §5.9，重点）：Zip Slip 全格式拒绝、软/硬链接成员拒绝、
反斜杠归一化。核心红线：dest 之外零文件落地。
"""
import io
import os
import tarfile
import zipfile

import pytest

from helpers import extract, assert_success, assert_error


def _make_slip_targz(path, member_name):
    """构造一个含穿越成员的 tar.gz（另带一个正常成员，保证包本身可读）。"""
    data = b"PWNED"
    with tarfile.open(path, "w:gz") as tar:
        norm = tarfile.TarInfo("ok.txt")
        norm.size = 3
        tar.addfile(norm, io.BytesIO(b"abc"))
        info = tarfile.TarInfo(member_name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def _make_tar(path, entries):
    """entries: [(kind, name, extra)]，kind ∈ file/symlink/hardlink/dir。"""
    with tarfile.open(path, "w:gz") as tar:
        for kind, name, extra in entries:
            if kind == "file":
                data = extra or b""
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            elif kind == "symlink":
                info = tarfile.TarInfo(name)
                info.type = tarfile.SYMTYPE
                info.linkname = extra
                tar.addfile(info)
            elif kind == "hardlink":
                info = tarfile.TarInfo(name)
                info.type = tarfile.LNKTYPE
                info.linkname = extra
                tar.addfile(info)
            elif kind == "dir":
                info = tarfile.TarInfo(name)
                info.type = tarfile.DIRTYPE
                tar.addfile(info)


# ---------- Zip Slip（tar / zip / 反斜杠，全格式一视同仁） ----------

@pytest.mark.parametrize("member", [
    "../evil_escape.txt",
    "../../evil_escape.txt",
    "sub/../../evil_escape.txt",
])
def test_tar_slip_rejected(tmp_path, member):
    archive = tmp_path / "malicious.tar.gz"
    _make_slip_targz(archive, member)

    dest = tmp_path / "dest"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包含非法路径")

    # 关键：dest 之外绝不落地任何文件
    assert not (tmp_path / "evil_escape.txt").exists(), "穿越成员逃逸到了 dest 之外！"
    for parent in [tmp_path, tmp_path.parent]:
        assert not (parent / "evil_escape.txt").exists()


def test_absolute_path_member_rejected(tmp_path):
    """成员用绝对路径也应被拒（同属穿越防护）。"""
    archive = tmp_path / "abs.tar.gz"
    _make_slip_targz(archive, "/tmp/czip_abs_escape_test.txt")
    dest = tmp_path / "dest"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包含非法路径")
    assert not os.path.exists("/tmp/czip_abs_escape_test.txt"), "绝对路径成员逃逸落地了"


def test_zip_slip_rejected(tmp_path):
    """zip 格式的 ../ 越界成员同样退 1、dest 外零落地。"""
    archive = tmp_path / "zipslip.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil_zip.txt", b"PWN")
    dest = tmp_path / "dest"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包含非法路径")
    assert not (tmp_path / "evil_zip.txt").exists(), "zip-slip 逃逸落地了"


def test_backslash_escape_rejected(tmp_path):
    """反斜杠归一化后仍越界的成员 → 退 1、dest 外零落地。"""
    archive = tmp_path / "bs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("..\\..\\evil_bs.txt", b"PWN")
    dest = tmp_path / "dest"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包含非法路径")
    assert not (tmp_path / "evil_bs.txt").exists()
    assert not (tmp_path.parent / "evil_bs.txt").exists()


def test_backslash_legal_path_normalized(tmp_path):
    """反斜杠合法路径（Windows 风格）→ 归一化为目录层级正常解出，名字里不带反斜杠。"""
    archive = tmp_path / "winpaths.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("top\\sub\\file.txt", b"WIN")
    dest = tmp_path / "dest"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest))   # top 唯一顶层项 → 铺开
    assert (dest / "top" / "sub" / "file.txt").read_bytes() == b"WIN"
    assert not any("\\" in p.name for p in dest.rglob("*")), "解出物名里不应带反斜杠"


# ---------- 软/硬链接成员拒绝（防顺链逃逸，重点） ----------

def test_symlink_member_rejected(tmp_path):
    """★重点：经典顺链逃逸包（软链指向 dest 外 + 后续成员顺链写）→
    退 1 `压缩包含链接成员`，dest 外的 outside 目录零文件落地。"""
    archive = tmp_path / "linkbomb.tar.gz"
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_tar(archive, [
        ("symlink", "link", str(outside)),       # link -> dest 外的 outside
        ("file", "link/pwned.txt", b"PWNED"),    # 顺链则写进 outside
    ])
    dest = tmp_path / "dest"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包含链接成员")
    assert not (outside / "pwned.txt").exists(), "顺链逃逸写到了 dest 之外！"
    assert list(outside.iterdir()) == [], "dest 外的 outside 不应有任何落地"


def test_symlink_relative_escape_rejected(tmp_path):
    """软链指向上级（../外面）也拒。"""
    archive = tmp_path / "linkrel.tar.gz"
    _make_tar(archive, [
        ("symlink", "esc", "../.."),
        ("file", "esc/pwn.txt", b"X"),
    ])
    dest = tmp_path / "dest"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包含链接成员")
    assert not (tmp_path.parent / "pwn.txt").exists()


def test_hardlink_member_rejected(tmp_path):
    """硬链接成员同样整包拒绝。"""
    archive = tmp_path / "hardlink.tar.gz"
    _make_tar(archive, [
        ("file", "real.txt", b"R"),
        ("hardlink", "hl.txt", "real.txt"),
    ])
    dest = tmp_path / "dest"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包含链接成员")


# ---------- 带密码 rar（需外部样本，无则 skip） ----------

def test_password_rar_rejected(tmp_path):
    """带密码 rar 直接退 5（§2.2/§4.2）。
    需一个真实"加密 rar"样本；mac 上通常无 rar 创建工具，无法现造。
    CI/手工请放一个用密码 'rarpw' 加密的 sample_encrypted.rar 到 fixtures/。"""
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "sample_encrypted.rar"
    if not fixture.exists():
        pytest.skip("缺加密 rar 样本（fixtures/sample_encrypted.rar）；"
                    "本机无 rar 创建工具，交由预置样本或手工覆盖")
    pytest.importorskip("rarfile")
    r = extract(fixture, dest=tmp_path, pw="rarpw")
    assert_error(r, 5, "不支持带密码的 rar 解压")
