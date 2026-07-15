"""不删不覆盖 + 顶层项级改名（§1.4 / §2.3 / §5.3）。stdlib 核心路径，直接可跑。

解压侧改名（改）：作用在顶层项整体（前缀重写 foo→foo-1），不逐成员判重。
铺开布局下 stdout = dest；顶层项撞名时整项前缀重写为 -N。
"""
from helpers import (compress, extract, assert_success, write_file,
                     collect_files)


# ---------- 压缩侧改名避让（单选，未变） ----------

def test_compress_same_name_renames(tmp_path):
    src = tmp_path / "项目"
    write_file(src / "a.txt", b"AAA")

    p1 = assert_success(compress("zip", "none", src))
    assert p1.name == "项目.zip", f"首个包名应为 项目.zip，实际 {p1.name}"

    p2 = assert_success(compress("zip", "none", src))
    assert p1.exists(), "第一次的包不应被删除/覆盖"
    assert p2 != p1
    assert p2.name == "项目-1.zip", f"第二个包名应为 项目-1.zip，实际 {p2.name}"

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
    """★替用户想到的：压缩全程只读输入，源文件内容/存在性不变。"""
    src = tmp_path / "src"
    write_file(src / "keep.txt", b"ORIGINAL")
    before = collect_files(src)
    assert_success(compress("zip", "none", src))
    after = collect_files(src)
    assert before == after, "源目录内容在压缩后被改动了"
    assert (src / "keep.txt").read_bytes() == b"ORIGINAL"


# ---------- 解压侧顶层项级改名（改） ----------

def test_extract_twice_top_item_renamed(tmp_path):
    """auto 铺开：同包解两次到同 dest，第二次顶层项前缀重写 -1，首次内容不被覆盖。"""
    src = tmp_path / "包内容"
    write_file(src / "x.txt", b"XX")
    archive = assert_success(compress("zip", "none", src))   # 顶层单项 包内容

    dest = tmp_path / "解压区"
    dest.mkdir()
    d1 = assert_success(extract(archive, dest=dest))
    d2 = assert_success(extract(archive, dest=dest))

    # 铺开布局：两次 stdout 都是 dest
    assert d1 == dest and d2 == dest
    # 顶层项撞名 → 第二次整项重写为 包内容-1，首次内容零改动
    assert (dest / "包内容" / "x.txt").read_bytes() == b"XX", "首次落地内容被覆盖"
    assert (dest / "包内容-1" / "x.txt").read_bytes() == b"XX", "第二次应落 包内容-1"


def test_extract_does_not_overwrite_existing(tmp_path):
    """目标顶层项已存在时整项避让，已存在同名目录内容不被动。"""
    src = tmp_path / "包内容"
    write_file(src / "x.txt", b"XX")
    archive = assert_success(compress("zip", "none", src))

    dest = tmp_path / "解压区"
    # 预先占坑：手动建一个同名顶层目录并放东西
    squat = dest / "包内容"
    write_file(squat / "预先存在.txt", b"KEEP-ME")

    landed = assert_success(extract(archive, dest=dest))
    assert landed == dest
    assert (squat / "预先存在.txt").read_bytes() == b"KEEP-ME", "占坑文件被覆盖了"
    assert (dest / "包内容-1" / "x.txt").read_bytes() == b"XX", "新内容应整项落 包内容-1"


def test_inplace_self_extract_no_merge_overwrite(tmp_path):
    """★重点（§5.3）：单文件夹装多文件的自压包，原地 auto 解压 →
    源 foo/ 及其内每个文件零改动，新内容整项落 foo-1/**。
    专防退化成"逐成员判 <dest>/foo/x 存在"→ 把包内 foo 逐个文件 merge 进源 foo、覆盖源。"""
    foo = tmp_path / "foo"
    write_file(foo / "a.txt", b"AAA")
    write_file(foo / "b.txt", b"BBB")
    write_file(foo / "sub" / "c.txt", b"CCC")
    archive = assert_success(compress("zip", "none", foo))   # foo.zip：顶层单项 foo，装 3 文件
    assert archive.name == "foo.zip"
    assert archive.parent == tmp_path

    # 原地解压（默认 dest = 包所在目录 = tmp_path），源 foo 就在这里
    landed = assert_success(extract(archive))   # auto → 单顶层项铺开
    assert landed == tmp_path

    # 源 foo 零改动（逐文件核对）
    assert (foo / "a.txt").read_bytes() == b"AAA"
    assert (foo / "b.txt").read_bytes() == b"BBB"
    assert (foo / "sub" / "c.txt").read_bytes() == b"CCC"
    # 新内容整项落 foo-1（而非 merge 进源 foo）
    assert (tmp_path / "foo-1" / "a.txt").read_bytes() == b"AAA"
    assert (tmp_path / "foo-1" / "b.txt").read_bytes() == b"BBB"
    assert (tmp_path / "foo-1" / "sub" / "c.txt").read_bytes() == b"CCC"
