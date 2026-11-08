# Streamlit Community Cloud 部署

部署入口使用 `cloud_app.py`，在 Advanced settings 中明确选择 **Python 3.12**。本地仍可运行 `streamlit run web_app.py`，知识目录默认保持项目原有布局。

本文说明部署适配；完成代码测试不等于云端已经部署。未上传知识数据、未替用户配置 Cloud Secrets，也未部署公开应用。

## 私有知识数据与使用授权

公开 GitHub 仓库只保存程序、无敏感值的配置示例和合成测试数据。Pollack、Greer 以及《周易》现代译注的全文、OCR、结构化牌义、chunks、向量及真实 API 密钥都不进入公开仓库。原始 PDF 不需要部署。

应用访问口令、私有存储和购买书籍本身不会自动赋予云端存储、处理或向模型服务发送内容的授权。管理员应先确认这些用途在其授权范围内；不能确认时，不上传该知识包。现代译注与公版古文应分别核实。若仅获准处理自有或明确许可资料，必须用相应的已授权知识集提供下述运行数据，并重新完成既有检索评估。

建议方案：把有处理授权的数据包放入管理员控制的**非公开 HTTPS 对象存储**，以短期签名 URL 或服务端 Bearer Token 下载。凭证只在 Streamlit Secrets 中配置；桶不开匿名读取，不通过 GitHub Releases、仓库附件或公开静态资源托管知识数据。访问应用还需输入独立口令，口令只发给有权访问该知识的用户。该口令是简易访问控制，不是独立用户账户；长期多人服务应增加 OIDC 身份验证与持久存储。

### 方案 A：私有数据包（Community Cloud 推荐）

本地先运行完整性检查，再在确认具有所需处理授权后打包。输出必须位于仓库之外；使用新文件名，工具拒绝覆盖已有包。

```bash
cd /Users/dengsonghao/Documents/Tarrot_Yi
.venv/bin/python -m rag.knowledge_check
.venv/bin/python -m scripts.package_private_knowledge \
  --output /Users/dengsonghao/Documents/private-deploy/tarot-knowledge-v1.tar.gz \
  --rights-confirmed
```

打包期间暂停摄取/索引写入，避免导出过程中集合发生变化。打包工具只读现有知识与向量，不调用任何 Embedding API。它导出三个集合的文档、元数据、ID 和现有向量，生成文件 SHA-256 清单，并输出数据包整体 SHA-256。每次更换数据包，都更新 Secrets 中的 URL 与校验值。

把包上传至自己的私有存储后，配置 `KNOWLEDGE_BUNDLE_URL` 和 `KNOWLEDGE_BUNDLE_SHA256`。云端会：

1. 在用户通过访问口令后下载数据；只接受 HTTPS，禁止跳转以保护 Bearer Token。
2. 校验包的 SHA-256；拒绝路径穿越、符号链接及超限压缩包。
3. 在私有目录解包并检查各文件 SHA-256。
4. 使用**已有的 1024 维向量**建立当前 Linux 平台的 Chroma ANN 文件；不重新请求 Embedding。
5. 完成三个集合、有效 ID、文本一致性、Greer 内容哈希和周易 OCR 页码检查后，才导入 RAG 模块。

默认存放位置：

```text
/tmp/tarot-private-knowledge/<bundle-sha256>/
├── data/
│   ├── deployment_manifest.json
│   ├── structured/{tarot_meanings,zhouyi_sections,hexagrams}.json
│   ├── extracted/zhouyi_pages.jsonl
│   └── chunks/{tarot_chunks,zhouyi_index_ready,greer_tarot_reversals_chunks}.jsonl
└── storage/
    ├── vector_exports/<collection>.jsonl
    └── chroma/                 # 本机恢复的数据库
```

`data/extracted/tarot_pages.jsonl`、`data/structured/tarot_sections.json`、`data/structured/greer_tarot_reversals_sections.json` 若本地存在，也会作为私有辅助资料打包，供章节检查工具使用。原书 PDF、个人历史、`.env` 不打包。

下载缓存使用进程间文件锁。同一包只恢复一次，失败时应用停止；若在恢复向量期间被强行中断，请配置新的 `KNOWLEDGE_CACHE_DIR` 后重启，或由管理员处理该私有缓存，程序不会自动删除数据。

### 方案 B：已有私有挂载目录

设置 `KNOWLEDGE_ROOT` 指向包含 `data/` 和 `storage/chroma/` 的私有目录。此方案需要部署平台提供该目录及同平台兼容的 Chroma 数据库；Community Cloud 不会自动挂载本地 Mac 的路径。

不配置 `KNOWLEDGE_BUNDLE_URL`，直接运行：

```bash
KNOWLEDGE_ROOT=/absolute/private/knowledge \
  .venv/bin/python -m rag.knowledge_check
```

## Streamlit Secrets

完整占位示例见 `.streamlit/secrets.toml.example`。在 Cloud 的 App settings / Secrets 中填写，或部署时粘贴到 Advanced settings。真实值不写进示例、不提交 `.streamlit/secrets.toml`。

```toml
SILICONFLOW_API_KEY = "你的私有值"
DEEPSEEK_API_KEY = "你的私有值"
DEEPSEEK_MODEL = "deepseek-chat"
APP_ACCESS_PASSWORD = "至少20字符的随机访问口令"
KNOWLEDGE_BUNDLE_URL = "https://你的私有服务/knowledge-v1.tar.gz?签名参数"
KNOWLEDGE_BUNDLE_SHA256 = "打包工具输出的64位十六进制值"
# 若服务采用 Bearer Token：
# KNOWLEDGE_BUNDLE_TOKEN = "你的私有值"
APP_RUNTIME_DIR = "/tmp/tarot-private-runtime"
API_GLOBAL_DAILY_UNITS = 160
API_SESSION_DAILY_UNITS = 24
API_COOLDOWN_SECONDS = 30
API_MAX_CONCURRENT = 2
```

`KNOWLEDGE_ROOT` 与 `KNOWLEDGE_BUNDLE_URL` 二选一。可选的 `KNOWLEDGE_CACHE_DIR` 默认 `/tmp/tarot-private-knowledge`。`TAROT_SOURCE_REGISTRY` 仍可指向来源配置；默认仓库中的 `configs/tarot_sources.yaml` 不变。Cloud 的 `APP_MODE=cloud` 由 `cloud_app.py` 强制设置。

更换目录、数据版本、来源配置或访问口令后重启应用，使导入时的知识对象和缓存统一刷新。Secrets/环境只接受配置值，不会显示在页面中。

## 数据路径审计

| 读取方 | 运行资料 | 部署路径 |
|---|---|---|
| `rag/hybrid_zhouyi.py` | 周易有效 chunks 与 ID 清单，导入时加载 | `KNOWLEDGE_ROOT/data/chunks/zhouyi_index_ready.jsonl` |
| `rag/exact_zhouyi.py` | 周易 OCR 与章节图，导入时加载 | `KNOWLEDGE_ROOT/data/extracted/zhouyi_pages.jsonl`、`data/structured/zhouyi_sections.json` |
| `rag/zhouyi_exact.py`、`rag/answer_zhouyi.py` | 按实际 PDF 页码读取 OCR | 同上 OCR 路径 |
| `rag/search_zhouyi.py`、`rag/hybrid_tarot.py` | 三个 Chroma 集合 | `KNOWLEDGE_ROOT/storage/chroma` |
| `rag/tarot_sources.py` | Pollack/Greer 有效 chunk 清单 | 注册表中相对路径解析到 `KNOWLEDGE_ROOT` |
| `rag/answer.py`、`engines/tarot_draw.py` | 78 张牌规范 ID 与精确牌义 | `KNOWLEDGE_ROOT/data/structured/tarot_meanings.json` |
| `knowledge/lookup.py` | 既有结构化卦资料 | `KNOWLEDGE_ROOT/data/structured/hexagrams.json` |
| `rag/section_lookup.py`（辅助工具） | Pollack 章节图和逐页文本 | 私有目录下对应 structured/extracted 文件 |
| 网页牌面图片 | 现有 78 个 JPG | 仓库 `assets/tarot`，不包含书籍知识全文 |
| 来源注册表 | 书目/集合名/路径配置 | 默认仓库 `configs/tarot_sources.yaml` |
| 网页历史与追问 | 当前会话的用户数据 | `APP_RUNTIME_DIR/sessions/<random-session-id>/` |
| 网页额度计数 | 仅随机会话号、时间、计数 | `APP_RUNTIME_DIR/usage.sqlite3` |

`rag/build_index.py`、`rag/build_zhouyi_index.py`、`rag/ingest_book.py` 和 `rag/evaluate_tarot.py` 是本地摄取/评估入口，不在云端启动时运行。不会为部署重新生成向量或修改已通过的检索、排序及引用处理。

## 启动完整性检查

网页启动前检查以下项目，缺一则停止并显示不含正文/密钥的诊断：

- 必需 JSON/JSONL 文件存在，78 张塔罗牌精确牌义齐备。
- 周易 OCR 页码唯一且完整覆盖章节图声明的页数，章节图包含 64 卦。
- 三个集合存在，向量维度为 1024，ANN 能使用现有向量查询。
- 每个来源的有效 ID 清单非空、无重复，所有有效 ID 存在于对应集合。
- 集合文档与清单文本一致，Greer 的内容哈希一致，覆盖 78 张牌。
- 周易 chunks 的引用页码存在于 OCR 页码清单。
- 两个 API Key 均已配置。

本次本地已核对：Pollack **841/841**（集合/有效清单）、周易 **688/688**、Greer **272/271**，周易 OCR **708 页**。Greer 额外一条旧记录仍由原检索器的有效清单过滤，检查只提示，不删除记录。

## 多用户历史与额度

每个 Streamlit 会话获得随机 128 位标识，历史枚举和追问写回都局限于其目录。网页不再写入共享的 `latest_yijing_cast.json`；CLI 的默认保存行为保留。原来的本地根目录历史文件未删除，但网页不再枚举这些无用户归属的共享旧记录。

当前会话隔离不提供跨设备登录或长期历史恢复：浏览器新建会话、Cloud 重启或实例回收都可能使历史不可恢复，页面已提醒及时导出。若要跨设备持久历史，应增加用户登录，并使用按用户授权的外部数据库；本次没有假装已提供这一能力。

额度在 SQLite 的 `BEGIN IMMEDIATE` 事务中预留，能防同一实例内并发绕过：完整联合解读预留 **8 单位**，追问预留 **2 单位**，失败也保留已预留额度。默认每会话每日 24、全应用每日 160，冷却 30 秒，同时 2 个操作。日界按 UTC，UI 输入最多 2000 字。

这些单位限制应用操作，不代表精确金额/Token 预算；SDK 重试、Token 数和价格会影响账单。会话额度可因新开会话而刷新，但同实例全局额度仍约束总量。`/tmp` 重启/实例回收后计数会重置，因此管理员还必须在 API 提供商设置预算或余额上限。跨实例、跨重启的硬性预算需要外部额度数据库，本次没有配置该服务。

## Python/Linux 依赖及验证

`requirements.txt` 锁定当前本地使用的 Streamlit、ChromaDB、OpenAI SDK、NumPy、Pillow、PyYAML、Requests、dotenv 和 filelock 版本。摄取用的 PyMuPDF 放到 `requirements-tools.txt`；应用启动不安装 PDF/OCR 系统工具，不需要 `packages.txt`。

已对 Python 3.12、Linux x86_64（manylinux2014/manylinux_2_28）执行全部运行依赖的二进制 wheel 解析，成功。**这只是依赖解析与 wheel 可用性验证，不等于在 Linux 上完整运行成功。** 本机 Docker daemon 不可用，未启动 Linux 容器。新增 `.github/workflows/linux-smoke.yml`，推送后可在 Ubuntu/Python 3.12 上执行无需真实私有知识的部署、引擎与追问测试；该工作流尚未在远程执行。

本地运行全部测试：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m rag.knowledge_check
```

部署安全测试使用合成数据，覆盖缺数据启动阻断、目录隔离、事务配额、并发请求、恶意压缩包拒绝、校验失败、缺失有效 ID、OCR 缺页以及现有向量恢复，不调用模型 API。

本次实际验证结果：全部 **40/40** 单元测试通过（包含原有 29 项）；本地 Streamlit AppTest 启动时异常 0、错误 0；`pip check` 通过。还使用真实本地知识在临时目录完成了一次“打包 → 安全解包 → 复用向量恢复 → 完整性检查”的往返验证，恢复后仍为 Pollack 841、周易 688、Greer 272（有效 271）、OCR 708 页，错误 0。测试用的私有包和恢复目录已随临时目录清除，没有上传。

## Git 提交与 Cloud 操作

先审阅变更；以下命令只暂存代码、文档及占位配置，不包含私有数据。未替用户提交或推送：

```bash
cd /Users/dengsonghao/Documents/Tarrot_Yi
git diff --check
git add -u
git add cloud_app.py requirements-tools.txt \
  rag/runtime_data.py rag/private_bundle.py rag/knowledge_check.py \
  rag/cloud_access.py rag/app_bootstrap.py \
  scripts/package_private_knowledge.py tests/test_cloud_deployment.py \
  docs/streamlit_cloud_deployment.md \
  .streamlit/config.toml .streamlit/secrets.toml.example \
  .github/workflows/linux-smoke.yml
git diff --cached --stat
git diff --cached --name-only
git commit -m "Prepare private knowledge runtime for Streamlit Community Cloud"
git push origin HEAD
```

检查暂存清单中没有 `.env`、真实 `secrets.toml`、`data/`、`storage/` 或知识压缩包。`.gitignore` 已覆盖这些内容；现有 Git 跟踪文件和可见历史中也未发现知识数据或真实 Secrets 路径。

在 Community Cloud 选择仓库 `SongHaoDeng1121/tarot-iching-agent`、需要的分支、入口 `cloud_app.py`、Python 3.12，填写 Secrets 后启动。检查远程 Linux CI 和 Cloud 日志，登录后检查能抽牌、显示牌面、完成经授权的解读；使用两个浏览器会话确认历史隔离，再验证额度限制。该远程步骤未执行前，不能声称部署成功。

官方说明：[部署与 Python 版本](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)、[依赖文件](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)、[Secrets 管理](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)。
