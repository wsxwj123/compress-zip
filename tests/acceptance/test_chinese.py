"""头号验收（项目成败关键）：中文文件名压 zip 后，用标准库 zipfile 打开生成包，
断言每个中文条目 flag_bits & 0x800 == 0x800（UTF-8 标志位置位）且文件名是正确中文。
none / aes / zipcrypto 三种加密各验一遍（INTERFACE §1.6 / §5.1）。

关键点：加密只影响文件"内容"，不影响中央目录里的"文件名"，所以三种加密都能用
标准库 zipfile 只读列名 + 读 flag，无需密码、无需第三方库即可验证头部。
"""
import zipfile

import pytest

from helpers import PW, compress, assert_success

# 覆盖真实用户会遇到的各种中文名：纯中文、中英混、带空格、带标点、emoji
CN_NAMES = [
    "中文文件.txt",
    "季度报告 2024.txt",   # 带空格
    "数据表格（最终）.csv",  # 带全角括号
    "说明书-v2.md",
    "🎉庆祝文档.txt",       # emoji
]


def _make_cn_dir(tmp_path):
    root = tmp_path / "中文资料夹"
    root.mkdir()
    for i, name in enumerate(CN_NAMES):
        (root / name).write_bytes(f"内容{i}".encode("utf-8"))
    return root


def _nonascii(s: str) -> bool:
    return any(ord(c) > 127 for c in s)


@pytest.mark.parametrize("encrypt", ["none", "aes", "zipcrypto"])
def test_chinese_zip_utf8_flag(tmp_path, encrypt):
    if encrypt == "aes":
        pytest.importorskip("pyzipper", reason="aes 压缩需要 pyzipper（开发阶段安装）")

    root = _make_cn_dir(tmp_path)
    pw = None if encrypt == "none" else PW
    result = compress("zip", encrypt, root, pw=pw)
    archive = assert_success(result)

    # 用标准库解析生成的 zip（不需要密码即可读文件名与 flag）
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        names = zf.namelist()

        # 每个中文名文件都应出现在包里，且没有被 mojibake（说明按 UTF-8 正确保存）
        for want in CN_NAMES:
            assert any(want in n for n in names), (
                f"包内找不到中文文件 {want!r}；实际条目: {names}")

        # 头号断言：凡含非 ASCII 字符的条目，bit 11 必须置位
        checked = 0
        for info in infos:
            if _nonascii(info.filename):
                assert info.flag_bits & 0x800 == 0x800, (
                    f"中文条目 {info.filename!r} 的 UTF-8 标志位(bit11)未置位，"
                    f"flag_bits={info.flag_bits:#06x}")
                checked += 1
        assert checked >= len(CN_NAMES), (
            f"应至少校验 {len(CN_NAMES)} 个中文条目，实际只校验了 {checked}")


@pytest.mark.parametrize("encrypt", ["none", "aes", "zipcrypto"])
def test_chinese_names_not_mojibake_via_cp437(tmp_path, encrypt):
    """反向验证不乱码：若误用 cp437/gbk 存名，标准库读出的名字会变乱码。
    这里断言读出的名字与原始中文完全一致（等价于 Windows 不乱码路径）。"""
    if encrypt == "aes":
        pytest.importorskip("pyzipper")

    root = _make_cn_dir(tmp_path)
    pw = None if encrypt == "none" else PW
    archive = assert_success(compress("zip", encrypt, root, pw=pw))

    with zipfile.ZipFile(archive) as zf:
        basenames = {n.rstrip("/").split("/")[-1] for n in zf.namelist()}
    for want in CN_NAMES:
        assert want in basenames, (
            f"中文名 {want!r} 未原样保留（疑似乱码），实际 basenames: {basenames}")
