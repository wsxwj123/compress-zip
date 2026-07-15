"""不删不覆盖 + 改名避让（§1.4 / §2.3 / §5.3）。stdlib 核心路径，直接可跑。"""
import zipfile

from helpers import (compress, extract, assert_success, write_file,
                     collect_files)


def test_compress_same_name_renames(tmp_path):
    src = tmp_path / "项目"
    write_file(src / "a.txt", b"AAA")

    # 第一次
    p1 = assert_success(compress("zip", "none", src))
    assert p1.name == "项目.zip", f"首个包名应为 项目.zip，实际 {p1.name}"

    # 第二次：改名避让为 -1，且原包仍在
    p2 = assert_success(compress("zip", "none", src))
    assert p1.exists(), "第一次的包不应被删除/覆盖"
    assert p2 != p1
    assert p2.name == "项目-1.zip", f"第二个包名应为 项目-1.zip，实际 {p2.name}"

    # 第三次 → -2
    p3 = assert_success(compress("zip", "none", src))
    assert p1.exists() and p2.exists()
    assert p3.name == "项目-2.zip", f"第三个包名应为 项目-2.zip，实际 {p3.name}"


def test_compress_out_existing_renames(tmp_path):
    """--out 指定的目标已存在也要改名避让，且已存在文件不被动。"""
    src = write_file(tmp_path / "a.txt", b"AAA")
    out = tmp_path / "backup.zip"
    out.write_bytes(b"OCCUPIED-DO-NOT-TOUCH")   # 预占坑，非真 zip

    p = assert_success(compress("zip", "none", src, out=out))
    assert out.read_bytes() == b"OCCUPIED-DO-NOT-TOUCH", "已存在的 --out 文件被覆盖了！"
    assert p.name == "backup-1.zip", f"应避让为 backup-1.zip，实际 {p.name}"


def test_compress_does_not_touch_source(tmp_path):
    """替用户想到的：压缩全程只读输入，源文件内容/存在性不变。"""
    src = tmp_path / "src"
    write_file(src / "keep.txt", b"ORIGINAL")
    before = collect_files(src)
    assert_success(compress("zip", "none", src))
    after = collect_files(src)
    assert before == after, "源目录内容在压缩后被改动了"
    assert (src / "keep.txt").read_bytes() == b"ORIGINAL"


def test_extract_twice_lands_in_dash1(tmp_path):
    src = tmp_path / "包内容"
    write_file(src / "x.txt", b"XX")
    archive = assert_success(compress("zip", "none", src))

    dest = tmp_path / "解压区"
    dest.mkdir()
    f1 = assert_success(extract(archive, dest=dest))
    f2 = assert_success(extract(archive, dest=dest))

    assert f1.exists() and f2.exists()
    assert f2 != f1
    assert f1.name == "包内容", f"首个子文件夹应叫 包内容，实际 {f1.name}"
    assert f2.name == "包内容-1", f"第二个子文件夹应叫 包内容-1，实际 {f2.name}"


def test_extract_does_not_overwrite_existing(tmp_path):
    """目标子文件夹已存在时避让，已存在的同名目录内容不被动。"""
    src = tmp_path / "包内容"
    write_file(src / "x.txt", b"XX")
    archive = assert_success(compress("zip", "none", src))

    dest = tmp_path / "解压区"
    # 预先占坑：手动建一个同名子文件夹并放东西
    squat = dest / "包内容"
    write_file(squat / "预先存在.txt", b"KEEP-ME")

    folder = assert_success(extract(archive, dest=dest))
    assert folder.name == "包内容-1", f"应避让为 包内容-1，实际 {folder.name}"
    assert (squat / "预先存在.txt").read_bytes() == b"KEEP-ME", "预先存在的文件被覆盖了"
