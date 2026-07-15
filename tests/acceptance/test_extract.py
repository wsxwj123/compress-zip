"""解压正向主路径（§2）：各格式解出内容一致、--dest 落地、空文件夹往返。"""
import pytest

from helpers import (compress, extract, assert_success, write_file,
                     assert_contains_files)


def _tree(tmp_path):
    root = tmp_path / "树"
    write_file(root / "顶层.txt", b"TOP")
    write_file(root / "子目录" / "里层.txt", b"DEEP")
    files = {"顶层.txt": b"TOP", "里层.txt": b"DEEP"}
    return root, files


def test_extract_zip_roundtrip(tmp_path):
    root, files = _tree(tmp_path)
    archive = assert_success(compress("zip", "none", root))
    folder = assert_success(extract(archive))
    # 默认 dest = 包所在父目录；子文件夹名 = 包去扩展名
    assert folder.name == "树", f"子文件夹应叫 树，实际 {folder.name}"
    assert folder.parent == archive.parent
    assert_contains_files(folder, files)


def test_extract_targz_roundtrip(tmp_path):
    root, files = _tree(tmp_path)
    archive = assert_success(compress("targz", "none", root))
    assert archive.name == "树.tar.gz"
    folder = assert_success(extract(archive))
    assert folder.name == "树", "tar.gz 应去掉整体扩展名"
    assert_contains_files(folder, files)


def test_extract_7z_roundtrip(tmp_path):
    pytest.importorskip("py7zr")
    root, files = _tree(tmp_path)
    archive = assert_success(compress("7z", "none", root))
    folder = assert_success(extract(archive))
    assert_contains_files(folder, files)


def test_extract_custom_dest(tmp_path):
    root, files = _tree(tmp_path)
    archive = assert_success(compress("zip", "none", root))

    dest = tmp_path / "指定输出"
    dest.mkdir()
    folder = assert_success(extract(archive, dest=dest))
    assert folder.parent == dest, "应解到 --dest 指定的父目录下"
    assert folder.name == "树"
    assert_contains_files(folder, files)


def test_empty_folder_roundtrip(tmp_path):
    """替用户想到的：空文件夹能压能解，解出后空目录仍在（§5.5）。"""
    empty = tmp_path / "空文件夹"
    empty.mkdir()
    archive = assert_success(compress("zip", "none", empty))

    dest = tmp_path / "out"
    dest.mkdir()
    folder = assert_success(extract(archive, dest=dest))
    # 解出的子文件夹存在且是目录（内部可能有也可能没有同名空子目录，至少目录树保留）
    assert folder.is_dir()
    # 能找到一个空目录：解出根本身，或其下的 空文件夹
    candidates = [folder] + [p for p in folder.rglob("*") if p.is_dir()]
    assert any(not any(c.iterdir()) for c in candidates), "空目录未被保留"
