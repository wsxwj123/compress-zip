#!/bin/zsh
# 兼容入口：NSService 壳 App 按文件名调用它。逻辑已统一到 czip-menu.sh。
# 默认走「一键压成 zip」。要高级压缩用 czip-menu.sh compress。
exec "${0:A:h}/czip-menu.sh" zip "$@"
