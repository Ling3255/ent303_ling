# CiteCheck

帮研究生在交综述、开组会、写开题之前，逐句核对 AI 或自己写的文字是否被所引论文支持，以及文中比较的结果是否在相同条件下测得。

第一版是网页：贴一段文字（≤ 1,500 字），附上最多 5 篇论文（PDF / DOI / arXiv 编号），得到逐句的三层检查报告：

| 层次 | 检查什么 | 结果标签 |
| --- | --- | --- |
| ① 来源 | 论文是否存在、是否正式发表 | 存在 / 预印本 / 找不到 |
| ② 支持 | 说法和数字原文里有没有 | 原文支持 / 原文没有 / 说法相反 / 数字不一致 |
| ③ 可比 | 被比较的两个结果测试条件是否一致 | 条件一致 / 有差异但通常不影响 / 有差异且可能影响结论 |

每个结果都附原文段落和页码，可以跳到 PDF 对应页并高亮。系统只提示差异，从不宣称两个结果可以放心比较。

## 快速开始

### 方式一：Docker（服务器部署用）

```bash
cp .env.example .env        # 填 LLM_API_KEY（DeepSeek）和 CONTACT_EMAIL
docker compose up -d --build
# 打开 http://localhost:8080
```

会启动 4 个服务：PostgreSQL、GROBID（PDF 解析，至少 4 GB 内存）、FastAPI 后端、Nginx + 前端。

### 方式二：本地开发

后端（Python 3.11）：

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://localhost:8000/docs 是接口文档
```

前端（Node 20+）：

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173，/api 自动转发到 8000
```

不配置任何外部服务也能跑通：没有 `LLM_API_KEY` 时用规则模式，没有 GROBID 时用 pypdf 简易解析，数据库默认 SQLite。
想要更好的 PDF 解析，可以单独起一个 GROBID：`docker run -p 8070:8070 lfoppiano/grobid:0.8.1`，然后设置 `GROBID_URL=http://localhost:8070`。

## 目录结构

```
backend/
  app/
    main.py              接口（/api/split、/api/papers、/api/checks …）
    services.py          论文入库（后台线程）、上传文件 7 天清理
    llm.py               大模型封装（OpenAI 兼容，DeepSeek / 通义千问只改环境变量）
    db.py                数据表：papers、condition_cache、checks、feedback
    pipeline/
      papers.py          第 1 步 读取论文：找开放全文，GROBID / pypdf 解析成带页码的段落
      sources.py         第 2 步 核对来源：Crossref、OpenAlex、arXiv、DBLP
      sentences.py       第 3 步 拆句、标出含数字 / 比较 / 引用的句子
      claims.py          第 3 步 识别论断并对应到论文（大模型，规则兜底）
      retrieval.py       第 4 步 查找段落：bge-m3 或 BM25 + 数字精确匹配
      support.py         第 5 步 判断支持并抽取五个条件字段；evidence.py 核对原句是否真实存在
      comparability.py   第 6 步 按规则文件判断可比
      runner.py          把 7 步串起来、生成报告、条件缓存
    rules/
      comparability.yaml 可比规则（不写代码也能改，重启后端生效）
      benchmarks.yaml    三个方向的数据集 / 划分 / 指标词表
  tests/                 自动测试（含 Whisper 例子端到端）
  eval/                  实验 2、3 的回归评测脚本和样例数据
frontend/
  src/pages/NewCheck.jsx     上传页：贴文字 → 加论文 → 确认句子
  src/pages/Report.jsx       报告页：进度、逐句颜色、三层结果
  src/components/PdfViewer.jsx  PDF.js 预览，跳页并高亮原文
  src/pages/PrintReport.jsx  一页证据单（浏览器打印存为 PDF）
```

## 怎么改规则（给研究组）

- **可比规则**：`backend/app/rules/comparability.yaml`。`fields` 定义五个字段不一致时的默认等级；`markers` 定义“落在次要字段里、却会改变结论”的关键差异，例如零样本 vs 微调、有无语言模型、单裁剪 vs 多裁剪、oracle 段落 vs 检索段落。每条规则写明关键词和理由，理由会原样显示在报告里。
- **词表**：`backend/app/rules/benchmarks.yaml`。新增数据集、划分、指标的写法，系统就会把它们当成同一个东西（例如 `ILSVRC-2012` = `ImageNet-1k`）。
- 改完运行 `cd backend && pytest -q`，确认没有把已有例子改坏。

## 测试与评测

```bash
cd backend
pytest -q                                                   # 单元测试 + Whisper 端到端
python -m eval.run_eval extraction eval/data/extraction_sample.jsonl --papers eval/data/papers   # 实验 2
python -m eval.run_eval sources eval/data/sources_sample.jsonl                                   # 实验 3（需联网）
```

`eval/run_eval.py` 开头写了标注文件格式。把 30 条人工标注放进 `eval/data/extraction.jsonl` 后，CI 里同样的命令会在字段正确率 < 85% 或编造率 ≥ 5% 时失败。

## 已实现 / 未实现

已实现（P0 全部 + 部分 P1）：文字输入与拆句、PDF / DOI / arXiv 论文输入、①②③ 三层检查、报告页、跳转 PDF 并高亮、导出证据单、“不同意”反馈入库、条件缓存、上传文件 7 天自动删除。

还没做：学生账号与每月次数上限（P1）、浏览器插件和 Zotero 插件（P2）。

已知限制：
- 规则模式（不配大模型）只能核对含数字的论断，条件抽取较粗，仅用于开发和演示。
- 没有 GROBID 时用 pypdf 解析，表格会被压成一行文字，无法按段落坐标高亮（会退回按文字匹配高亮）。
- ICML、NeurIPS 等没有 DOI 的会议论文依赖 DBLP 判断是否正式发表；DBLP 访问失败时会显示为“预印本”。

## 合规

- 用户上传的 PDF 只用于当次检查，`UPLOAD_RETENTION_DAYS`（默认 7）天后自动删除，同时删除解析出的全文；缓存只保留抽取出的条件和短句引文。
- 只调用已备案的国产大模型（默认 DeepSeek）。
- 报告始终注明“系统只提示差异，请核对原文”。
