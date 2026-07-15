"""pytest 配置：注册 slow 标记，并保证本目录在 sys.path 上（helpers 可 import）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: 慢用例（构造大文件等），可用 -m 'not slow' 跳过")
