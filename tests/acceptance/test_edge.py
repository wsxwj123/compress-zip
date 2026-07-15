"""边界/替用户想到的（§5.5/§1.2/§1.3.1）：空格名、emoji 名、symlink 跟随、
ZipCrypto 单文件 >4GiB 退5（稀疏文件桩，不真占盘）。"""
import os

import pytest

from helpers import (compress, extract, assert_success, assert_error,
                     write_file, assert_contains_files, collect_files)


def test_name_with_spaces(tmp_path):
    root = tmp_path / "有 空格 的 目录"
    write_file(root / "文件 名.txt", b"SPACE")
    archive = assert_success(compress("zip", "none", root))
    folder = assert_success(extract(archive, dest=tmp_path / "out"))
    assert_contains_files(folder, {"文件 名.txt": b"SPACE"})


def test_name_with_emoji(tmp_path):
    root = tmp_path / "🎁礼物"
    write_file(root / "🚀火箭.txt", b"EMOJI")
    archive = assert_success(compress("zip", "none", root))
    folder = assert_success(extract(archive, dest=tmp_path / "out"))
    assert_contains_files(folder, {"🚀火箭.txt": b"EMOJI"})


def test_symlink_follows_target(tmp_path):
    """§1.3.1：输入含 symlink 时跟随链接、存目标内容（不存链接本身）。"""
    target = write_file(tmp_path / "真实目标.txt", b"REAL-CONTENT")
    root = tmp_path / "含链接"
    root.mkdir()
    link = root / "链接.txt"
    os.symlink(target, link)

    archive = assert_success(compress("zip", "none", root))
    folder = assert_success(extract(archive, dest=tmp_path / "out"))
    # 解出物里应有目标内容；且解出的是普通文件（非悬空链接）
    got = collect_files(folder)
    assert b"REAL-CONTENT" in got.values(), f"symlink 未跟随存目标内容；got={got}"


def test_symlink_to_dir_followed(tmp_path):
    """指向目录的 symlink 也应跟随，存目录内文件内容。"""
    realdir = tmp_path / "真目录"
    write_file(realdir / "inner.txt", b"INNER")
    root = tmp_path / "含目录链接"
    root.mkdir()
    os.symlink(realdir, root / "目录链接")

    archive = assert_success(compress("zip", "none", root))
    folder = assert_success(extract(archive, dest=tmp_path / "out"))
    got = collect_files(folder)
    assert b"INNER" in got.values(), f"指向目录的 symlink 未跟随；got={got}"


@pytest.mark.slow
def test_zipcrypto_over_4gib_rejected(tmp_path):
    """ZipCrypto 单文件 >4GiB(0xFFFFFFFF) 退 5（§1.2）。
    用稀疏文件桩造超大逻辑体积，不真占磁盘。正确实现应在写入前按 st_size 判定，秒退。"""
    from helpers import PW
    big = tmp_path / "超大文件.bin"
    with open(big, "wb") as f:
        f.truncate(0xFFFFFFFF + 1)   # 4GiB + 1 字节，> 上限
    assert os.stat(big).st_size > 0xFFFFFFFF

    r = compress("zip", "zipcrypto", big, pw=PW, )  # noqa
    assert_error(r, 5, "ZipCrypto 不支持超过 4GB 的单文件，请改用 AES")


@pytest.mark.slow
def test_aes_over_4gib_ok_no_limit(tmp_path):
    """对照：AES 路径无 4GiB 限制（pyzipper 自动 zip64）。这里只验证不因大小被判 5。
    仍用稀疏文件；若无 pyzipper 则跳过。压缩 4GiB 稀疏零可能较慢，故标 slow。"""
    pytest.importorskip("pyzipper")
    from helpers import PW
    big = tmp_path / "aes大文件.bin"
    with open(big, "wb") as f:
        f.truncate(0xFFFFFFFF + 1)
    r = compress("zip", "aes", big, pw=PW)
    # 不应是"超过4GB"的 5；成功(0)或其它运行期错误都可，但绝不能是这条组合限制
    assert not (r.returncode == 5 and "4GB" in r.stderr), (
        f"AES 不应触发 4GiB 限制；stderr={r.stderr!r}")
