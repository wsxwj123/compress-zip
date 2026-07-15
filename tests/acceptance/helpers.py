"""黑盒验收测试的公共工具。

约定：czip.py 位于项目根（tests/acceptance 的上上级）。
一切通过子进程调用 czip.py + 检查退出码/stdout/stderr/产物，绝不 import 内部模块。
密码只走环境变量 COMPRESS_PW。
"""
import os
import sys
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CZIP = PROJECT_ROOT / "czip.py"

# 需要密码的加密方式统一用这个密码（含中文/emoji/符号，顺带验证密码不必是纯 ASCII）
PW = "P@ss中文123🔒"


def require_czip():
    """实现尚未落地时跳过，而不是报错——保证 `pytest tests/acceptance/` 现在可收集可跑。"""
    if not CZIP.exists():
        pytest.skip(f"czip.py 尚未实现: {CZIP}")


def run_czip(*args, pw=None, extra_env=None, cwd=None, timeout=180):
    """调用 czip.py。pw=None → 不设 COMPRESS_PW；pw="" → 设为空串；pw="x" → 设为 x。"""
    require_czip()
    env = os.environ.copy()
    env.pop("COMPRESS_PW", None)
    if pw is not None:
        env["COMPRESS_PW"] = pw
    if extra_env:
        env.update(extra_env)
    argv = [sys.executable, str(CZIP), *[str(a) for a in args]]
    return subprocess.run(
        argv, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=env, cwd=str(cwd) if cwd else None, timeout=timeout,
    )


def compress(fmt, encrypt, *inputs, pw=None, out=None):
    args = ["compress", "--format", fmt, "--encrypt", encrypt]
    if out is not None:
        args += ["--out", str(out)]
    args += ["--", *[str(i) for i in inputs]]
    return run_czip(*args, pw=pw)


def extract(archive, dest=None, pw=None):
    args = ["extract"]
    if dest is not None:
        args += ["--dest", str(dest)]
    args += ["--", str(archive)]
    return run_czip(*args, pw=pw)


def stdout_path(result):
    """成功输出必须恰好一行绝对路径。"""
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 1, f"stdout 应恰好一行，实际: {result.stdout!r}"
    p = lines[0].strip()
    assert os.path.isabs(p), f"stdout 应为绝对路径: {p!r}"
    return Path(p)


def assert_success(result):
    """成功契约（§1.5/§2.4）：退 0、stderr 空、stdout 一行绝对路径且产物存在。"""
    assert result.returncode == 0, (
        f"退出码应为 0，实际 {result.returncode}；stderr={result.stderr!r}")
    assert result.stderr.strip() == "", f"成功时 stderr 应为空: {result.stderr!r}"
    p = stdout_path(result)
    assert p.exists(), f"产物应存在: {p}"
    return p


def assert_error(result, code, substr):
    """业务错误契约（§4）：对应退出码、stdout 空、stderr 含稳定子串。"""
    assert result.returncode == code, (
        f"退出码应为 {code}，实际 {result.returncode}；"
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    assert substr in result.stderr, (
        f"stderr 应含子串 {substr!r}，实际: {result.stderr!r}")
    # 业务错误时 stdout 必须为空（避免误把错误当成功路径解析）
    assert result.stdout.strip() == "", f"错误时 stdout 应为空: {result.stdout!r}"


def write_file(path, content=b"hello"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode("utf-8")
    path.write_bytes(content)
    return path


def collect_files(root):
    """收集 root 下所有普通文件：basename -> bytes。用于内容一致性比对，
    避免对内部 arcname 目录层级做过度假设。"""
    out = {}
    for p in Path(root).rglob("*"):
        if p.is_file():
            out.setdefault(p.name, p.read_bytes())
    return out


def assert_contains_files(extracted_root, expected):
    """expected: {basename: bytes}。断言解出物里能找到每个文件且内容一致。"""
    got = collect_files(extracted_root)
    for name, data in expected.items():
        assert name in got, f"解出物缺文件 {name!r}；实际有 {list(got)}"
        assert got[name] == data, f"文件 {name!r} 内容不一致"
