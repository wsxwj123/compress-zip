"""白盒单测：直接 import 内部函数，覆盖验收测试不便直接触达的内部逻辑。
（验收测试是黑盒子进程调用，这里补内部纯函数/分支的覆盖。）"""
import os
import sys
import zipfile

import pytest

# 让 import czip / zipcrypto 生效（项目根在 tests/unit 的上上级）
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import czip
import zipcrypto


# ---------- 改名避让 ----------

def test_avoid_collision_file(tmp_path):
    p = tmp_path / "a.zip"
    assert czip.avoid_collision(str(p)) == str(p)          # 不存在 → 原路径
    p.write_bytes(b"x")
    assert czip.avoid_collision(str(p)) == str(tmp_path / "a-1.zip")
    (tmp_path / "a-1.zip").write_bytes(b"x")
    assert czip.avoid_collision(str(p)) == str(tmp_path / "a-2.zip")


def test_avoid_collision_targz_whole_ext(tmp_path):
    p = tmp_path / "backup.tar.gz"
    p.write_bytes(b"x")
    # .tar.gz 视为整体扩展名，-1 插在整体扩展名前
    assert czip.avoid_collision(str(p)) == str(tmp_path / "backup-1.tar.gz")


def test_avoid_collision_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    assert czip.avoid_collision(str(d)) == str(tmp_path / "out-1")


# ---------- 扩展名拆分 ----------

@pytest.mark.parametrize("name,stem", [
    ("x.zip", "x"), ("x.7z", "x"), ("x.tar.gz", "x"), ("x.tgz", "x"),
    ("a.b.zip", "a.b"), ("报告.txt.zip", "报告.txt"),
])
def test_archive_basename(name, stem):
    assert czip._archive_basename(name) == stem


# ---------- 输出路径推导 §1.3 ----------

def test_derive_single_file(tmp_path):
    f = tmp_path / "报告.txt"
    f.write_bytes(b"x")
    out = czip.derive_output_path([str(f)], "zip")
    assert out == str(tmp_path / "报告.txt.zip")


def test_derive_single_dir(tmp_path):
    d = tmp_path / "资料"
    d.mkdir()
    out = czip.derive_output_path([str(d)], "targz")
    assert out == str(tmp_path / "资料.tar.gz")


def test_derive_multi_same_parent_uses_archive(tmp_path):
    # 多选（改）→ 固定基础名 归档，落第一个输入的父目录（§1.3）
    parent = tmp_path / "工作区"
    (parent / "子").mkdir(parents=True)
    a = parent / "a.txt"; a.write_bytes(b"a")
    c = parent / "子" / "c.txt"; c.write_bytes(b"c")
    out = czip.derive_output_path([str(a), str(c)], "zip")
    assert out == str(parent / "归档.zip")


def test_derive_multi_cross_parent_uses_archive(tmp_path):
    # 多选跨目录（改）→ 同样 归档，落第一个输入的父目录（§1.3）
    a = tmp_path / "d1" / "首个.txt"; a.parent.mkdir(); a.write_bytes(b"a")
    b = tmp_path / "d2" / "第二.txt"; b.parent.mkdir(); b.write_bytes(b"b")
    out = czip.derive_output_path([str(a), str(b)], "zip")
    assert out == str(tmp_path / "d1" / "归档.zip")


# ---------- collect_entries：空目录 + symlink 跟随 ----------

def test_collect_entries_preserves_empty_leaf_dir(tmp_path):
    root = tmp_path / "r"
    (root / "空").mkdir(parents=True)
    (root / "有" ).mkdir()
    (root / "有" / "f.txt").write_bytes(b"x")
    entries = czip.collect_entries([str(root)])
    dirnames = {arc for src, arc, is_dir in entries if is_dir}
    files = {arc for src, arc, is_dir in entries if not is_dir}
    assert "r/空/" in dirnames          # 叶子空目录被显式保留
    assert "r/有/f.txt" in files
    # 非空目录不必显式条目（由文件路径隐含），避免冗余


def test_collect_entries_follows_symlink_file(tmp_path):
    target = tmp_path / "real.txt"; target.write_bytes(b"REAL")
    root = tmp_path / "r"; root.mkdir()
    os.symlink(target, root / "link.txt")
    entries = czip.collect_entries([str(root)])
    srcs = {arc: src for src, arc, is_dir in entries if not is_dir}
    assert "r/link.txt" in srcs
    with open(srcs["r/link.txt"], "rb") as f:
        assert f.read() == b"REAL"      # 读到的是目标内容


# ---------- ZipCrypto 手搓写入器 ----------

def test_zipcrypto_bit11_and_encrypt_bit(tmp_path):
    """S2：加密位按位或加上，不清掉 UTF-8 bit11。"""
    src = tmp_path / "中文.txt"; src.write_bytes("内容".encode("utf-8"))
    arc = tmp_path / "o.zip"
    zipcrypto.write_zipcrypto(str(arc), [(str(src), "中文.txt", False)],
                              b"pw123")
    with zipfile.ZipFile(arc) as zf:
        info = zf.infolist()[0]
        assert info.flag_bits & 0x800 == 0x800   # UTF-8 bit11 保留
        assert info.flag_bits & 0x1 == 0x1        # 加密位置位


def test_zipcrypto_roundtrip_stdlib(tmp_path):
    src = tmp_path / "中文.txt"
    payload = "秘密 secret 🔒".encode("utf-8")
    src.write_bytes(payload)
    arc = tmp_path / "o.zip"
    pw = "P@ss中文🔒".encode("utf-8")
    zipcrypto.write_zipcrypto(str(arc), [(str(src), "中文.txt", False)], pw)
    with zipfile.ZipFile(arc) as zf:
        zf.setpassword(pw)
        assert zf.read("中文.txt") == payload


def test_zipcrypto_wrong_password_fails(tmp_path):
    src = tmp_path / "a.txt"; src.write_bytes(b"data")
    arc = tmp_path / "o.zip"
    zipcrypto.write_zipcrypto(str(arc), [(str(src), "a.txt", False)], b"right")
    with zipfile.ZipFile(arc) as zf:
        zf.setpassword(b"wrong")
        with pytest.raises(RuntimeError):
            zf.read("a.txt")


def test_zipcrypto_over_4gib(tmp_path, monkeypatch):
    src = tmp_path / "big.bin"; src.write_bytes(b"x")
    monkeypatch.setattr(os.path, "getsize",
                        lambda p: zipcrypto.MAX_ZIPCRYPTO_SIZE + 1)
    with pytest.raises(zipcrypto.Over4GiBError):
        zipcrypto.write_zipcrypto(str(tmp_path / "o.zip"),
                                  [(str(src), "big.bin", False)], b"pw")


def test_zipcrypto_dir_entry_not_encrypted(tmp_path):
    """目录条目不加密：空内容、无加密位。"""
    arc = tmp_path / "o.zip"
    zipcrypto.write_zipcrypto(str(arc), [(None, "空目录/", True)], b"pw")
    with zipfile.ZipFile(arc) as zf:
        info = zf.infolist()[0]
        assert info.filename == "空目录/"
        assert info.flag_bits & 0x1 == 0       # 目录不加密
        assert info.flag_bits & 0x800 == 0x800  # 中文名仍 UTF-8
