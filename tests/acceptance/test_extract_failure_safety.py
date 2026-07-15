"""解压失败时绝不删除用户已有文件（补：code-review 发现的数据丢失盲区）。

红线：无论解压因何失败（密码错、包损坏、tar-slip 拒绝），
已存在的同名目标目录及其内容都不能被删除。默认原地解压时，
目标目录常常就是用户的源目录本身，删掉 = 丢数据。
"""
import io
import tarfile
from pathlib import Path

from helpers import compress, extract, assert_success, write_file, require_czip


def test_wrong_password_preserves_existing_dir(tmp_path):
    """原地解压 + 密码错：源目录必须原样保留。"""
    require_czip()
    src = tmp_path / "docs"
    write_file(src / "important.txt", b"keep me")
    r = compress("zip", "zipcrypto", src, pw="secret")
    assert_success(r)
    archive = tmp_path / "docs.zip"
    assert archive.exists()

    r = extract(archive, pw="wrongpass")          # 原地解压（不给 --dest），密码错
    assert r.returncode == 4, f"密码错应退4，实际{r.returncode}"
    assert (src / "important.txt").exists(), "解压失败不该删除已有同名目录"
    assert (src / "important.txt").read_bytes() == b"keep me", "已有文件内容不该被动"


def test_tarslip_preserves_existing_dir(tmp_path):
    """原地解压含 ../ 的恶意 tar.gz：拒绝的同时不能删掉已有同名目录。"""
    require_czip()
    existing = tmp_path / "evil"
    write_file(existing / "keep.txt", b"important")
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        data = b"x"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    r = extract(archive)                           # 原地解压，target=<tmp>/evil（已存在）
    assert r.returncode == 1, f"tar-slip 应退1，实际{r.returncode}"
    assert (existing / "keep.txt").exists(), "tar-slip 拒绝不该删除已有同名目录"
    assert not (tmp_path / "escape.txt").exists(), "逃逸文件不该落地"
