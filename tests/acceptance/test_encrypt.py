"""加解密闭环（§5.2）：三种加密压出的包，用正确密码解出内容一致（退0），
用错误密码解退 4 且 stderr 含"密码错误"。zip 的 none/zipcrypto 为 stdlib 核心路径直接可跑；
aes 及 7z 需第三方库，importorskip 保护。
"""
import pytest

from helpers import (PW, compress, extract, assert_success, assert_error,
                     write_file, assert_contains_files)


def _payload(tmp_path):
    root = tmp_path / "src"
    files = {
        "文档.txt": b"\xe4\xb8\xad secret payload",
        "note.md": b"# hello\nline2\n",
        "data.bin": bytes(range(256)),
    }
    for name, data in files.items():
        write_file(root / name, data)
    return root, files


def _roundtrip(tmp_path, fmt, encrypt, need=None):
    if need:
        pytest.importorskip(need)
    root, files = _payload(tmp_path)
    pw = None if encrypt == "none" else PW
    archive = assert_success(compress(fmt, encrypt, root, pw=pw))

    dest = tmp_path / "out"
    dest.mkdir()
    folder = assert_success(extract(archive, dest=dest, pw=pw))
    assert_contains_files(folder, files)
    return archive


def test_zip_none_roundtrip(tmp_path):
    _roundtrip(tmp_path, "zip", "none")


def test_zip_zipcrypto_roundtrip(tmp_path):
    # 手搓 ZipCrypto，无第三方依赖，核心路径
    _roundtrip(tmp_path, "zip", "zipcrypto")


def test_zip_aes_roundtrip(tmp_path):
    _roundtrip(tmp_path, "zip", "aes", need="pyzipper")


def test_7z_none_roundtrip(tmp_path):
    _roundtrip(tmp_path, "7z", "none", need="py7zr")


def test_7z_aes_roundtrip(tmp_path):
    _roundtrip(tmp_path, "7z", "aes", need="py7zr")


def test_targz_none_roundtrip(tmp_path):
    _roundtrip(tmp_path, "targz", "none")


@pytest.mark.parametrize("encrypt,need", [
    ("zipcrypto", None),
    ("aes", "pyzipper"),
])
def test_wrong_password_extract(tmp_path, encrypt, need):
    if need:
        pytest.importorskip(need)
    root, _ = _payload(tmp_path)
    archive = assert_success(compress("zip", encrypt, root, pw=PW))

    dest = tmp_path / "out"
    dest.mkdir()
    result = extract(archive, dest=dest, pw="错误的密码wrong")
    # §4.2：退 4，子串"密码错误或压缩包已损坏"（含"密码错误"）
    assert_error(result, 4, "密码错误")


@pytest.mark.parametrize("encrypt,need", [
    ("zipcrypto", None),
    ("aes", "pyzipper"),
])
def test_empty_password_extract_encrypted(tmp_path, encrypt, need):
    """加密包但解压时 COMPRESS_PW 为空 → 退 4（§4.2）。"""
    if need:
        pytest.importorskip(need)
    root, _ = _payload(tmp_path)
    archive = assert_success(compress("zip", encrypt, root, pw=PW))

    dest = tmp_path / "out"
    dest.mkdir()
    result = extract(archive, dest=dest, pw="")
    assert_error(result, 4, "密码错误")
