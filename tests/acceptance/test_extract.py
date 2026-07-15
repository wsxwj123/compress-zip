"""解压正向主路径 + 智能布局 auto（§2.3，重点）。

auto 判据（钉死）：按成员"第一路径段去重"数顶层项，不是按 namelist 条数。
  - 恰好 1 个顶层项 → 铺开（stdout = dest，顶层项落 dest 下）
  - ≥2 个顶层项 → 套 <dest>/<包名>/（stdout = 壳路径）
  - 0 个顶层项（空包/仅 .DS_Store）→ 退 1 `压缩包为空`
注意（改）：铺开布局下 stdout = dest 本身，不再是子文件夹；据此改断言。
"""
import zipfile

import pytest

from helpers import (compress, extract, assert_success, assert_error,
                     write_file, assert_contains_files)


def _tree(tmp_path):
    """单文件夹 树 装多个文件 → 顶层项恰好 1 个（用于验证 auto 铺开）。"""
    root = tmp_path / "树"
    write_file(root / "顶层.txt", b"TOP")
    write_file(root / "子目录" / "里层.txt", b"DEEP")
    files = {"顶层.txt": b"TOP", "里层.txt": b"DEEP"}
    return root, files


# ---------- 各格式往返（单顶层项 → auto 铺开） ----------

def test_extract_zip_roundtrip(tmp_path):
    root, files = _tree(tmp_path)
    archive = assert_success(compress("zip", "none", root))
    dest = tmp_path / "out"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest))
    # 1 顶层项 → 铺开：stdout = dest；顶层项 树/ 落在 dest 下
    assert landed == dest, f"铺开布局 stdout 应为 dest，实际 {landed}"
    assert (dest / "树").is_dir(), "顶层项 树 应铺在 dest 下"
    assert_contains_files(dest, files)


def test_extract_targz_roundtrip(tmp_path):
    root, files = _tree(tmp_path)
    archive = assert_success(compress("targz", "none", root))
    assert archive.name == "树.tar.gz"
    dest = tmp_path / "out"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest))
    assert landed == dest
    assert (dest / "树").is_dir()
    assert_contains_files(dest, files)


def test_extract_7z_roundtrip(tmp_path):
    pytest.importorskip("py7zr")
    root, files = _tree(tmp_path)
    archive = assert_success(compress("7z", "none", root))
    dest = tmp_path / "out"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest))
    assert landed == dest
    assert (dest / "树").is_dir()
    assert_contains_files(dest, files)


def test_extract_custom_dest(tmp_path):
    """--dest 指定父目录，单顶层项铺开进该目录。"""
    root, files = _tree(tmp_path)
    archive = assert_success(compress("zip", "none", root))

    dest = tmp_path / "指定输出"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest))
    assert landed == dest, "铺开布局应解到 --dest 本身"
    assert (dest / "树").is_dir()
    assert_contains_files(dest, files)


# ---------- auto 布局核心（§2.3，重点） ----------

def test_auto_single_folder_many_files_flattens(tmp_path):
    """★重点：单文件夹装多文件 → 顶层项=1 → auto 铺开。
    证明按"第一路径段去重"数项，而非按 namelist 条数（否则会被当 N 项误套壳）。"""
    root = tmp_path / "包"
    write_file(root / "a.txt", b"A")
    write_file(root / "b.txt", b"B")
    write_file(root / "sub" / "c.txt", b"C")
    archive = assert_success(compress("zip", "none", root))   # 顶层单项 包，内含 3 文件
    dest = tmp_path / "out"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest))
    assert landed == dest, "单顶层项应铺开，stdout=dest"
    assert (dest / "包").is_dir()
    assert not (dest / "包" / "包").exists(), "不应再套一层 包/包"
    assert_contains_files(dest / "包", {"a.txt": b"A", "b.txt": b"B", "c.txt": b"C"})


def test_auto_multi_top_items_wraps(tmp_path):
    """≥2 顶层项 → auto 套 <dest>/<包名>/。"""
    a = write_file(tmp_path / "src" / "a.txt", b"A")
    b = write_file(tmp_path / "src" / "b.txt", b"B")
    archive = assert_success(compress("zip", "none", a, b))   # 多选 → 归档.zip，2 顶层项
    assert archive.name == "归档.zip"
    dest = tmp_path / "out"
    dest.mkdir()
    shell = assert_success(extract(archive, dest=dest))
    assert shell == dest / "归档", f"多顶层项应套 归档 壳，实际 {shell}"
    assert_contains_files(shell, {"a.txt": b"A", "b.txt": b"B"})


def test_auto_empty_archive_rejected(tmp_path):
    """0 成员空包 → 退 1 `压缩包为空`（§4.2）。"""
    archive = tmp_path / "空.zip"
    with zipfile.ZipFile(archive, "w"):
        pass   # 无任何成员
    dest = tmp_path / "out"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包为空")


def test_auto_only_ds_store_is_empty(tmp_path):
    """仅含 .DS_Store 的包 → 过滤 macOS 元数据后剩 0 顶层项 → 退 1 `压缩包为空`。"""
    archive = tmp_path / "只有ds.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(".DS_Store", b"junk")
    dest = tmp_path / "out"
    dest.mkdir()
    r = extract(archive, dest=dest)
    assert_error(r, 1, "压缩包为空")


def test_empty_folder_roundtrip(tmp_path):
    """★替用户想到的：空文件夹能压能解，解出后空目录仍在（§5.7）。
    空目录 = 1 个顶层项（目录条目），非"空包"，故正常铺开。"""
    empty = tmp_path / "空文件夹"
    empty.mkdir()
    archive = assert_success(compress("zip", "none", empty))

    dest = tmp_path / "out"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest))
    assert landed == dest
    # 顶层项 空文件夹/ 铺在 dest 下，且仍是空目录
    kept = dest / "空文件夹"
    assert kept.is_dir(), "空目录顶层项未保留"
    assert not any(kept.iterdir()), "解出的空目录里不应凭空多出内容"
