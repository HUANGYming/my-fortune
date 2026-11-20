# My Fortune

团队接手与下一步实施顺序见 [On-premise agent 接手说明](docs/HANDOFF.md)。五项推荐流程见 [英文演示文稿](docs/presentations/My_Fortune_Developer_Guide_v5.pptx)。

Python + FastAPI 后端，澳门日期驱动预计算，五项完整生成后持久化至 Yellowbrick，REST API 查询已有结果。

## 项目模块

| 位置 | 职责 |
| --- | --- |
| app/main.py | REST 查询与 OpenAPI |
| app/precalculate.py | 全表每日预计算入口，支持指定日期 |
| app/service.py | 排盘、规则五行、五项推荐、发布 |
| app/recommendations/ | 生肖、数字、颜色、物品、餐厅五个独立文件 |
| app/rules.py | 主题候选、关系评分、目录筛选与排名 |
| app/llm.py | on-premises Qwen / vLLM 客户端 |
| app/taibu.py | Python 计算入口，保留现有调用契约 |
| app/calculations/ | 历法、真太阳时、四柱、黄历、岁运和干支关系的 Python 实现 |
| vendor/ | 上游算法口径、许可证和依赖许可说明 |
| app/repository.py | Yellowbrick 数据映射与结果读写 |
| sql/ | 初始表结构与已有数据库增量脚本 |
| docs/RULES.md | 第一版推荐方法、目录标签 |

## 安装与启动

使用 uv 管理环境和依赖，默认 Python 3.12（`.python-version`），代码兼容 Python 3.11+。运行时全部使用 Python，历法库 lunar-python 1.4.9 和天文库 astronomy-engine 2.1.19 已锁定版本。

```sh
uv sync --locked
cp .env.example .env
# 修改 .env 的 Yellowbrick、Qwen 配置
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`uv sync --locked` 使用已提交的 `uv.lock`，默认安装开发测试依赖。服务环境可使用 `uv sync --locked --no-dev`，并通过 `uv run --locked --no-dev uvicorn app.main:app` 启动。添加依赖使用 `uv add 包名`，添加测试工具使用 `uv add --dev 包名`，提交时同时包含 pyproject.toml 和 uv.lock。锁文件使用规则见 [uv 文档](https://docs.astral.sh/uv/concepts/projects/sync/)。

OpenAPI 文档 `/docs`，规范 `/openapi.json`。Python 在进程内执行计算。旧版 NODE_BINARY 和 TAIBU_BASE_URL 配置已移除。

## 数据库准备

新安装由数据库负责人执行 sql/001_schema.sql。已经使用旧版表结构时只应用 sql/002_birth_coordinates.sql。应用不自动修改数据库。fortune_patron_source 可以替换成现有 Patron 表的映射视图。

新增出生字段 birth_minute、birth_timezone、longitude。其中 birth_timezone 是实际出生时区；不填时提供 general 黄历主题。出生日期当前按公历处理。未知出生小时可得到三柱结果。目录标签见 docs/RULES.md。当前 Patron 只读取出生资料。

fortune_catalog 的 kind 使用 item 或 dining，entry_id 应唯一，active=true 表示可推荐。物品、餐厅目录需要先填入有效数据。

## 预计算

现有企业调度器每天调用 CLI，可提前生成明天的 Fortune。

```sh
uv run --locked python -m app.precalculate --date 2026-11-20
```

从 fortune_patron_source 分页读取全部不同的 Patron ID，默认每页 500 位，可用 --batch-size 调整。省略 --date 时使用澳门当天日期。使用 16 个并发工作任务计算并持久化，同一天已成功结果复用，失败继续处理其他客人。失败返回非零退出码，重跑补算缺失记录。任务状态表、分布式队列尚待扩展。

Python 排盘与黄历计算，规则确定每日五行并生成生肖、数字、颜色，Qwen 选择物品及餐厅，最后完整保存。

payload 保存五项展示内容、模型/提示词/规则版本和 personalization（general、three_pillars、four_pillars）。audit_json 保存原始计算结果与日运依据。使用 VARCHAR 保存 JSON，避免依赖 JSONB 或 ON CONFLICT。

发布事务使用 EXCLUSIVE 表锁，检查并插入，所有写入方须走同一路径。目标 Yellowbrick 的锁语法、权限和并发行为尚需真实版本联调，仓库未声称已验证该部分。模型调用在事务外执行。

## REST API

- GET /health/live 返回进程存活状态。
- GET /v1/patrons/{patron_id}/fortunes/today 按澳门日期读取。
- GET /v1/patrons/{patron_id}/fortunes/{fortune_date} 读取指定日期。

查询不触发计算，尚未生成返回 404，数据库故障返回 503。业务接口采用 X-API-Key，供可信内部服务调用。客户网关需按登录身份授权 Patron 范围。生成入口为 CLI，当前没有后台 HTTP 任务接口。

## Qwen 接入

app/llm.py 调用 /v1/chat/completions，每人两次调用，分别选择物品和餐厅。日运五行由 rules.py 按固定分数选出，日运数据只保留 element。物品和餐厅先由程序筛选，再把排名前 20 个合格候选交给 Qwen，模型可以综合日运与目录标签选择其中任意一个。输出 ID 再次校验，理由保存在 audit_json.catalog_decisions。JSON 由 Pydantic 校验，超时和临时错误有限重试，非法结果使本次任务失败。Qwen 的 chat template / reasoning parser 需确保 content 返回纯 JSON。没有配置外部模型回退。

## 测试与接入状态

```sh
uv run --locked pytest -q
```

测试覆盖实际太卜的四柱、三柱和一般黄历计算，规则筛选，以及采用模型/数据库替身的生成、发布和查询流程。20 组上游快照用于验证迁移一致性，测试无需安装 Node。

真实 Qwen 和 Yellowbrick 尚未提供地址凭据，需联调。规则属于第一版娱乐内容配置，正式命理方法及运营目录由团队继续完善。

上游版本及许可见 vendor/UPSTREAM.md。参考 [Yellowbrick Python 连接](https://docs.yellowbrick.com/7.4.4/tutorial/connecting_with_Python.html)、[vLLM 接口](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/)。

## 测试数据

`sql/003_test_data.sql` 包含 6 位虚构 Patron、6 件物品、6 家虚构餐厅（其中 1 家停用），以及 2026-11-19、2026-11-20 两天共 10 份完整推荐。

| Patron | 测试场景 |
| --- | --- |
| DEMO-P001 | 完整出生资料、澳门经度校正 |
| DEMO-P002 | 完整香港出生资料 |
| DEMO-P003 | 出生时辰未知 |
| DEMO-P004 | 出生时区缺失，使用 general 黄历主题 |
| DEMO-P005 | 出生资料缺失 |
| DEMO-P006 | 伦敦出生时区，特意未预存结果，用于测试 404 和补生成 |

先建立或升级表结构，再通过数据库客户端执行该 SQL，或填写 `.env` 后运行以下命令。

```sh
uv run --locked python -m app.seed
```

SQL 在一个事务内导入。重复运行会替换脚本中明确列出的 DEMO 数据及两天结果，其他 ID 和其他日期的结果保留。建议在团队测试库使用。

预存结果使用真实太卜排盘及现有五项规则。日运主题选择最高分候选，未调用 Qwen，结果标记 model=fixture-no-llm，审计字段 demo=true。这批数据用于 API 展示及规则测试；真实模型联调可使用 DEMO-P006，或指定尚未预存的日期。

例如查询 `GET /v1/patrons/DEMO-P001/fortunes/2026-11-19`，或运行以下命令测试真实 Qwen 生成及写回。

```sh
uv run --locked python -m app.precalculate --date 2026-11-20
```

本仓库通过本地 SQLite 检查脚本重复导入、数据关联和模型结构，未据此认定 Yellowbrick 实例已完成导入。


### 使用 Qwen 生成测试推荐

配置 `.env` 中 DATABASE_DSN、QWEN_BASE_URL、QWEN_MODEL，以及部署需要的 QWEN_API_KEY 后，可以载入虚构客人和目录，并通过真实 Qwen 生成推荐。

```sh
uv run --locked python -m app.seed --with-llm --date 2026-11-21
```

省略 --date 时使用澳门当天日期。该模式只导入 Patron 和目录，保留已保存的 Fortune，随后对 fortune_patron_source 全表执行预计算。若之前导入了 19、20 日的固定结果，请选择尚未生成的日期，或执行全表 precalculate，补算尚未保存的客人。真实调用失败会返回非零退出码，并允许重跑补算。


算法范围和验证方法见 [Python 迁移说明](docs/PYTHON_MIGRATION.md)。SQL 固定样例保留原引擎标记，新计算使用 my-fortune-python 1.0.0。


已有数据库中的 preferences_json 列可以保留，当前代码不再读取。新建测试表和测试 Patron 输入已移除该字段。每天的任务为每位客人创建当天记录，同日期重跑复用已有成功结果。


## 并发执行

每个批处理进程最多同时处理 16 位 Patron，等待队列最多 32 个 ID。批任务共用一个 QwenClient，其请求信号量保证最多 16 个 HTTP 请求在途，重试退避时释放请求名额。同一位客人的物品与餐厅使用独立上下文并发选择，共享一个 QwenClient 请求限流器。数据库同步访问通过后台线程执行，五项结果的发布事务沿用现有实现。

上限 16 按单个批处理进程生效，多个独立进程或其他 vLLM 调用方的请求数量需要部署侧统一协调。--batch-size 控制每页 ID 数量，和并发上限分别控制。当前仍按 ID 读取 Patron，未在这次改动中增加批量资料读取或批量结果写入。
