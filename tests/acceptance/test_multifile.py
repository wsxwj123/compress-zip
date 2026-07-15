"""压缩命名（§1.3，改）+ 包内结构（§1.3.2，新）。stdlib 核心路径。

命名（改）：单选用该项名；多选默认 归档.zip（不再是父目录名/第一项名）。
结构（新）：包内不加顶层前缀（foo→foo/ 非 foo/foo/），不写 .DS_Store / __MACOSX。
"""
import zipfile

from helpers import (compress, extract, assert_success, write_file,
                     assert_contains_files)


# ---------- 命名（改） ----------

def test_single_file_naming(tmp_path):
    """单选文件 → 包名 = 该文件名（含原扩展名）+ .zip。"""
    f = write_file(tmp_path / "报告.txt", b"R")
    p = assert_success(compress("zip", "none", f))
    assert p.name == "报告.txt.zip", f"实际 {p.name}"
    assert p.parent == tmp_path


def test_single_folder_naming(tmp_path):
    """单选文件夹 → 包名 = 该文件夹名。"""
    d = tmp_path / "资料"
    write_file(d / "a.txt", b"A")
    p = assert_success(compress("zip", "none", d))
    assert p.name == "资料.zip", f"实际 {p.name}"


def test_multi_same_dir_default_archive_name(tmp_path):
    """（改）同一父目录多选 → 包名 = 归档.zip（不再用父目录名）；落第一个输入的父目录。"""
    parent = tmp_path / "工作区"
    a = write_file(parent / "a.txt", b"A")
    b = write_file(parent / "b.txt", b"B")
    c = write_file(parent / "子" / "c.txt", b"C")
    p = assert_success(compress("zip", "none", a, b, c))
    assert p.parent == parent, f"应落第一个输入的父目录 {parent}，实际 {p.parent}"
    assert p.name == "归档.zip", f"多选应默认命名 归档.zip，实际 {p.name}"

    # 3 个顶层项 → auto 套壳 归档/，解出三文件齐全
    shell = assert_success(extract(p, dest=tmp_path / "out"))
    assert shell.name == "归档", f"多顶层项应套 归档 壳，实际 {shell.name}"
    assert_contains_files(shell, {"a.txt": b"A", "b.txt": b"B", "c.txt": b"C"})


def test_multi_cross_dir_default_archive_name(tmp_path):
    """（改）跨父目录多选 → 包名同样 归档.zip；落第一个输入的父目录（§1.3）。"""
    d1 = tmp_path / "dir1"
    d2 = tmp_path / "dir2"
    first = write_file(d1 / "首个.txt", b"FIRST")
    second = write_file(d2 / "第二.txt", b"SECOND")

    p = assert_success(compress("zip", "none", first, second))
    assert p.parent == d1, f"应落第一个输入的父目录 {d1}，实际 {p.parent}"
    assert p.name == "归档.zip", f"多选应默认命名 归档.zip，实际 {p.name}"

    shell = assert_success(extract(p, dest=tmp_path / "out"))
    assert_contains_files(shell, {"首个.txt": b"FIRST", "第二.txt": b"SECOND"})


# ---------- 包内结构（新，§1.3.2） ----------

def test_no_top_level_prefix(tmp_path):
    """选文件夹 foo → 包内顶层就是 foo/…，不套娃成 foo/foo/…。"""
    foo = tmp_path / "foo"
    write_file(foo / "a.txt", b"A")
    write_file(foo / "sub" / "b.txt", b"B")
    archive = assert_success(compress("zip", "none", foo))
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    tops = {n.split("/")[0] for n in names if n.strip("/")}
    assert tops == {"foo"}, f"包内顶层应只有 foo，实际 {tops}"
    assert not any(n.startswith("foo/foo/") for n in names), \
        f"不应加顶层前缀套娃 foo/foo/：{names}"


def test_multi_no_wrapping_folder_in_archive(tmp_path):
    """多选两个文件 → 包内顶层直接是这两项，不额外套 归档/ 前缀。"""
    a = write_file(tmp_path / "src" / "a.txt", b"A")
    b = write_file(tmp_path / "src" / "b.txt", b"B")
    archive = assert_success(compress("zip", "none", a, b))
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    tops = {n.split("/")[0] for n in names if n.strip("/")}
    assert tops == {"a.txt", "b.txt"}, f"包内顶层应为两项自身名，实际 {tops}"


def test_no_macos_metadata_in_archive(tmp_path):
    """.DS_Store / __MACOSX 一律不写进包（否则污染包 + 干扰顶层项计数）。"""
    foo = tmp_path / "foo"
    write_file(foo / "real.txt", b"R")
    write_file(foo / ".DS_Store", b"macos-junk")
    archive = assert_success(compress("zip", "none", foo))
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert not any(".DS_Store" in n for n in names), f".DS_Store 混进包了：{names}"
    assert not any("__MACOSX" in n for n in names), f"__MACOSX 混进包了：{names}"
    assert any("real.txt" in n for n in names), f"正常文件应在包里：{names}"
