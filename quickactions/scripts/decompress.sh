#!/bin/zsh
# 兼容入口：NSService 壳 App 按文件名调用它。逻辑已统一到 czip-menu.sh。
# 默认走「解压到此处」（先试无密码，加密包才问密码）。
exec "${0:A:h}/czip-menu.sh" here "$@"
