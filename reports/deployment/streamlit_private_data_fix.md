# Streamlit 私有 RAG 数据缺失修复

日期：2026-11-09（Asia/Shanghai）。

## 当前状态

已完成代码适配、完整本地快照、干净目录恢复、应用启动与实际 RAG/API 验证。未上传知识包、未创建私有仓库或 Token、未修改 Cloud Secrets，也未推送应用代码。线上部署尚未验证成功。

用户已在本次对话确认：拥有将书籍衍生的结构化文本、OCR、chunks 和向量存放于 GitHub 私有仓库并用于当前云端应用的所需授权。此确认不等于数据已上传。

## 根因与审计

本地知识目录不会随 Streamlit 从公开代码仓库部署而自动出现。项目的 `.gitignore` 正确排除了 `data/structured/`、`data/extracted/`、`data/chunks/`、`storage/chroma/`、原书 PDF、`.env` 和真实 Streamlit Secrets。故需要独立私有数据源，而不是把知识文件加入公开代码仓库。

审查到的启动器原本只支持通用 HTTPS 数据包；代码中没有 Cloudflare R2 专用集成，也没有需要移除的 R2 依赖。此前 v1 数据包导出向量并创建目标数据库，本次改用完整目录快照 v2，直接恢复 SQLite 与索引目录，不重建集合。

实际 Cloud 管理后台的入口文件和 Secrets 本次未能检查；不能断言其具体配置。应按下述步骤把入口设置为 `cloud_app.py`。对 `https://tarrot-yi-agent.streamlit.app/` 的网页读取/浏览器加载未成功，因此未核验线上当前界面，更未核验线上修复结果。

### 必需运行资料

以下文件全部在本地存在且通过 readiness 检查：

| 路径 | 读取方/用途 |
|---|---|
| `data/structured/tarot_meanings.json` | 塔罗牌规范 ID、抽牌牌库与 Pollack 精确证据 |
| `data/structured/zhouyi_sections.json` | 周易章节图与卦名识别 |
| `data/structured/hexagrams.json` | 既有结构化卦资料查找 |
| `data/extracted/zhouyi_pages.jsonl` | 周易按 PDF 页码精确取证与引用检查 |
| `data/chunks/zhouyi_index_ready.jsonl` | 周易词法检索和有效 ID 映射 |
| `data/chunks/tarot_chunks.jsonl` | Pollack 词法/混合检索 |
| `data/chunks/greer_tarot_reversals_chunks.jsonl` | Greer 精确牌义、正逆位与有效 ID 清单 |
| `storage/chroma/chroma.sqlite3` **及全部索引目录** | 三个现有 Chroma 集合 |

真实本地数据库路径：`/Users/dengsonghao/Documents/Tarrot_Yi/storage/chroma/`，约 33 MiB。完整目录含 3 个 UUID 索引目录、12 个 `.bin` 文件；不是仅有 SQLite。

| 集合 | 实际记录数 | 有效清单数 |
|---|---:|---:|
| `tarot_bge_m3_v1` | 841 | 841 |
| `zhouyi_bge_m3_v1` | 688 | 688 |
| `tarot_greer_reversals_bge_m3_v1` | 272 | 271 |

周易 OCR 为 708 页。Greer 额外 1 条旧向量仍按原有有效 ID 逻辑过滤，保留原记录。本次没有删除、重建或重新嵌入任何现有集合。

原书 PDF、历史记录、缓存与密钥不属于此次部署快照。牌面图片和书目注册配置继续由现有代码仓库提供。启动前 readiness 检查仍然执行，并未绕过。

## 私有 GitHub 方案及限制

采用独立私有数据仓库，通过 GitHub Contents API 的 raw 媒体类型下载压缩包。GitHub Free 支持私有仓库；不需要 Cloudflare R2、LFS 或信用卡计费服务。

本次快照约 15.6 MiB，低于 GitHub 网页上传 25 MiB、普通 Git 文件 100 MiB 和 Contents API 100 MB 的上限。适合当前小型部署资源。不要把仓库作为高频数据库备份服务堆积快照；若未来超过当前大小限制，应停止此路线并重新评估，而不是自动选择付费服务。

官方依据：[GitHub Free](https://docs.github.com/en/get-started/learning-about-github/githubs-plans)、[文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、[Contents API 与细粒度 Token 的 Contents: read 权限](https://docs.github.com/en/rest/repos/contents)。

## 已准备的本地快照

文件：

`/Users/dengsonghao/Documents/private-deploy/tarot-knowledge-full-20261109.tar.gz`

- 大小：**16,388,678 字节**（约 15.6 MiB）。
- SHA-256：`8648e30ddda165beac628207a5c1f59e41e348f039b16ad58b0d1440e7c631c5`。
- 格式版本：2，`complete_chroma_directory`。
- ChromaDB 版本：1.5.9。
- 源平台：Darwin-arm64；原生目录跨平台的最终兼容性仍须由实际 Cloud Linux 环境验证。
- 压缩包：21 个文件，其中 12 个向量索引 `.bin` 文件。
- 内部清单：`data/deployment_manifest.json`，记录每个文件的 SHA-256、集合计数、OCR 页数和 ChromaDB 版本。
- 不含 PDF、`.env`、Secrets、用户历史或向量导出副本。

快照工具完整复制 Chroma 目录，并使用 SQLite backup API 生成一致的 SQLite 文件；检查复制前后本地知识文件未变化。复制后的独立数据库通过 SQLite integrity_check 和既有 readiness 检查，集合计数一致。哈希清单在验证后写入；最终数据包位于公开仓库之外，权限为仅用户读写。

快照中的 `.bin` 文件都按 SQLite `segments` 表登记的向量目录核对，缺少任一目录或必需文件时启动器拒绝恢复。

日后重新制作快照（暂停摄取/索引写入，使用新文件名）：

```bash
cd /Users/dengsonghao/Documents/Tarrot_Yi
.venv/bin/python -m scripts.snapshot_private_knowledge \
  --output /Users/dengsonghao/Documents/private-deploy/tarot-knowledge-full-NEWVERSION.tar.gz
```

## 启动恢复机制

1. 从 Secrets 或环境读取 GitHub 配置；无远程源时，本地仍使用原目录。
2. 检查 `owner/repository`、固定 40 位数据 commit SHA、相对文件路径和 Token。
3. 通过 GitHub 元数据 API 确认仓库 `private=true`；若是公开仓库则拒绝下载。
4. 使用 Authorization Header 下载 raw 文件，不把 Token 拼入 URL，也不记录响应正文。禁止 HTTP 跳转，防止凭证被转发到其他主机。
5. 在带文件锁的私有临时目录下载，校验压缩包 SHA-256；拒绝超限文件、路径穿越、链接和额外文件。
6. 核对完整文件清单、逐文件 SHA-256、SQLite 完整性、向量索引目录和 ChromaDB 版本。
7. 在短生命周期子进程中执行原有 readiness 检查，校验三个集合和 OCR；子进程退出后关闭数据库句柄。
8. 写入就绪标记并原子重命名到 `/tmp/tarot-private-knowledge/<SHA-256>/`，然后设置 `KNOWLEDGE_ROOT`；此后才为网页导入 RAG 模块。
9. 同一实例的后续启动复用带正确标记的缓存，不重复下载。若下载或验证失败，未完成目录不会被安装，也不会成为运行知识目录。

不会覆盖本地项目数据，也不调用集合创建/删除、索引重建或 Embedding 生成来恢复 v2 快照。v1 旧格式保留兼容分支；本次使用 v2。

## 文件变更

修改：

- `rag/private_bundle.py`：私有 GitHub 读取、完整快照校验、验证后原子安装、安全错误提示。
- `rag/app_bootstrap.py`：读取 GitHub Secrets，识别此私有源，展示不含凭证的诊断。
- `.streamlit/secrets.toml.example`：GitHub 只读来源占位示例。
- `docs/streamlit_cloud_deployment.md`：指向当前 v2 修复说明。

新增：

- `scripts/snapshot_private_knowledge.py`：完整一致目录快照。
- `scripts/verify_private_snapshot.py`：本地模拟 GitHub 传输、完整恢复、启动及 RAG/API 验证。
- `tests/test_private_github_snapshot.py`：私有来源、Token 失败、固定提交、目录攻击、不完整 Chroma 和原子失败测试。
- 本报告。

未修改抽牌、起卦、检索排序或引用验证逻辑；未修改本地依赖环境。

## 手动设置步骤

### 1. 提交应用代码

仅提交代码与本报告，不把快照放到公开代码仓库中：

```bash
cd /Users/dengsonghao/Documents/Tarrot_Yi
git diff --check
git add rag/private_bundle.py rag/app_bootstrap.py \
  .streamlit/secrets.toml.example docs/streamlit_cloud_deployment.md \
  scripts/snapshot_private_knowledge.py scripts/verify_private_snapshot.py \
  tests/test_private_github_snapshot.py \
  reports/deployment/streamlit_private_data_fix.md
git diff --cached --name-only
git commit -m "Restore private RAG snapshot from private GitHub storage"
git push origin main
```

这些命令尚未代为执行。

### 2. 创建并上传到独立私有数据仓库

1. 在 GitHub 手动创建仓库，例如 `SongHaoDeng1121/tarot-iching-private-data`，明确选择 **Private**。该名称为建议，本次没有创建。
2. 在这个**私有仓库**使用 Add file → Upload files，把上述 `.tar.gz` 上传到仓库根目录并提交。当前包小于网页上传限制。
3. 在文件历史中打开这次提交，复制完整 **40 位 commit SHA**。
4. 确认仓库仍显示 Private，且文件名为 `tarot-knowledge-full-20261109.tar.gz`。

不要把这个包上传到公开的 `tarot-iching-agent` 仓库，也不要设为公开 Release 或公开下载链接。

### 3. 创建细粒度只读 Token

在 GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens：

- Resource owner：数据仓库所属账户。
- Repository access：**Only select repositories**，只选择私有数据仓库。
- Repository permissions：**Contents: Read-only**；Metadata 的隐含只读权限保留。
- 不授予 Contents 写入、Workflows、Administration 或无关仓库访问权限。
- 设置有效期；若组织要求批准，等待批准。
- Token 仅填入 Streamlit Secrets，不贴到聊天、终端命令、Git remote 或代码文件中。

本次未创建 Token，也没有得到真实数据仓库 Token，因此未执行真实 GitHub 私有下载。

### 4. 配置 Streamlit Secrets

在 `tarrot-yi-agent` 应用的 Settings → Secrets 中配置；替换两个仓库/提交占位值与 Token，保留自己的 API 密钥：

```toml
KNOWLEDGE_GITHUB_REPOSITORY = "SongHaoDeng1121/tarot-iching-private-data"
KNOWLEDGE_GITHUB_REF = "替换为数据仓库40位commitSHA"
KNOWLEDGE_GITHUB_PATH = "tarot-knowledge-full-20261109.tar.gz"
KNOWLEDGE_GITHUB_TOKEN = "替换为细粒度只读Token"
KNOWLEDGE_BUNDLE_SHA256 = "8648e30ddda165beac628207a5c1f59e41e348f039b16ad58b0d1440e7c631c5"

APP_ACCESS_PASSWORD = "保留或设置至少20字符的随机访问口令"
SILICONFLOW_API_KEY = "保留自己的私有值"
DEEPSEEK_API_KEY = "保留自己的私有值"
DEEPSEEK_MODEL = "deepseek-chat"
```

删除旧的 `KNOWLEDGE_BUNDLE_URL`（如有），不要同时启用两种远程源；删除指向本地 Mac 路径的 `KNOWLEDGE_ROOT`（如有）。无需配置 R2。可选缓存目录：

```toml
KNOWLEDGE_CACHE_DIR = "/tmp/tarot-private-knowledge"
APP_RUNTIME_DIR = "/tmp/tarot-private-runtime"
```

原有额度设置继续使用。不要把上述真实值写进公开仓库的示例文件。

### 5. 重启并实际验收

确认 Cloud 的应用入口为 `cloud_app.py`、Python 为 3.12，安装锁定的 ChromaDB 1.5.9。保存 Secrets 后 Reboot app。输入访问口令后，下载器检查私有仓库并恢复知识；若失败，查看安全诊断，检查 Token 有效期、仓库权限、数据提交与文件路径。

进入提问/抽牌页面说明启动检查通过，但还需实际完成一次解读，并确认页面文献出处与引用检查。不要仅凭 Streamlit 的 HTTP 健康检查宣称 RAG 完成。

## 测试结果

| 项目 | 实际结果 |
|---|---|
| 全部单元测试 | 47/47 通过 |
| 全部必需文件存在 | 通过 |
| SQLite integrity_check | 通过 |
| 完整包/文件 SHA-256 | 通过 |
| 独立目录恢复后三个集合 | 841 / 688 / 272，与本地相同 |
| OCR 页码 | 708 页，完整且唯一 |
| GitHub 协议与私有属性检查 | 模拟响应测试通过；尚无真实私有仓库 Token |
| 重启缓存 | 复用成功，第二次恢复不发起下载 |
| 不可用资源/错误 Token/公开仓库 | 安全阻断，不激活半成品目录 |
| SQLite-only 不完整快照 | 在初始化 Chroma 前拒绝 |
| 恢复后的 Streamlit AppTest | 异常 0、错误 0，提问输入框 1 |
| 塔罗随机抽牌 | 3 张不同卡牌，方向结构正常 |
| 周易随机起卦 | 6 爻正常 |
| Pollack 精确检索 | 三张测试牌各 1 条专属证据，共 3 条 |
| Greer 精确检索 | 三张测试牌各 1 条，共 3 条；魔术师逆位带 PDF 56–58（含正位背景） |
| 真实塔罗混合检索 API | 6 条结果，两位作者来源均返回 |
| 真实周易混合检索 API | 讼卦九二问题首条 `zhouyi_p0095_c000`，PDF 95 |
| DeepSeek 实际生成 | 返回 3134 字符答案 |
| DeepSeek 引用校验 | **未通过：5 个大小写错误的证据 ID，3 条 Pollack 精确证据未以正确 ID 引用** |
| Cloud 真实部署 | **尚未验证** |

证据页码样例：Pollack 魔术师 PDF 46–51、星币皇后 252–253、星币十 256–259；Greer 魔术师 56–58、星币皇后 222、星币十 190–191。以上为恢复后实际送入模型的元数据；本次未逐页重新人工审阅原书 PDF。

生成引用失败的 ID 包括 `EXACT_Pollack_the_magician` 等，模型把标准的 `POLLACK` / `GREER` 大写改成混合大小写。保留严格验证，未把这些 ID 当成合法引用，也未修改既有检索/引用逻辑。完整端到端验收因此还有引用质量限制，不能报告全部通过。

可复现命令（`--online` 会调用现有 API，可能计费；只生成查询向量，不重新嵌入知识库）：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.verify_private_snapshot \
  --snapshot /Users/dengsonghao/Documents/private-deploy/tarot-knowledge-full-20261109.tar.gz
.venv/bin/python -m scripts.verify_private_snapshot \
  --snapshot /Users/dengsonghao/Documents/private-deploy/tarot-knowledge-full-20261109.tar.gz \
  --online
```

在线验证若发现引用审计失败会以非零状态结束。模拟 GitHub 下载只是本地验证传输协议、恢复和启动流程，不能代替真实 GitHub Token 下载及 Cloud Linux 验收。

## 剩余限制与阻塞

1. 私有数据仓库上传、细粒度只读 Token、Cloud Secrets 与应用代码推送仍需手动完成。
2. 真实 GitHub 私有下载和 Cloud Linux 环境尚未验证；Mac 原生快照如遇平台兼容错误，程序会停止，而不会擅自重建集合。
3. 本次 DeepSeek 回答出现 ID 大小写错误，严格引用审计失败；这与缺文件问题独立，未放宽现有校验。
4. GitHub Contents API HTTP 跳转被拒绝；如实际响应使用跳转，应先安全审查目标主机再扩展，而不能转发私有 Token。
5. 账号口令与会话历史隔离沿用现有实现；云端临时存储回收后会重新下载，同实例配额计数并非跨重启的硬性费用预算。

完成上述真实配置与验收前，不能声称 `https://tarrot-yi-agent.streamlit.app/` 已修复上线。
