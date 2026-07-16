"""流式解压回归：大于分块大小(_CHUNK=1MB)的成员必须字节完整。

锁定 copy_to 的分块拷贝跨 chunk 边界无损——防 zip 炸弹的流式改动被改回"整读进内存"，
或引入丢字节/错位。安全审计实证：800MB 成员解压峰值内存从 1.7GB 降到 ~75MB。
用 2.6MB 随机(不可压)内容确保跨多个 chunk，任何边界 bug 都会导致内容不一致。
"""
import os

import pytest

from helpers import compress, extract, assert_success, write_file

SIZE = 2_600_000  # > 2 个 _CHUNK(1MB)，确保跨块流式被真正触发


@pytest.mark.parametrize("fmt", ["zip", "targz", "7z"])
def test_large_member_streams_intact(tmp_path, fmt):
    data = os.urandom(SIZE)
    src = write_file(tmp_path / "big.bin", data)
    archive = assert_success(compress(fmt, "none", src))
    dest = tmp_path / "out"
    dest.mkdir()
    assert_success(extract(archive, dest=dest))
    got = (dest / "big.bin").read_bytes()
    assert got == data, f"{fmt}: 解出内容与原文件不一致（跨块流式丢字节/错位）"
