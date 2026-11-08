# 错误排查报告（v1.0 审计）

> 本报告记录 AI-Study-Assistant v1.0 原型（commit `165b2c8`，`app.py` 共 874 行）的缺陷审计结果，
> 包括问题定位、根因、复现方式、实测证据与修复计划。
> 报告随缺陷修复持续更新；缺陷编号固定（BUG-xx），便于在 issue、提交信息与代码注释中引用。

| 项目 | 内容 |
| --- | --- |
| 报告版本 | v1.0（2026-11-08 首次审计） |
| 审计对象 | `main` @ `165b2c8`（`app.py` 874 行） |
| 审计环境 | Windows 10/11 · Python 3.11.15（conda `ai-study`）· Streamlit 1.38.0 · ChromaDB 0.5.5 · Ollama 0.33.2 |
| 审计方法 | 代码走查 + 本地运行时探针 + 依赖核对 + 文档一致性检查 |
| 结论 | 主流程可跑通；存在 **2 个 P0、6 个 P1** 及若干 P2/P3 缺陷，建议按 Roadmap 修复后再对外展示 |

## 1. 结论摘要

1. **检索质量（P0）**：所谓 Hybrid Search 对中文实际退化为纯向量检索（BUG-01）；归一化 + 固定阈值会让检索结果数不稳定、通常只剩 1 条（BUG-03）。这两点直接决定问答质量，是“经不起追问”的根源。
2. **数据持久性（P0）**：向量库使用内存实例（BUG-02），刷新页面或重启应用后知识库全部丢失；且每次“Process Documents”都会删除重建集合，分批上传无法累积。
3. **健壮性（P1）**：chunk 参数组合可触发死循环（BUG-04）；总结/复习模式答非所问（BUG-05）；长文档摘要被截断（BUG-06）；metadata 冗余（BUG-07）。
4. **工程化（P2/P3）**：无测试、无 CI、无日志；生成请求无超时；模型下拉框不区分类型；存在死代码与未使用依赖。

## 2. 缺陷总览

| ID | 等级 | 位置（`app.py`） | 问题 | 状态 |
| --- | --- | --- | --- | --- |
| BUG-01 | P0 | 445–466 | 中文关键词检索失效（空格分词） | Open |
| BUG-02 | P0 | 753 | ChromaDB 内存模式，知识库不持久 | Open |
| BUG-03 | P1 | 507–538 | Min-Max 归一化 + 固定 0.3 阈值，分数不可解释 | Open |
| BUG-04 | P1 | 320–342、686–687 | chunk 参数未校验，可死循环卡死 | Open |
| BUG-05 | P1 | 822–829 | 总结/复习模式仍按问题检索 top-k | Open |
| BUG-06 | P1 | 344–375 | 整篇文档一次性摘要，长文被截断 | Open |
| BUG-07 | P1 | 730–737 | 每个 chunk 重复存储整份摘要/预览 | Open |
| BUG-08 | P2 | 820 | 所有文档摘要无条件进入 Prompt | Open |
| BUG-09 | P2 | 664–681 | 模型下拉框不区分对话/Embedding 模型 | Open |
| BUG-10 | P2 | 255–259 | 生成请求无 timeout、无恢复 | Open |
| BUG-11 | P2 | 217–230 | Embedding 逐条请求，未批量 | Open |
| BUG-12 | P2 | 486–493 | 向量化失败返回 None 直接用于查询 | Open |
| BUG-13 | P2 | 808、821、438 | 记忆窗口把当前问题算入历史（off-by-one） | Open |
| BUG-14 | P3 | 255–259、829–832 | 使用 `/api/generate` 而非 `/api/chat` | Open |
| BUG-15 | P3 | 377、2、5、15、636–637 | 死代码与未使用导入 | Open |
| BUG-16 | P3 | 全仓库 | 无测试/CI/日志；依赖与文档问题 | Open |
| BUG-17 | P3 | 822–827 | 分支缩进 25 空格，违反 PEP8 | Open |
| BUG-18 | P2 | 489–529 | 全量查询 + Python 侧排序，KB 增大后变慢 | Open |
| BUG-19 | P3 | 310–311、305 | `.xls` 用 openpyxl 打开会失败；PDF 空页静默 | Open |
| BUG-20 | P3 | 716–719 | 文件去重缓存仅会话内有效，重复上传仍重新处理 | Open |

等级说明：P0 = 阻断性/核心功能失效；P1 = 显著影响质量或稳定性；P2 = 稳定性/性能/易用性；P3 = 工程质量。

## 3. 缺陷明细

### BUG-01（P0）中文关键词检索失效，Hybrid 退化为纯向量检索

- **位置**：`app.py:445-466`（`keyword_search`），核心逻辑 `app.py:459`、`app.py:463`。
- **现象**：中文问题（如“什么是快速排序”）在关键词检索中得分为 0，关键词分支完全不参与融合；英文问题才可能命中。
- **根因**：`query.lower().split()` 按空白字符分词。中文句子没有空格，整句变成 1 个 token；文档侧同样按空格切分，中文长句基本无法与之精确匹配。
  ```python
  query_words = set(query.lower().split())            # app.py:459
  doc_words = set(doc['content'].lower().split())     # app.py:462
  score = len(query_words.intersection(doc_words)) / len(query_words)  # app.py:463
  ```
- **实测证据**（本地探针，2 个中文文档片段，query=“什么是快速排序”）：
  - `keyword_search` 得分：`{'0': 0.0, '1': 0.0}` → 关键词分支全 0。
  - 归一化后 keyword 全 0 → 融合分数退化为 `semantic / 2`，即纯向量结果。
- **影响**：README/简历中宣称的“Hybrid Search”对中文不成立；专业术语、缩写、代码标识符等关键词信号全部丢失。
- **修复建议**：引入 `jieba` 中文分词（含自定义词典），实现真正的 BM25（或 `rank_bm25`）；关键词检索返回未归一化的原始分，交由 RRF 融合。
- **验收标准**：中文查询下关键词分支能命中至少一个片段；构造 10 条中文查询的对比评测，BM25、向量、RRF 三种方式的命中率/NDCG 有可量化差异。

### BUG-02（P0）ChromaDB 使用内存实例，知识库不持久

- **位置**：`app.py:753` `chroma_client = chromadb.Client()`。
- **现象**：刷新页面或重启 Streamlit 后知识库丢失，需要重新上传处理；分批上传也不能累积（每次 Process 会删除并重建集合，见 `app.py:762-771`）。
- **实测证据**：探针输出 `is_persistent = False`（`chromadb.Client()` 为内存实现，非 `PersistentClient`）。
- **影响**：与“个人课程知识库”的产品定位直接冲突；每次使用都要重跑解析 + 摘要 + 向量化，耗时且烧算力。
- **修复建议**：改用 `chromadb.PersistentClient(path="data/chroma")`（路径加入 `.gitignore`）；以文件哈希/文档 ID 为单位增量写入，避免整库重建；提供“清空知识库”按钮。
- **验收标准**：Process 后重启应用，知识库仍在；同会话分批上传两次，两份资料都能被检索到。

### BUG-03（P1）归一化分数 + 固定 0.3 阈值，结果数不稳定且不可解释

- **位置**：`app.py:507-538`（归一化 511–521、融合 524–529、阈值 532–538）。
- **现象**：检索返回条数与预期不符；中文场景下经常只返回 1 条（`num_chunks=4` 不生效）；页面展示的“相关度”不是余弦相似度，无法解释。
- **根因**：对每个候选集的分数做 Min-Max 归一化，最高分必然被映射为 1.0，因此融合分 = `(1.0 + keyword)/2`，最高分至少 0.5，必然越过 0.3；但第二名通常归一化后远低于 0.6，`fused < 0.3` 被过滤，导致只剩 top-1。阈值的含义随候选集分布漂移，且展示给用户的是融合分而非原始相似度。
- **实测证据**（4 个片段，中文查询）：
  - `sem_norm = [1.0, 0.2955, 0.1136, 0.0]`
  - `fused    = [0.5, 0.1477, 0.0568, 0.0]`
  - `fused >= 0.3` 只有 1 条 → 实际上下文只有 1 个 chunk。
- **修复建议**：放弃 Min-Max 融合；向量检索用真实余弦相似度（Chroma 用 `hnsw:space="cosine"`，分数 = 1 - distance），阈值只作用在余弦相似度上（如 0.5，可配置）；关键词与向量用 RRF（Reciprocal Rank Fusion）做排名融合，不混用分数尺度；页面展示展示真实相似度或排名。
- **验收标准**：同一查询下返回条数等于 `min(num_chunks, 命中数)`；展示分数与余弦相似度一致（误差 < 1e-6）。

### BUG-04（P1）chunk 参数可触发死循环

- **位置**：`app.py:341`（`start += chunk_size - chunk_overlap`）配合 UI `app.py:686-687`（chunk_size 100–2000，overlap 0–500）。
- **复现**：`chunk_size=100`、`chunk_overlap=500` → 步长 `100 - 500 = -400`，`while start < len(text)` 永不结束，页面卡死、CPU 占满。
- **修复建议**：入口校验 `0 <= overlap < chunk_size`；切分逻辑改为 `start = end - overlap`（保证前进）；UI 增加联动约束（overlap 上限 = chunk_size - 1）。
- **验收标准**：对所有合法参数组合（含 chunk_size=100、overlap=500 的非法组合被 UI/函数拒绝）处理 1 万字符文本能在 1 秒内完成。

### BUG-05（P1）总结 / 复习模式仍按问题做 top-k 检索

- **位置**：`app.py:822-829`（`study_mode` 分支只切换 Prompt 模板），检索固定发生在 `app.py:816`。
- **现象**：“总结这篇文档”这类问题仍以问题文本做相似度检索，只取 top-4 片段；若问题与正文表述差异大，模型拿到的上下文与“总结”目标无关，容易答非所问或只总结局部。
- **修复建议**：总结模式走全文路径（按文档取全部 chunk，必要时 map-reduce：分块摘要 → 合并摘要）；或提供“按文档/按章节总结”的显式入口；问答模式才使用相似度检索。
- **验收标准**：对 1 篇 20 页 PDF 提问“总结全文”，回答覆盖文档主要章节要点（人工评估或 LLM 打分）。

### BUG-06（P1）整篇文档一次性摘要，长文档被截断

- **位置**：`app.py:344-375`（`summarize_document`），Prompt 在 `app.py:362`。
- **现象**：长 PDF 的文本一次性拼进 Prompt，超出模型上下文窗口后被截断；摘要只覆盖前半部分，且浪费大量 token。
- **修复建议**：分块摘要（map）→ 汇总（reduce）；或先提取目录/标题结构再分节摘要。
- **验收标准**：20 页以上文档摘要能覆盖文末章节内容。

### BUG-07（P1）metadata 冗余：每个 chunk 重复存整份摘要

- **位置**：`app.py:730-737`（每个 chunk 的 `metadata` 都包含 `summary` 与 `preview`）。
- **影响**：文档摘要被复制 N 份（N=chunk 数），向量库/内存/Prompt 体积放大；`preview` 可由 `content[:150]` 现场计算，无需存储。
- **修复建议**：摘要按文档单独存储（`summaries[filename]` 已有），metadata 只保留 `source`、`chunk` 与必要字段。

### BUG-08（P2）所有文档摘要无条件进入 Prompt

- **位置**：`app.py:820`。
- **影响**：多文档时 Prompt 膨胀，且未命中文档的摘要构成噪声，稀释检索上下文。
- **修复建议**：仅注入与检索结果相关文档的摘要，或按 token 预算裁剪。

### BUG-09（P2）模型下拉框不区分对话 / Embedding 模型

- **位置**：`app.py:664-681`（两个下拉框都用 `st.session_state.models`）。
- **现象**：把 `llama3.1` 选成 Embedding 模型 → `/api/embed` 返回 400；把 `paraphrase-multilingual` 选成对话模型 → 生成失败。
- **修复建议**：通过模型名/已知清单过滤，或在 UI 中明确标注“Embedding 模型 / 对话模型”；给出默认值。

### BUG-10（P2）生成请求无超时、无错误恢复

- **位置**：`app.py:255-259`（`requests.post(..., stream=True)` 未设置 `timeout`）。
- **影响**：Ollama 无响应时页面无限等待；无重试与降级策略。

### BUG-11（P2）Embedding 逐条请求，未批量

- **位置**：`app.py:217-230`（`for text in texts` 逐条 POST）。
- **影响**：几百个 chunk 需要几百次网络往返，处理时间被放大数倍。
- **修复建议**：Ollama `/api/embed` 的 `input` 支持数组，按批（如 32 条）提交。

### BUG-12（P2）向量化失败后 None 直接传入查询

- **位置**：`app.py:486-493`。
- **现象**：`embed_documents` 异常时返回 `None`，`collection.query(query_embeddings=None)` 抛出未捕获异常。
- **修复建议**：显式判断并给出用户可理解的提示；失败时终止本轮问答。

### BUG-13（P2）记忆窗口 off-by-one

- **位置**：`app.py:808`（先 append 当前问题）、`app.py:821` 与 `app.py:438`（取最近 `memory_size*2` 条）。
- **现象**：当前问题被算进历史，导致真正的上一轮对话被挤掉；`get_chat_history` 的配对起点也可能错位。
- **修复建议**：先取历史再 append；或从 `messages[:-1]` 构建历史；`/api/chat` 原生支持 role 数组更稳妥。

### BUG-14（P3）使用 /api/generate 而非 /api/chat

- **位置**：`app.py:255-259`、`app.py:829-832`。
- **影响**：所有角色/历史被压成一条字符串，模型对对话结构的理解弱于 `/api/chat` 的 messages 数组。

### BUG-15（P3）死代码与未使用导入

- `app.py:377` `process_documents()` 定义后从未调用（主流程在 `main()` 内重复实现）。
- `app.py:2` `from streamlit_chat import message` 未使用。
- `app.py:5` `from pathlib import Path` 未使用。
- `app.py:15` `from collections import Counter` 未使用。
- `app.py:636-637` `previous_embedding_model` 只写不读。

### BUG-16（P3）工程化缺失

- 无单元测试 / 评测脚本 / CI / logging。
- `requirements.txt` 锁定旧版 `streamlit==1.38.0`，且包含未使用的 `streamlit-chat==0.1.1`。
- README 原有问题：图片 Markdown 语法错误（`![alt]<img ...>`）、`git clone <...>` 尖括号语法错误、末尾残留调试笔记“400/500 报错请修改代码”。

### BUG-17（P3）分支缩进 25 空格

- `app.py:822-827` 的 if/elif/else 分支缩进为 25 空格（应为 24/28 的对齐风格），功能正常但不符合 PEP8，阅读混乱。

### BUG-18（P2）全量查询 + Python 侧排序

- `app.py:489-529`：`collection.query(n_results=total_docs)` 全量取回再在 Python 里归一化、融合、排序。知识库变大后每次问答都要传输并排序全部向量结果。
- **修复建议**：Chroma 侧取 top-k（如 20）后再融合；或使用 `where` 过滤。

### BUG-19（P3）文件解析边界

- `app.py:310-311`：`.xls`（旧版 Excel 二进制格式）用 `openpyxl` 打开会抛异常，应使用 `xlrd` 或提示仅支持 `.xlsx`。
- `app.py:305`：PDF 页面 `extract_text()` 可能返回空串/None，扫描版 PDF 会被静默跳过（有 `except` 兜底但无用户提示）。

### BUG-20（P3）文件去重仅会话内有效

- `app.py:716-719`：`processed_file_hashes` 只存在 `st.session_state`，刷新即失效；重新上传同一文件会重新摘要/向量化。

## 4. 检索质量实测记录

> 探针脚本未提交到仓库（在本地以临时脚本运行），数据采集环境同上。以下数值来自 2026-11-07 的本地运行，并在 2026-11-08 审计时与代码逻辑复核一致。

测试数据：中文文档片段（含“快速排序”相关表述），Embedding 模型 `paraphrase-multilingual`。

| 指标 | 结果 |
| --- | --- |
| `keyword_search` 得分（2 片段用例） | `{'0': 0.0, '1': 0.0}`（中文查询完全失配） |
| 归一化后语义分（4 片段用例） | `[1.0, 0.2955, 0.1136, 0.0]` |
| 融合分（均值） | `[0.5, 0.1477, 0.0568, 0.0]` |
| `>= 0.3` 过滤后 | 仅 1 条（期望 `num_chunks=4`） |
| `chromadb.Client()` 持久化 | `is_persistent = False` |
| chunk_size=100 / overlap=500 | 步长 -400，死循环 |

## 5. 运行期报错排查流程

遇到报错时按以下顺序定位：

1. **看 Streamlit 终端日志**：`streamlit run app.py` 所在终端会打印异常堆栈与 Ollama 请求错误。
2. **确认 Ollama**：
   ```bash
   ollama list      # 模型是否已下载
   ollama ps        # 模型是否在运行、是否 OOM
   curl http://localhost:11434/api/tags
   ```
3. **确认模型用途**：对话模型 ≠ Embedding 模型；选错会 400（BUG-09）。
4. **确认参数**：`chunk_overlap < chunk_size`，否则卡死（BUG-04）。
5. **确认知识库状态**：刷新后丢失是已知缺陷（BUG-02），需要重新处理。
6. **提交问题**：附上终端日志、Ollama 版本、复现步骤与使用的模型名，并标注对应 BUG 编号。

## 6. 修复路线与验收

| 阶段 | 内容 | 验收标准 |
| --- | --- | --- |
| v1.1（进行中） | 修复 BUG-01/02/03/04/05/06/09/10/11/12/13 | 中文关键词分支生效；重启后知识库保留；检索条数符合 `num_chunks`；非法参数被拒绝；长文摘要覆盖全文；基础错误提示可用 |
| v1.2 | 评测集 + 消融实验（向量 / BM25 / RRF / rerank） | 10–30 条中文问答评测，记录 Recall@k、NDCG、答案正确率对比表 |
| v2.0 | 模块拆分 + 引用溯源 + CI + 文档 | `pytest` 覆盖核心逻辑；GitHub Actions 通过；README/DESIGN 与代码一致 |

## 7. 变更记录

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-11-08 | v1.0 | 首次审计：重写 README，新增本报告，记录 BUG-01 ~ BUG-20 |
