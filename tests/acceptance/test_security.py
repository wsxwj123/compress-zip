"""安全边界（§2.3 / §5.7）：tar-slip 目录穿越拒绝、带密码 rar 拒绝。"""
import io
import tarfile

import pytest

from helpers import extract, assert_error


def _make_slip_targz(path, member_name):
    """构造一个含穿越成员的 tar.gz。"""
    data = b"PWNED"
    with tarfile.open(path, "w:gz") as tar:
        # 一个正常成员，保证包本身可读
        norm = tarfile.TarInfo("ok.txt")
        norm.size = 3
        tar.addfile(norm, io.BytesIO(b"abc"))
        # 穿越成员
        info = tarfile.TarInfo(member_name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


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
    # 退 1，稳定子串
    assert_error(r, 1, "压缩包含非法路径")

    # 关键：dest 之外绝不能落地任何文件（替用户想到的——不只看退出码）
    escaped = tmp_path / "evil_escape.txt"
    assert not escaped.exists(), "穿越成员逃逸到了 dest 之外！"
    # dest 的上级、上上级都不应出现逃逸文件
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
    import os
    assert not os.path.exists("/tmp/czip_abs_escape_test.txt"), "绝对路径成员逃逸落地了"


def test_password_rar_rejected(tmp_path):
    """带密码 rar 直接退 5（§2.2/§4.2）。

    需要一个真实的"加密 rar"样本；mac 上通常没有 rar 创建工具（rar 为非自由软件），
    无法在测试里现造。若 fixtures 下预置了样本则跑，否则跳过并说明。
    CI/手工请放一个用密码 'rarpw' 加密的 sample_encrypted.rar 到 fixtures/。
    """
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "sample_encrypted.rar"
    if not fixture.exists():
        pytest.skip("缺加密 rar 样本（fixtures/sample_encrypted.rar）；"
                    "本机无 rar 创建工具，交由预置样本或手工覆盖")
    pytest.importorskip("rarfile")
    r = extract(fixture, dest=tmp_path, pw="rarpw")
    assert_error(r, 5, "不支持带密码的 rar 解压")
