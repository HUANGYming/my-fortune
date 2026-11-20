# My Fortune

完整目录职责、算法输入输出、调用链及当前版本示例见 [目录结构与算法开发说明](docs/PROJECT_STRUCTURE_AND_ALGORITHMS.md)。团队接手与下一步实施顺序见 [On-premise agent 接手说明](docs/HANDOFF.md)。五项推荐流程见 [英文演示文稿](docs/presentations/My_Fortune_Developer_Ten_Colors_v7.pptx)。

Python + FastAPI 后端，澳门日期驱动预计算，五项完整生成后持久化至 Yellowbrick，REST API 查询已有结果。

## 项目模块

| 位置 | 职责 |
| --- | --- |
| app/main.py | REST 查询与 OpenAPI |
| app/precalculate.py | 全表每日预计算入口，支持指定日期 |
| app/service.py | 排盘、规则五行、五项推荐、发布 |
| app/recommendations/ | 生肖、数字、颜色、物品、餐厅五个独立文件 |
| app/rules.py | 生扶五行决策、干支关系常量、目录五行硬筛选及生肖/颜色优先排序 |
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

payload 保存五项展示内容、模型/提示词/规则版本和 personalization（general、three_pillars、four_pillars）。audit_json 保存原始计算结果、日运依据和生肖候选决策。使用 VARCHAR 保存 JSON，避免依赖 JSONB 或 ON CONFLICT。

发布事务使用 EXCLUSIVE 表锁，检查并插入，所有写入方须走同一路径。目标 Yellowbrick 的锁语法、权限和并发行为尚需真实版本联调，仓库未声称已验证该部分。模型调用在事务外执行。

## REST API

- GET /health/live 返回进程存活状态。
- GET /v1/patrons/{patron_id}/fortunes/today 按澳门日期读取。
- GET /v1/patrons/{patron_id}/fortunes/{fortune_date} 读取指定日期。

查询不触发计算，尚未生成返回 404，数据库故障返回 503。业务接口采用 X-API-Key，供可信内部服务调用。客户网关需按登录身份授权 Patron 范围。生成入口为 CLI，当前没有后台 HTTP 任务接口。

## Qwen 接入

app/llm.py 调用 /v1/chat/completions，每人两次调用，分别选择物品和餐厅。日运五行由 rules.py 的 daily_element_decision 按固定生扶表确定，日运数据只保留 element。输入五行、关系及选择理由作为 element_decision 传给 Qwen 并存入审计。程序只保留五行匹配的有效物品和餐厅，按生肖匹配优先、颜色匹配其次、ID 排序，各取前 20 个交给 Qwen。生肖标签可选，不匹配也不因此排除；模型可以选择入选池中任意一个。没有五行候选时失败，不跨五行兜底。返回 ID 再次校验，理由、候选 ID 和命中标签保存在 audit_json.catalog_decisions。JSON 由 Pydantic 校验，超时和临时错误有限重试，非法结果使本次任务失败。默认提示词版本为 fortune-v6，已有环境若覆盖 PROMPT_VERSION 需同步更新。Qwen 的 chat template / reasoning parser 需确保 content 返回纯 JSON。没有配置外部模型回退。

## 测试与接入状态

```sh
uv run --locked pytest -q
```

测试覆盖实际太卜的四柱、三柱和一般黄历计算，规则筛选，以及采用模型/数据库替身的生成、发布和查询流程。20 组上游快照用于验证迁移一致性，测试无需安装 Node。

实际 Qwen 和 Yellowbrick 连接由项目维护者自行完成和替换，业务接口约定见目录结构与算法开发说明。规则属于第一版娱乐内容配置，正式命理方法及运营目录由团队继续完善。

上游版本及许可见 vendor/UPSTREAM.md。参考 [Yellowbrick Python 连接](https://docs.yellowbrick.com/7.4.4/tutorial/connecting_with_Python.html)、[vLLM 接口](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/)。

## 测试数据

`sql/003_test_data.sql` 包含 6 位虚构 Patron、10 件物品、10 家虚构餐厅（其中 1 家停用），以及 2026-11-19、2026-11-20 两天共 10 份完整推荐。有效目录对每种五行、每种 kind 都提供至少两个候选，包含多五行标签、可选生肖标签和没有生肖标签的场景。生肖标签是演示产品配置，不是传统命理结论。

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

预存结果使用真实太卜排盘及生成时的 v5 规则，日运主题选择最高分候选。它们未调用 Qwen，结果标记 model=fixture-no-llm，审计字段 demo=true。这批历史数据用于 API 展示及规则测试，不代表当前 v8 结果；真实模型联调可使用 DEMO-P006，或指定尚未预存的日期。

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

当前幸运色固定为 Red、Blue、Purple、Green、Yellow、Gold、Silver、Orange、Brown、Pink。五行分组及日期轮换见 docs/RULES.md。历史成功记录保留原结果，新生成记录使用 daily-theme-v8。生扶表沿用 v6：丙火日主遇当天木、火、土、金、水，分别推荐木、火、木、火、木；没有个人日主时使用当天五行。

v7 生肖以个人年、月、日、时支的六合生肖为候选，合并去重，排除当天六冲；候选全部被排除时扩展个人三合组伙伴。与当天六合或同属三合组的候选同等优先，并列或没有当天相合关系时按日期轮换。未知时支跳过；没有个人地支时使用当天六合。选择依据作为 zodiac_decision 传给 Qwen 并持久化到审计。生肖仍完全由规则生成，每位客人仍只有两次 Qwen 调用，REST 响应格式不变。既有演示文稿保留旧版评分示例，当前规则以 docs/RULES.md 为准。

v8 物品、餐厅复用 fortune_catalog.metadata_json 的 elements 数组，并新增可选 zodiacs 数组，例如 `{"elements":["metal"],"zodiacs":["Tiger","Horse"],"category":"jewelry"}`。不新增数据库列。现有实际目录在启用 v8 前须补齐 elements，否则该条目不会入选；zodiacs 可以不填。SQL 按 kind、active 取数，Python 解析 JSON 后筛选，不依赖 Yellowbrick JSON 函数。完整标签约定及示例见 docs/RULES.md。
