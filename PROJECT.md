# PROJECT 状态账本 — compress-zip

> 唯一写者：主会话。子代理只读，Bug 通过返回报告回传由主会话登记。
> 走 dev-flow 全流程（标准任务）。

## 阶段进度
- 01 立项：✅ 完成 @3f974aa
- 02 方案：✅ 卡点1已确认
- 03 测试设计：✅ 卡点2已确认，验收测试锁定（LOCK 已落盘）
- 04 开发：✅ czip.py + zipcrypto.py 内核完成，解压逻辑重构已落地（命名归档/智能布局/拒链接/Zip Slip每成员复核）
- 05 验收：✅ 裁判合格（头号中文+数据安全达标）；BUG-01~04 全部已修
- 05.5 安全审计：✅ AppleScript 注入致命已修（argv 传参 @92dc9e9/ca04402）
- 🟢 访达右键集成：✅ **已定案并跑通**
  - **交付形态变更**：从"手写 .workflow 快捷操作"改为 **NSService 壳 App（CompressZip.app）**——手写 workflow 在 macOS 15 无法可靠登记进右键；壳 App 走 NSServices，机制同 MacZip，pbs 自动登记，稳定出现在「服务」子菜单
  - **OneDrive 关键结论**：用户重度用 OneDrive。所有右键增强 App（Menuist/超级右键等）靠 Finder Sync 扩展，在云盘文件夹里**一律失效**（File Provider 独占，苹果官方确认）。唯 NSServices 不受限 → 本方案在 OneDrive 里照常可用（用户已实测确认"在、能用"）
  - **Menuist 调研否决**：用户的右键增强 App 是 Menuist（闭源）——自定义脚本要付费会员，且在 OneDrive 里失效，放弃集成
  - **交互重设计**：czip-menu.sh 统一入口，四模式 zip(一键)/compress(高级)/here(解压到此处，加密才问密码)/to(解压到指定目录)；最常用动作零弹窗 @2525624
  - **沙盒鲁棒**：脚本不依赖 $HOME（${0:A:h} 定位 + id 反查真实家目录）@affc751
  - "藏太深"用键盘快捷键弥补（用户已自行绑定，NSKeyEquivalent 已登记生效）
  - install.command 已重写为"装内核+脚本 + 编译注册壳 App"，依赖检查修为 find_py 一致探测

## 待收尾
- [ ] 06 发布：push GitHub 公开仓库 wsxwj123
- [ ] 07 用户实测终审（右键压缩/解压 + OneDrive 场景已通过）
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
