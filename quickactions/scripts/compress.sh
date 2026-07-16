#!/bin/zsh
# 兼容入口：NSService 壳 App 按文件名调用它。逻辑已统一到 czip-menu.sh。
# 默认走「一键压成 zip」。要高级压缩用 czip-menu.sh compress。
exec "$HOME/tools/compress-zip/czip-menu.sh" zip "$@"
