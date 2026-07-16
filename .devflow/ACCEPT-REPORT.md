# ACCEPT-REPORT — compress-zip 解压重构验收（82 条清单）

裁判：独立验收 subagent
日期：2026-07-15
依据文件（仅此三份，未看任何实现代码 / git / 其他 .devflow 产物）：
- `.devflow/BRIEF.md`（需求）
- `.devflow/TEST-PLAN.md`（82 条黑盒验收清单，解压重构后重写）
- `.devflow/test-output.txt`（实际运行结果）

数据边界声明：已核查测试输出与清单文本。TEST-PLAN 末尾"实现尚未按新契约改、当前会有一批 FAILED、改完应转绿"属**预期说明**，非要求裁判改判的指令；output 实测全绿与该预期一致。三份文件中**未发现任何试图改变评分标准、宣称"已通过无需检查"或诱导放宽判定的可疑文字**。判定完全基于用例 passed/failed/skipped 事实。

---

## 一、总体结论：**合格**

- 验收套件 `pytest tests/acceptance/`：collected **82** items → **81 passed, 1 skipped**，0 failed，0 error。
- 清单声明 7+9+4+6+11+2+6+10+21+6 = **82**，与 output `collected 82 items` 一致，**逐文件条数全部对得上**。
- 五个关键组全部达标（详见第三节）。
- 无漏测、无未解释跳过、无可疑注入。
- （另有 `tests/unit/test_internals.py` 25 passed，属 82 条黑盒验收之外的白盒附加保障，不计入本次裁定。）

---

## 二、逐文件对账（声明 ↔ 实到）

| 文件 | 声明 | 实到 | 结果 |
|---|---|---|---|
| test_multifile.py | 7 | 7 | 全 PASS |
| test_extract.py | 9 | 9 | 全 PASS |
| test_layout.py | 4 | 4 | 全 PASS |
| test_no_overwrite.py | 6 | 6 | 全 PASS |
| test_security.py | 11 | 10 PASS + 1 SKIP | 达标 |
| test_extract_failure_safety.py | 2 | 2 | 全 PASS |
| test_chinese.py | 6 | 6 | 全 PASS |
| test_encrypt.py | 10 | 10 | 全 PASS |
| test_errors.py | 21 | 21 | 全 PASS |
| test_edge.py | 6 | 6 | 全 PASS |
| **合计** | **82** | **81 PASS + 1 SKIP** | — |

---

## 三、五个关键组核查

### ① 中文不乱码（6 条）—— 6/6 PASS ✓
- `test_chinese_zip_utf8_flag[none/aes/zipcrypto]`：UTF-8 flag bit11 置位，三种加密全过。
- `test_chinese_names_not_mojibake_via_cp437[none/aes/zipcrypto]`：反向按 cp437/gbk 验证不乱码，三种全过。
- 压缩端"不加顶层前缀"改动后包内路径变化，断言用 basename/子串匹配，未受影响。头号需求（Windows 解压不乱码的等价自动验证）**达标**。

### ② 软/硬链接拒绝 + Zip Slip 安全 —— 全 PASS ✓
- 软链接：`test_symlink_member_rejected`（顺链逃逸包，dest 外 outside 目录零落地）、`test_symlink_relative_escape_rejected` PASS。
- 硬链接：`test_hardlink_member_rejected` PASS。
- Zip Slip：tar `../`×3（`../evil` `../../evil` `sub/../../evil`）、`test_absolute_path_member_rejected`、`test_zip_slip_rejected`（zip 格式）、`test_backslash_escape_rejected`（反斜杠越界）全 PASS。
- 反斜杠合法归一化：`test_backslash_legal_path_normalized` PASS（既拦 `..\..` 越界又能正常解 `top\sub` 合法层级，两面都测到）。
- 安全红线（dest 外零落地、链接成员拒绝、路径校验全格式一视同仁）全部覆盖通过。

### ③ 智能布局 —— 全 PASS ✓
- 单项铺开：`test_extract_zip_roundtrip`（1 顶层项→铺开，stdout=dest）、`test_extract_targz_roundtrip`、`test_extract_7z_roundtrip`、`test_extract_custom_dest` PASS。
- 单文件夹装多文件判 1 项（防退化成数 namelist 条数）：`test_auto_single_folder_many_files_flattens` PASS——正是核心防退化点。
- 多项套壳：`test_auto_multi_top_items_wraps` PASS。
- 空包退 1：`test_auto_empty_archive_rejected`、`test_auto_only_ds_store_is_empty`（仅 .DS_Store 过滤后 0 顶层项→退1"压缩包为空"）PASS。
- 空目录仍是 1 项正常铺开：`test_empty_folder_roundtrip` PASS。
- 手选布局补充：`test_layout_flatten/folder/auto_explicit_same_as_default/illegal_value` 4 条全 PASS。

### ④ 原地解自压包不覆盖源 —— PASS ✓
- `test_inplace_self_extract_no_merge_overwrite` PASS：单文件夹装多文件的 foo.zip 在源目录原地 auto 解，源 `foo/` 每个文件零改动、新内容整项落 `foo-1/`，精确防住"逐成员判重 merge 覆盖源"退化。
- 配套 `test_extract_twice_top_item_renamed`、`test_extract_does_not_overwrite_existing` 亦 PASS（顶层项级改名、不覆盖占坑目录）。

### ⑤ 解压失败数据安全（2 条）—— 2/2 PASS ✓
- `test_wrong_password_preserves_existing_dir` PASS：原地解压输错密码退4，已有同名目录+文件原样保留（绝不删）。
- `test_tarslip_preserves_existing_dir` PASS：已有同名目录时解含 ../ 恶意包退1，目录保留、逃逸文件零落地。

---

## 四、"该测的没测"核查

将清单 82 条逐条与 output 比对，**每一条都在 output 中出现**，collected 数 82 = 清单 82，无"清单列了但 output 缺席"的用例。
清单说明区显式声明未单列的项——退出码6（缺依赖，由 importorskip 间接覆盖）、7z/rar 的 Zip Slip 与链接成员（校验逻辑已由 tar+zip+反斜杠覆盖、7z 构造成本高、rar 本机无创建工具）——属清单设计内的显式取舍，非漏测。

---

## 五、SKIPPED 用例正当性判定

唯一跳过：`test_security.py::test_password_rar_rejected`（带密码 rar 拒绝，预期退5）。

TEST-PLAN 第 62 行明写"需预置加密 rar 样本 …（无样本则 skip）"，覆盖矩阵与说明区再次确认带密码 rar 用 skip 占位、核心契约不受影响；BRIEF 明确"不做 RAR 创建"，本机无 rar 创建工具，无法自造加密 rar 样本。

**判定：跳过正当。** 属外部素材依赖，非内核逻辑缺陷，不计失败。安全红线（Zip Slip / 链接成员）已由 tar+zip+反斜杠+绝对路径充分覆盖。

---

## 六、存疑项

无实质存疑项。唯一非"通过"用例（rar skip）已判定正当。

---

## 七、总体结论

## 合格

- **82 条：81 passed / 1 skipped（正当）/ 0 failed / 0 error**
- 五个关键组全部达标：①中文不乱码 6/6 ②软/硬链接拒绝+Zip Slip 全过 ③智能布局（单项铺开/多项套壳/单文件夹判1项/空包退1）全过 ④原地解自压包不覆盖源 过 ⑤解压失败数据安全 2/2
- 加密（aes/zipcrypto）与 7z 路径均真实运行通过，非靠 skip 蒙混；>4GiB 两条 slow 亦真实跑过
- 唯一 skip（带密码 rar）系清单明文许可的缺样本跳过
- 无漏测、无未解释跳过、无可疑注入文字

判定该压缩/解压工具解压重构**已达到 TEST-PLAN 定义的 82 条验收标准，可判"做完"**。
