# PROJECT 状态账本 — compress-zip

> 唯一写者：主会话。子代理只读，Bug 通过返回报告回传由主会话登记。
> 走 dev-flow 全流程（标准任务）。

## 阶段进度
- 01 立项：✅ 完成 @3f974aa
- 02 方案：✅ 卡点1已确认
- 03 测试设计：✅ 卡点2已确认，验收测试锁定（LOCK 已落盘）
- 04 开发：✅ czip.py + zipcrypto.py 内核完成，解压逻辑重构已落地（命名归档/智能布局/拒链接/Zip Slip每成员复核）
- 05 验收：✅ 裁判合格（头号中文+数据安全达标）；BUG-01~04 全部已修
- 05.5 安全审计：✅ 两轮完成
  - 核心 czip.py：AppleScript 注入致命已修（argv 传参 @92dc9e9/ca04402）
  - 集成层专项审计（opus 实证攻击）：致命 0；ask_pw 注入实证已堵；Zip Slip/symlink/数据覆盖/密码泄漏全格式挡住；唯一 🟠 zip 炸弹 DoS 已修（改流式，峰值 1.7GB→75MB）@f8e0327。报告见 .devflow/SECURITY-REPORT-integration.md
- 05 代码审查（fable，右键集成层）：✅ 2 致命(ask_pw 注入 @a27c44c / NOMATCH glob @ffa5f8e) + 4 改进全修
- 🟢 访达右键集成：✅ **已定案并跑通**
  - **交付形态变更**：从"手写 .workflow 快捷操作"改为 **NSService 壳 App（CompressZip.app）**——手写 workflow 在 macOS 15 无法可靠登记进右键；壳 App 走 NSServices，机制同 MacZip，pbs 自动登记，稳定出现在「服务」子菜单
  - **OneDrive 关键结论**：用户重度用 OneDrive。所有右键增强 App（Menuist/超级右键等）靠 Finder Sync 扩展，在云盘文件夹里**一律失效**（File Provider 独占，苹果官方确认）。唯 NSServices 不受限 → 本方案在 OneDrive 里照常可用（用户已实测确认"在、能用"）
  - **Menuist 调研否决**：用户的右键增强 App 是 Menuist（闭源）——自定义脚本要付费会员，且在 OneDrive 里失效，放弃集成
  - **交互重设计**：czip-menu.sh 统一入口，四模式 zip(一键)/compress(高级)/here(解压到此处，加密才问密码)/to(解压到指定目录)；最常用动作零弹窗 @2525624
  - **沙盒鲁棒**：脚本不依赖 $HOME（${0:A:h} 定位 + id 反查真实家目录）@affc751
  - "藏太深"用键盘快捷键弥补（用户已自行绑定，NSKeyEquivalent 已登记生效）
  - install.command 已重写为"装内核+脚本 + 编译注册壳 App"，依赖检查修为 find_py 一致探测

## 阶段进度（续）
- 06 发布：✅ 公开仓库 https://github.com/wsxwj123/compress-zip ，master 全量推送，CI(macOS pytest) 绿
  - 直推 master（未走 PR：初次发布 + 两账号/代理摩擦下从简；后续变更走 feature 分支+PR）
  - 建仓账号切换：wsxwj123（gh 两账号，owner 级操作切 wsxwj123 建仓、完事切回 euphoriaaaaaa1）
  - CI 首跑失败(无 pytest + pip/python 指向不同解释器)→ 修(python -m pip 装 pytest)→ 绿
- 07 用户实测终审：🔄 进行中
  - ✅ 右键服务在访达（含 OneDrive 文件夹）出现且可用
  - ⏳ 待用户确认：4 菜单项齐全、加密压缩(第2项)→解压输密码 全链在本机顺畅

## 待收尾
- ⚠️ 已知局限：默认原地解压外部"无顶层前缀扁平包"到已存在同名目录时可能覆盖同名文件；本工具自压的包无此问题

## Bug 台账
| 编号 | 现象 | 状态 | 发现者 | 修复 commit |
|------|------|------|--------|------------|
| BUG-01 | 解压失败会删掉同名已有目录→丢数据 | ✅已修 | code-review | 654cd85 |
| BUG-02 | 7z损坏包误判密码错退4(应退1) | ✅已修 | code-review | 654cd85 |
| BUG-03 | encrypt_dirs死参数+注释不符 | ✅已修 | code-review | 654cd85 |
| BUG-04 | 7z/RAR3 symlink 误判 | ✅已修 | code-review | b46cf77 |

**关键教训**：裁判(只看行为测试)判合格，但代码有致命删数据bug——验收测试漏测"失败时源文件是否保留"。code-review 补盲区的价值在此坐实。测试盲区已补(2条数据安全测试)。

## 关键决策
- 交付形态：命令行内核 + **NSService 壳 App**（右键「服务」集成，非 workflow、非 Finder Sync）——理由见"访达右键集成"
- 格式：压缩 zip/7z/tar.gz；解压广覆盖含 rar；不做 rar 创建
- 加密：AES-256 + ZipCrypto 两种，压缩时选
- 头号目标：中文名 Windows 解压不乱码（UTF-8 + 标志位，可自动验证，无需真 Windows）
- 原文件：绝不删除/覆盖，同名改名避让
- 发布：GitHub 公开仓库
- 格式调研用 sonnet（用户指定），其余调研/审查/裁判用 opus
