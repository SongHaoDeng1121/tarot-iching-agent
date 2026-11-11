# 周易章节解析故障修复

日期：2026-11-11（Asia/Shanghai）。本次是代码修复，不需要私有知识快照 v3。

## 根因与准确复现

六爻从下到上为 `[8, 8, 6, 8, 7, 7]`：本卦 20《观》，第三爻为老阴六三，变卦 53《渐》。现有起卦引擎得到这一结果，与网页显示一致，未发现卦序映射错误。

实际调用链：

```text
cast_hexagram / build_cast_result
  -> 网页显示已经确定的本卦、动爻、变卦
  -> web_app.generate_joint（先执行塔罗解读）
  -> run_reading（重用同一组六爻值，不重新起卦）
  -> build_exact_evidence
  -> retrieve_cast_evidence
     -> get_chapter(20) -> 用第21卦章首确定观的终点
     -> find_moving_line(观, 六三)
     -> get_chapter(53) -> 用第54卦归妹章首确定渐的排他终点
  -> 周易 DeepSeek 解读与页码审计
  -> fuse_readings
```

查找《归妹》属于**章节终点定位**，不是内容检索扩展、不是变卦变成归妹，也不是增加第三个解读卦。旧实现依赖全书严格标题正则匹配，并要求标题后紧邻 `【题解】`。

原始 OCR 的 PDF 489 页标题为 `归1妹（王）`，中间多出 ASCII 数字 `1`；旧正则只允许汉字之间出现空白，因此无法定位。异常在给《渐》寻找终点时抛出，周易生成和 Fusion 都尚未开始。这是解析代码对真实 OCR 结构的处理缺陷，由 OCR 标题噪声触发。

原来的完整证据调用已经使用上述六爻值复现了完全相同的错误：`无法定位《归妹》章首…`，调用栈位于 changed_chapter -> get_chapter(53) -> find_chapter_heading(归妹)。

## 全 64 卦审计

实际结构表为 `index_type=provisional_page_boundaries`；64 卦的 `end_boundary_verified` 均为 false。它包含正确的候选页码及 `heading_context_ocr`，但不能直接拿重叠页全文当成已经验证的章节。

修复前章节解析成功 **57/64**，失败为：

| 失败章节 | 原因 |
|---|---|
| 24 复、25 无妄 | 无妄的 OCR 标题为“无安”，使前一卦终点和本卦起点均失败 |
| 32 恒、33 遯 | 引擎规范名为“遯”，原书及结构表使用“遁” |
| 53 渐、54 归妹 | 归妹的 OCR 标题中插入数字 1 |
| 64 未济 | 旧代码没有第64卦的附录终点规则，直接拒绝解析 |

修复后 **64/64** 成功，相邻章节共用的排他终点/起点逐一一致。审计详情见 `reports/deployment/zhouyi_chapter_resolution_audit.json`，不包含原书全文。

## 修复方式与来源完整性

新增 `rag/zhouyi_boundaries.py`，由 `get_chapter()` 使用：

1. 使用现有结构表指定的页面定位；校验卦序、规范名、相邻关系和结束页一致性。
2. 在该页识别紧邻 `【题解】` 的唯一标题，取得真实字符偏移，不把整张边界页归给一章。
3. 标题层做全角/半角、空白及夹入数字的规范化；支持有文献依据的遯/遁标题变体，不改抽卦规范 ID。
4. 若 OCR 标题本身有错字，要求它精确匹配结构表记录的原始 OCR 标题，并在限定的本章引言中同时出现重复目标卦名及该卦自己的卦辞标题。没有通用模糊替换或“无安=无妄”的硬编码字表。
5. 交叉确认不从下一章所在的共享边界页借用正文；一个明确属于其他卦的合法标题不能因正文提到目标卦而被重标。
6. 第64卦以结构表中的首个附录为候选终点，再确认实际 OCR 的“周易系辞上”标题和 `【题解】`；不会直接延伸到文件末尾。
7. 缺页、矛盾索引、重复候选或不足的正文确认均报错，不回退到语义检索或别的章节。
8. 终点解析失败时，错误明确说明“请求章节的结束边界”对应哪个章节，避免再次把边界查找误解为卦象映射错误。

本次未把原结构表的待审核标记改成已审核，也未编辑 OCR。所谓“已核实”证据来自运行时实际交叉确认的标题/偏移，不能据此声称全书已经人工校对。

## 观 → 渐、六三的实际证据

| 证据类型 | 目标 | 本次送入模型的 PDF 页 |
|---|---|---|
| original_hexagram | 观 | 209–216 |
| moving_line | 观·六三 | 214–215 |
| changed_hexagram | 渐 | 480–487 |

《渐》的完整章节范围为 PDF 480 页偏移 255，至 PDF 489 页偏移 160（排他）。归妹在该边界之后的正文不进入《渐》章节。本次送入模型的是章节引言窗口，因此只到 PDF 487 页。

《归妹》自身解析范围为 PDF 489:160 至 497:301。第64卦在 PDF 580:0 截止，未包括系辞上传。

## 本地联合解读与引用验证

通过 Streamlit AppTest 点击网页真实的“开始双系统解读与 Fusion 综合分析”按钮执行，未替换生成函数。使用观→渐六三及固定测试三牌（星币五正位、圣杯国王正位、星币四正位）；用户没有提供失败现场的塔罗牌和问题，因此这里的三牌及通用测试问题不是对现场塔罗输入的推断。

结果保存在 `reports/deployment/guan_jian_fusion_validation.json`，仅保留证据和审计元数据，不保存书籍正文或真实用户历史：

- 三张牌、六爻值及动爻在生成过程中未改变。
- 网页启动异常 0、错误 0。
- 塔罗注册来源 15 条：6 条精确来源、9 条混合检索来源，两位作者均有证据。
- 精确 ID 包括 `EXACT_POLLACK_five_of_pentacles`、`EXACT_GREER_five_of_pentacles_UPRIGHT`，其余各牌 ID 和页码见 JSON。
- 周易精确链路不使用 Chroma 检索 ID；它按 `type/name/pages` 登记直接 OCR 证据，实际仅有观、观·六三、渐三组。
- 周易模型引用页码为 209、210、211、212、214、215、481、482，全部位于实际供给证据中；`unsupported_pages=[]`，原严格页码审计通过。
- Fusion 返回 **678 字符**综合解读；没有显式 PDF 页码引用，因此未发现新增未供给页码。这不等于对其每一句综合解释都完成了文献语义核验。
- 本次塔罗未知 ID 为 0，但 **6 条精确证据未以标准 ID 引用**，所以完整引用验收不是全部通过。

此前 DeepSeek 把 `POLLACK/GREER` 写成混合大小写的引用风险仍未修复。本次没有重现大小写错误，但出现漏引；不能据一次运行宣称生成引用已稳定。既有 `check_citations()` 和 `audit_page_citations()` 均未修改。新增回归测试明确断言混合大小写 ID 和未供给页码仍会被判为无效。

## 测试结果

- 全部 **62/62** 单元/本地知识回归测试通过，无跳过。
- 64 卦实际 OCR 章节解析 **64/64** 通过；修复前为57/64。
- 已观察六爻的直接复现与修复后证据测试通过。
- 新增测试覆盖同页多章、夹入数字、遯/遁、标题错字的多重确认、借用下章证据的拒绝、错卦名/错页元数据、缺页、重复标题、第64卦终点及严格引用校验。
- 将已有私有完整快照解包到干净临时目录，再用当前代码进行64卦审计，仍为64/64；无需修改包内容。
- Chroma 集合最终计数仍为 Pollack 841、周易 688、Greer 272；没有删除、重建或重新生成已有 Embedding。
- 临时联合解读记录在独立测试目录中自动清除，未写入用户现有历史。

本次覆盖全部章节端点和现场六三，不声称已经穷尽检查所有384个动爻 OCR 标题。

## 是否需要私有快照 v3

**不需要。** 修改仅涉及代码、测试和不含正文的审计报告。

本地两份私有资料与现有 `tarot-knowledge-full-20261109.tar.gz` 中对应文件 SHA-256 一致：

- `data/structured/zhouyi_sections.json`：`5c03db4a61be6f9b738fac108d1010be583d933f7103057413fe24148977aa5c`
- `data/extracted/zhouyi_pages.jsonl`：`e88ebdb2f9c2b6779bea8977c36eec6ba4ec55ab59e765af322429215f4508a9`

保持现有数据仓库 commit SHA、数据包 SHA-256 及 Streamlit Secrets，不重新上传数据，不清空 Chroma 或私有缓存。若以后人工修订私有结构表或 OCR，届时才需新快照、数据提交 SHA、包 SHA-256 和 Secrets 更新。

## 修改文件

- 修改 `rag/zhouyi_exact.py`：生产路径改为精确结构/OCR 边界，旧严格探测器仅保留作审计基线。
- 新增 `rag/zhouyi_boundaries.py`：通用边界交叉确认。
- 新增 `tests/test_zhouyi_boundaries.py`：合成数据回归。
- 新增 `tests/test_zhouyi_knowledge.py`：私有 OCR 的64卦和现场六三回归；无私有资料的公开环境会跳过此集成测试。
- 新增 `scripts/audit_zhouyi_chapters.py`：全卦旧/新解析对比。
- 新增 `scripts/verify_guan_jian_fusion.py`：网页真实联合流程验证；有引用审计问题时以非零状态结束。
- 新增本报告及两个 JSON 审计结果。

未修改抽卦引擎、Fusion 提示、私有知识文件、密钥或依赖版本。

## 精确复验、Git 与部署命令

```bash
cd /Users/dengsonghao/Documents/Tarrot_Yi
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.audit_zhouyi_chapters \
  --output reports/deployment/zhouyi_chapter_resolution_audit.json
.venv/bin/python -m scripts.verify_guan_jian_fusion
```

实际 API 联合测试（会计费；若塔罗漏引/未知 ID 或页码审计失败，命令返回非零）：

```bash
.venv/bin/python -m scripts.verify_guan_jian_fusion --online \
  --output reports/deployment/guan_jian_fusion_validation.json
```

仅提交代码、测试和审计元数据，命令尚未代为执行：

```bash
git diff --check
git add rag/zhouyi_exact.py rag/zhouyi_boundaries.py \
  scripts/audit_zhouyi_chapters.py scripts/verify_guan_jian_fusion.py \
  tests/test_zhouyi_boundaries.py tests/test_zhouyi_knowledge.py \
  reports/deployment/zhouyi_chapter_resolution_fix.md \
  reports/deployment/zhouyi_chapter_resolution_audit.json \
  reports/deployment/guan_jian_fusion_validation.json
git diff --cached --name-only
git commit -m "Fix OCR-aware I Ching chapter boundary resolution"
git push origin main
```

当前本地分支为 main。Streamlit Cloud 拉取新 main 代码后，在 Manage app 菜单中 Reboot app，使 Python 模块与缓存一起重新加载；保持原来的 `cloud_app.py` 入口和所有知识源 Secrets。随后重新发起阅读。若要精确回归同一卦，请运行上述固定六爻脚本，不依赖随机抽卦再次碰到该组合。

本次没有提交、推送或操作线上部署，不能声称云端修复已经验证。
