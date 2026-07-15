"""多文件混选 + 输出路径推导（§1.3 / §5.4）。stdlib 核心路径。"""
from helpers import (compress, extract, assert_success, write_file,
                     assert_contains_files)


def test_single_file_naming(tmp_path):
    """单个文件输入 → 包名 = 文件名（含原扩展名）+ .zip。"""
    f = write_file(tmp_path / "报告.txt", b"R")
    p = assert_success(compress("zip", "none", f))
    assert p.name == "报告.txt.zip", f"实际 {p.name}"
    assert p.parent == tmp_path


def test_single_folder_naming(tmp_path):
    d = tmp_path / "资料"
    write_file(d / "a.txt", b"A")
    p = assert_success(compress("zip", "none", d))
    assert p.name == "资料.zip", f"实际 {p.name}"


def test_multi_same_dir_uses_parent_name(tmp_path):
    """同一父目录多选 → 包名 = 父目录名，落该父目录。"""
    parent = tmp_path / "工作区"
    a = write_file(parent / "a.txt", b"A")
    b = write_file(parent / "b.txt", b"B")
    c = write_file(parent / "子" / "c.txt", b"C")
    p = assert_success(compress("zip", "none", a, b, c))
    assert p.parent == parent
    assert p.name == "工作区.zip", f"实际 {p.name}"

    # 解出后三个文件都在
    folder = assert_success(extract(p, dest=tmp_path / "out"))
    assert_contains_files(folder, {"a.txt": b"A", "b.txt": b"B", "c.txt": b"C"})


def test_multi_cross_dir_uses_first_input(tmp_path):
    """跨父目录多选 → 输出落第一个输入的父目录，包名 = 第一个输入名（§1.3）。"""
    d1 = tmp_path / "dir1"
    d2 = tmp_path / "dir2"
    first = write_file(d1 / "首个.txt", b"FIRST")
    second = write_file(d2 / "第二.txt", b"SECOND")

    p = assert_success(compress("zip", "none", first, second))
    assert p.parent == d1, f"应落第一个输入的父目录 {d1}，实际 {p.parent}"
    assert p.name == "首个.txt.zip", f"实际 {p.name}"

    folder = assert_success(extract(p, dest=tmp_path / "out"))
    assert_contains_files(folder, {"首个.txt": b"FIRST", "第二.txt": b"SECOND"})
