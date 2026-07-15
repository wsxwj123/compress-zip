# TEST-PLAN — compress-zip 黑盒验收清单

> 全部基于 INTERFACE.md 的黑盒契约：子进程调 `czip.py` → 查退出码 / stdout / stderr / 产物。
> 密码只走环境变量 `COMPRESS_PW`，不 import 内部模块。
> 位置：`tests/acceptance/`，跑法：`pytest tests/acceptance/`（未实现时全部 skip，不报错）。
> 标 ★ = 替用户想到的（需求没明说、但按常理必须对）。
> 依赖第三方库的用例用 `importorskip` 保护；核心（中文 zip / 错误契约 / 不覆盖 / zipcrypto）纯 stdlib 直接可跑。

格式：场景 / 怎么操作 / 预期看到什么

---

## test_chinese.py — 头号验收（中文名不乱码，项目成败关键，6 条）
- 中文名压 zip(none) / 用 zipfile 打开生成包 / 每个中文条目 flag_bits&0x800==0x800，中文名原样在包内
- 中文名压 zip(aes) / 同上（需 pyzipper） / 加密不影响文件名头部，bit11 仍置位
- 中文名压 zip(zipcrypto) / 同上（手搓路径，无第三方依赖） / bit11 置位、中文名正确
- ★ 反向验不乱码 zip(none) / 读出的 basename 与原中文逐一相等 / 没走 cp437/gbk 乱码路径
- ★ 反向验不乱码 zip(aes) / 同上 / 加密路径也不乱码
- ★ 反向验不乱码 zip(zipcrypto) / 同上 / 手搓加密路径也不乱码
  （中文集覆盖：纯中文、中英混、带空格、全角括号、emoji 文件名）

## test_encrypt.py — 加解密闭环（10 条）
- zip+none 往返 / 压后解、比对内容 / 退0，解出文件内容一致
- zip+zipcrypto 往返 / 正确密码解 / 退0，内容一致（核心，无依赖）
- zip+aes 往返 / 正确密码解（需 pyzipper） / 退0，内容一致
- 7z+none 往返 / 需 py7zr / 退0，内容一致
- 7z+aes 往返 / 需 py7zr / 退0，内容一致
- targz+none 往返 / 压后解 / 退0，内容一致
- zip+zipcrypto 错密码解 / COMPRESS_PW 给错值 / 退4，stderr 含"密码错误"
- zip+aes 错密码解 / 需 pyzipper / 退4，含"密码错误"
- ★ zip+zipcrypto 空密码解加密包 / COMPRESS_PW="" / 退4（加密包必须要密码）
- ★ zip+aes 空密码解加密包 / 需 pyzipper / 退4

## test_errors.py — 错误契约 §3/§4（21 条，纯 stdlib）
- 缺 --format / compress 不给 --format / 退2，stderr 含 usage:
- 缺 --encrypt / 不给 --encrypt / 退2，usage:
- 非法 --format(rar) / / 退2，usage:
- 非法 --encrypt(rc4) / / 退2，usage:
- 无 PATH / 只给选项不给输入 / 退2，usage:
- targz+aes / / 退5，"tar.gz 不支持加密"
- targz+zipcrypto / / 退5，"tar.gz 不支持加密"
- 7z+zipcrypto / / 退5，"7z 不支持 ZipCrypto 加密"
- aes 空密码压缩 / COMPRESS_PW="" / 退4，"该加密方式需要密码，但未提供"
- zipcrypto 空密码压缩 / 同上 / 退4，同串
- ★ aes 未设 COMPRESS_PW 压缩 / 变量完全不存在 / 退4（"未设"也算空）
- ★ zipcrypto 未设 COMPRESS_PW / 同上 / 退4
- 输入不存在 / PATH 指向不存在文件 / 退3，"找不到输入"
- 多输入其一不存在 / 一真一假 / 退3，"找不到输入"
- 写入失败 / --out 指向不存在父目录 / 退1，"写入失败"
- ★ 校验顺序：格式 vs 输入 / 非法 format + 不存在 PATH / 退2（format 先于 input）
- ★ 校验顺序：密码 vs 输入 / 空密码 aes + 不存在 PATH / 退4（密码先于 input）
- extract 缺 ARCHIVE / 只给 extract / 退2，usage:
- extract 包不存在 / / 退3，"找不到输入"
- extract 不支持格式 / .xyz 文件 / 退5，"不支持的压缩包格式"
- extract 损坏包 / 真 zip 截断一半 / 退1，"压缩包损坏或不完整"，不崩栈

## test_no_overwrite.py — 不删不覆盖 §1.4/§2.3（5 条，纯 stdlib）
- 同名压两次三次 / 连压 3 次同一输入 / 依次 name.zip / name-1.zip / name-2.zip，前包都还在
- --out 目标已存在 / --out 指到已占坑文件 / 生成 backup-1.zip，原文件字节不变
- ★ 压缩不动源 / 压完比对源目录 / 源文件内容/存在性完全不变（只读输入）
- 解压两次 / 同包解两次到同 dest / 落 name / name-1 两个子文件夹，都在
- ★ 解压不覆盖占坑目录 / dest 下预置同名目录放文件 / 避让到 name-1，占坑文件不被动

## test_extract.py — 解压主路径 §2（5 条）
- zip 往返 / 默认 dest 解压 / 子文件夹=包去扩展名，落包所在父目录，内容一致
- targz 往返 / / 包名 树.tar.gz，解出去掉整体扩展名，内容一致
- 7z 往返 / 需 py7zr / 内容一致
- --dest 指定 / 解到自选父目录 / 子文件夹落在 --dest 下，内容一致
- ★ 空文件夹往返 / 压空目录再解 / 退0，解出后空目录仍保留

## test_multifile.py — 多选 + 输出命名 §1.3（4 条，纯 stdlib）
- 单文件命名 / 压单个 报告.txt / 包名 报告.txt.zip，落同目录
- 单目录命名 / 压 资料/ / 包名 资料.zip
- 同目录多选 / 三文件同父目录 / 包名=父目录名，落该目录，解出三文件齐全
- 跨目录多选 / dir1/首个 + dir2/第二 / 落 dir1、包名=首个.txt.zip，解出两文件齐全

## test_security.py — 安全边界 §2.3/§5.7（5 条）
- tar-slip ../ / 构造含 ../evil 成员的 tar.gz / 退1，"压缩包含非法路径"
- tar-slip ../../ / 同 / 退1，同串
- tar-slip sub/../../ / 同 / 退1，同串
  （★ 以上三条都额外断言：dest 之外确实无逃逸文件落地，不只看退出码）
- 绝对路径成员 / 成员名 /tmp/... / 退1，"压缩包含非法路径"，且该绝对路径无文件
- 带密码 rar 拒绝 / 需预置加密 rar 样本 / 退5，"不支持带密码的 rar 解压"（无样本则 skip 并说明）

## test_extract_failure_safety.py — 解压失败数据安全（2 条，补 code-review 发现的删数据盲区）
- ★ 原地解压密码错 / 源目录含文件、压成加密包、原地解压时输错密码 / 退4，且已有同名目录+文件原样保留（绝不删）
- ★ 原地解压 tar-slip / 已有同名目录、解含 ../ 的恶意包 / 退1，且已有同名目录保留、逃逸文件零落地

## test_edge.py — 边界/替用户想到的（6 条）
- ★ 名字带空格 / "文件 名.txt" 压解 / 往返内容一致
- ★ 名字带 emoji / "🚀火箭.txt" 压解 / 往返内容一致
- ★ symlink 跟随(文件) / 输入含指向文件的软链 / 解出存的是目标内容、普通文件
- ★ symlink 跟随(目录) / 软链指向目录 / 解出含目录内文件内容
- ZipCrypto >4GiB 退5 / 稀疏文件桩造 4GiB+1 逻辑体积 / 退5，"ZipCrypto 不支持超过 4GB..."（标 slow）
- ★ AES >4GiB 无限制(对照) / 同稀疏桩走 aes / 绝不触发 4GiB 组合限制（标 slow，需 pyzipper）

---

## 覆盖矩阵小结
| 方向 | 覆盖 |
|---|---|
| 正向主路径 | zip/7z/targz 压+解往返、内容一致；none/aes/zipcrypto 加解密闭环 |
| 头号（中文 zip 头部） | none/aes/zipcrypto ×（flag 断言 + 反向不乱码），共 6 条 |
| 错误契约 §4 | 退出码 1/2/3/4/5 全覆盖；stderr 稳定子串；§3 校验顺序 2 条 |
| 不删不覆盖 | 压两次改名、--out 占坑避让、源不被动、解两次落 -1、占坑目录不被动 |
| 多选 + 命名 §1.3 | 单文件/单目录/同目录多选/跨目录多选 4 种命名规则 |
| 安全 §2.3 | tar-slip（3 种 ../ 形态 + 绝对路径）、dest 外零落地、带密码 rar |
| 边界 | 空格/emoji/空目录/symlink（文件+目录）/超 4GiB |

## 说明
- 退出码 6（缺依赖）：无法在有依赖的环境里稳定构造，未单列断言；由 importorskip 间接覆盖（缺库时相关用例 skip）。
- 退出码 1「写入失败」的解压侧、7z 成员穿越：未单列（tar-slip 已代表穿越防护主逻辑）。
- 带密码 rar、超大文件：需外部样本/大体积，分别用 skip 与 slow 标记；核心契约不受影响。
