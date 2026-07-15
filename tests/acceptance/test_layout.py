"""手选布局（§2.3，新）：--layout flatten 强制铺开、folder 强制套壳、非法值退 2。

对照 auto：flatten 对多顶层项也不套壳；folder 对单顶层项也套壳。
"""
from helpers import (compress, extract, assert_success, assert_error, write_file)


def test_layout_flatten_forces_flat_on_multi(tmp_path):
    """--layout flatten：多顶层项也强制铺进 dest，不套壳。"""
    a = write_file(tmp_path / "src" / "a.txt", b"A")
    b = write_file(tmp_path / "src" / "b.txt", b"B")
    archive = assert_success(compress("zip", "none", a, b))   # 2 顶层项，归档.zip
    dest = tmp_path / "out"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest, layout="flatten"))
    assert landed == dest, "flatten 布局 stdout 应为 dest"
    assert (dest / "a.txt").read_bytes() == b"A"
    assert (dest / "b.txt").read_bytes() == b"B"
    assert not (dest / "归档").exists(), "flatten 不应套 归档 壳"


def test_layout_folder_forces_shell_on_single(tmp_path):
    """--layout folder：单顶层项也强制套 <dest>/<包名>/。"""
    root = tmp_path / "单项"
    write_file(root / "x.txt", b"X")
    archive = assert_success(compress("zip", "none", root))   # 顶层单项 单项
    dest = tmp_path / "out"
    dest.mkdir()
    shell = assert_success(extract(archive, dest=dest, layout="folder"))
    assert shell == dest / "单项", f"folder 应套 包名 壳，实际 {shell}"
    # 套壳后包内顶层项 单项/ 落在壳里（folder 无条件套一层，故会出现 单项/单项）
    assert (shell / "单项" / "x.txt").read_bytes() == b"X"


def test_layout_auto_explicit_same_as_default(tmp_path):
    """显式 --layout auto 与省略一致：单顶层项铺开。"""
    root = tmp_path / "树"
    write_file(root / "a.txt", b"A")
    write_file(root / "b.txt", b"B")
    archive = assert_success(compress("zip", "none", root))   # 顶层单项 树
    dest = tmp_path / "out"
    dest.mkdir()
    landed = assert_success(extract(archive, dest=dest, layout="auto"))
    assert landed == dest
    assert (dest / "树").is_dir()


def test_illegal_layout_value_exit2(tmp_path):
    """非法 --layout 值 → 退 2（argparse usage:）。"""
    root = tmp_path / "d"
    write_file(root / "a.txt", b"A")
    archive = assert_success(compress("zip", "none", root))
    r = extract(archive, dest=tmp_path / "out", layout="wtf")
    assert_error(r, 2, "usage:")
