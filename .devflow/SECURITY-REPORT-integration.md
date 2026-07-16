# 05.5 安全审计报告 —— 右键集成层（+ 核心复核）

审计方式：独立 opus 审计代理，攻击者视角，**构造真实恶意样本动态验证**（隔离 /tmp）。
对象：czip.py / zipcrypto.py 核心 + 集成层（czip-menu.sh / main.swift / Info.plist / install.command）。
（早前的 SECURITY-REPORT.md 针对旧 .workflow，集成层已全面重写，此报告为新对象。）

## 结论：修掉 1 个 DoS 后可安全发布

任意代码执行 / 逃出目录写文件 / 删覆盖用户数据 / 密码泄漏——**实测均未找到可行路径**。

## 🔴 致命：0

- ask_pw 注入（05 代码审查发现）→ 实证确认已堵（on run a + argv，非源码拼接）
- Zip Slip `../`、绝对路径、Windows 反斜杠 `..\`：zip/7z/tar.gz/rar **全格式拒绝**，逃逸文件零落盘
- symlink/hardlink 成员（顺链逃逸）：写入前一律拒绝 + 落地前 realpath 二次复核
- `__MACOSX/../evil`（垃圾跳过绕过 `..` 检查）：已修确认（`..` 检查在跳过之前）
- 解压失败/损坏包：dest 同名文件无伤、staging 残留 0（隔离 temp、成功才 rename）
- 同名已存在：不覆盖，避让 `xxx-1`
- 密码：env 传入、启动即 pop 不传子进程、argv/ps/日志/临时文件/报错全无明文；ZipCrypto 头 `os.urandom`、AES 走 pyzipper WZ_AES，无误用
- 带密码 rar：明确拒绝（避免密码落 unar argv）
- install.command：无 sudo、只写自身目录、无 quarantine 绕过
- 壳 App：pasteboard→path 同用户权限无越权，mode 每个 @objc 写死不可外控

## 🟠 重要：1（已修）

- **zip 炸弹 / 资源耗尽（DoS）**：解压把整个成员读进内存，815KB 高压缩比包 → 峰值 1.7GB，可 OOM/占满盘（不丢数据）。
  **已修** @f8e0327：改 `shutil.copyfileobj` 分块流式（_CHUNK=1MB），四格式同改，异常映射不变。实证峰值 1.7GB→75MB，内容完整；加 test_large_member 锁定。

## 🟡 建议（不影响发布，已处置）

1. 压缩跟随 symlink 可能打包 `~/.ssh` 等敏感内容 → 已在 README 已知局限注记
2. 7z 链接检测依赖 py7zr → 维持版本固定，升级时复验（备案）
3. 密码 env 同用户 `ps -E` 理论可见 → 本地单机工具威胁模型可接受（备案）
