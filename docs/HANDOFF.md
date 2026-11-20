# On-premise agent 接手说明

## 目标与已确认设计

My Fortune 为 Patron 按澳门日期预计算五项个人推荐，并持久化至 Yellowbrick。前端 REST 请求读取已发布记录。后端使用 Python + FastAPI，Qwen 由内网 vLLM 提供。五项推荐保持五个独立文件，方便团队并行完善。

当前规则版本 daily-theme-v8，提示词默认版本 fortune-v6。个人日运五行保留 v6 固定生扶表，仅保存 element；输入、关系及理由另存 audit_json.element_decision 并传给 Qwen。丙火日主遇当天木、火、土、金、水，分别推荐木、火、木、火、木。没有个人日主时使用当天五行。未实现随机生扶 / 制约切换，制约分支待讨论。Qwen 分别选择物品和餐厅，每人共两次调用。物品及餐厅先经过程序过滤，模型从最多 20 个合格候选中选择，选择理由存入 audit_json.catalog_decisions。

v7 生肖以个人四支的六合生肖为基础候选；排除当天六冲，优先与当天六合或同属三合组的候选，两种关系同等优先。候选全部被排除时扩展个人三合伙伴；并列或无当天相合候选时按日期稳定轮换。未知时支跳过，无个人命盘时使用当天六合。个人其他柱的六冲不作为硬排除，不评分。候选来源及完整选择过程存入 audit_json.zodiac_decision，并传给 Qwen。REST 响应和表结构不变，历史成功结果不自动重算。

v8 在 fortune_catalog.metadata_json 内使用 elements 和可选 zodiacs 数组，无需新增列。SQL 只取对应 kind、active=true 目录，Python 强制筛选五行匹配条目，按生肖匹配、颜色匹配、ID 顺序排列，各取前 20 个交给 Qwen。无生肖标签也可入选，生肖优先不是硬筛选；没有五行候选时失败，不跨五行兜底。模型输入含逐项 rule_matches，审计保存候选 ID、选中条目的命中标签和模型理由。当前目录格式校验不改变旧版 payload 的兼容读取。

## 当前完成情况

- 计算模块已迁移为 Python，参照 taibu-core 4.1.0 / 4b2a51a 的规则，许可证及算法口径已保留。
- app/calculations 在进程内计算本命盘、黄历及岁运关系，使用 lunar-python 和 Python astronomy-engine。
- 提供预计算 CLI、Yellowbrick 访问层、事务发布、REST 查询和 OpenAPI。
- 提供 6 位虚构 Patron、20 项目录及两天 10 份预存结果。每种五行的有效物品、餐厅候选至少各两个。
- 提供 --with-llm 测试数据入口。没有在仓库保存真实凭据、Patron 或餐厅记录。
- 当前 107 项本地测试通过，覆盖真实太卜计算、生扶规则、个人四支生肖算法、目录五行硬筛选/生肖及颜色优先/非法标签/候选上限/模型 ID 校验，以及使用 Qwen 和数据库替身的完整生成链路。

真实 Yellowbrick 和 Qwen 地址尚未提供，未做生产环境联调或部署。My Fortune 当前实现业务需要的八字、黄历及干支关系，范围见 docs/PYTHON_MIGRATION.md。

## 第一阶段 · 跑通内网链路

1. 阅读 README.md、docs/RULES.md、docs/PYTHON_MIGRATION.md 和 .env.example，准备 uv 和 Python 3.12，使用 `uv sync --locked` 按 uv.lock 安装依赖。内网环境可预先准备对应平台的 Python、uv 缓存或 wheel 包。运行时使用 Python 计算。
2. 创建本地 .env，配置 DATABASE_DSN、API_KEY、QWEN_BASE_URL、QWEN_MODEL 和需要的 QWEN_API_KEY。QWEN_BASE_URL 包含 /v1，客户端会追加 /chat/completions。数据库连接使用实际 TLS 参数。
3. 确认 Yellowbrick 版本。核对 sql/001_schema.sql 的类型、长度及 schema，再在测试环境应用。已有旧版表的环境使用 002 增量脚本，勿再次执行 001。确认 repository.py 的 LOCK TABLE ... IN EXCLUSIVE MODE 在该版本有效，执行两个并发写入和回滚测试。若不支持，依据实际数据库能力替换发布并发控制。
4. 将 fortune_patron_source 映射到现有 Patron 数据。确认生日为公历，以及出生时区、小时、分钟、性别字段含义。缺出生时区会得到 general；时辰未知时保留三柱。不要把所有人的出生时区设为澳门。
5. 配置 Qwen chat template 与 reasoning parser，验证返回的 message.content 为符合 schema 的 JSON。已有环境若覆盖 PROMPT_VERSION，更新为 fortune-v6。先用单一 Patron 检查两次模型调用、候选 ID 校验与数据库写入。若模型会输出 Markdown 代码围栏或额外解释，在模型调用层适配结构化输出，并添加对应回归测试。
6. 用以下命令导入输入并通过真实模型生成，选用尚未保存的日期。

```sh
uv run --locked python -m app.seed --with-llm --date 2026-11-21
```

如之前已导入固定测试结果，可以仅用未预计算的客人测试真实生成。

```sh
uv run --locked python -m app.precalculate --date 2026-11-20
```

固定 SQL 结果 model=fixture-no-llm，不能当作真实 Qwen 测试证明。重复执行会复用已有结果，选择新的日期可再次触发模型。

第一阶段验收应有一位客人的真实太卜结果、两次真实 Qwen 调用、完整数据库记录及 REST 响应。重跑时结果相同、没有重复行。模型失败时没有部分 Fortune，已有成功记录保留。全表分页、失败后继续和非法目录 ID 测试均通过。

## 第二阶段 · 数据与规则完善

- 用实际可推荐的物品和餐厅替换虚构目录。启用 v8 前为有效目录补齐 elements 数组，确保五种五行的物品及餐厅都有候选；缺失或空数组将被排除。zodiacs 可选，按 Zodiac 英文枚举拼写。核实 colors、materials、category、cuisine 等标签质量及 active 状态。标签为产品配置，不自动从材质、菜系推断五行。
- 当前版本使用出生资料、日运与目录标签。目录标签拼写需一致，并继续验证实际模型的推荐理由。
- 五个模块负责人分别检查个人六合生肖筛选、数字映射、色表、物品提示词、餐厅提示词。当前固定生扶表及生肖优先条件是产品方法，不是完整命理取用算法。用测试客群检查推荐分布，不宣称均匀或绝对唯一。规则变更记录版本，历史成功记录默认保留。SQL 固定样例和既有 PPT 保留旧版评分口径，当前规则以 docs/RULES.md 为准。
- 如需 Featured Game，另定义真实玩法目录及运营关联。当前代码没有生肖到 Lucky 6 的映射。
- 确认前端是否需要名称本地化、图片、餐厅地址和跳转信息。现有 CatalogEntry.metadata 可以承载数据，确定正式 API 字段后补入模型与 OpenAPI。

## 第三阶段 · 批量任务与服务运行

- 当前 CLI 默认按澳门当天日期对 fortune_patron_source 全表计算，以 Patron ID 分页读取，每页默认 500 位，以 16 个工作任务并发处理。继续完善持久化任务状态、失败明细和监控。个人命盘维持每次计算的实现。
- 按澳门日期提前生成次日结果，接入团队调度器。明确截止时间、数据更新策略和失败告警。
- 测量两次模型调用的吞吐、延迟及上下文长度，当前单个批任务的请求并发上限固定为 16。内网验证实际 GPU 吞吐、超时重试及 Yellowbrick 锁竞争。多个批处理进程的限流由部署侧协调。
- 查询接口目前使用内部 X-API-Key，可访问任意 Patron。对接网关身份认证与客人范围授权，补 readiness、请求追踪和团队日志规范。
- 当前表结构使用 VARCHAR(64000) 存储结果及审计 JSON。评估真实长命盘、字符编码、字段大小及保留周期。大型 Patron 数据量下评估 Yellowbrick 分布方式、查询速度与发布锁竞争。
- 确定部署方式后再补容器、进程管理和发布配置。当前仓库没有部署流水线。

## 团队文件分工

| 工作 | 主要文件 |
| --- | --- |
| Patron / Yellowbrick | app/repository.py、app/database.py、sql/ |
| 太卜与日期规则 | app/taibu.py、app/calculations/、vendor/UPSTREAM.md |
| 模型连接 | app/llm.py、app/config.py |
| 日运与公共规则 | app/service.py、app/rules.py、docs/RULES.md |
| 五项推荐 | app/recommendations/ 下各自文件 |
| REST 与鉴权 | app/main.py、app/models.py |
| 批处理调度 | app/precalculate.py、app/seed.py |

首次改动前运行 `uv run --locked pytest -q`，后续根据改动执行相关测试和真实内网集成验证。发布前补充实际版本、运行命令与联调结果至本说明。
