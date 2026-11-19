# My Fortune 第一版推荐规则

规则版本 `daily-theme-v2`，提示词版本 `fortune-v3`。

此版本是可执行的娱乐内容方法，分数和映射由本项目定义。它采用明确的干支关系及五行主题，不执行完整旺衰、格局、调候或喜用神推断。出生资料相同可以得到相同推荐；不追求人与人之间绝对唯一。

## 计算依据

Python 实现参照 taibu-core 4.1.0 的公农历、节气、时区、四柱、十神、藏干、黄历与干支关系口径，使用 lunar-python 与 Python astronomy-engine。日运查询固定以澳门日期计算。关系工具同时返回大运、流年、流月、流日及与原局的关系。上游规则全文位于 `vendor/taibu-core/ALGORITHM_RULES.md`。

出生时间使用出生地时区，日期输入当前为公历。出生日期、性别、出生时区齐全时计算命盘；未知小时只排三柱。资料不齐标记 general，提供一般当日主题。交节等上游无法确定的边界会失败并留待补资料，不悄悄伪造命盘。

## 日运主题与 Qwen 的职责

天干五行按甲乙木、丙丁火、戊己土、庚辛金、壬癸水。

- 当日日干五行加 2 分。
- 有个人日主时，其五行加 2 分，生扶它的上一五行加 1 分。
- 得分大于零的五行成为候选，分数提供给 Qwen 参考。
- Qwen 综合真实命盘、黄历、关系、偏好，在这些候选内选一个主题五行，返回 theme 和 basis。
- 输出超出候选或格式错误则本次生成失败；不会用随机值补齐。

这套分数用于构造主题候选，不代表日主强弱或喜用神。Qwen 每位客人调用三次，日运、物品及餐厅各一次，五项推荐共享同一主题。temperature=0 有助于稳定；最终结果以数据库中首次成功保存的记录为准。

## 今日生肖

候选为十二生肖。分别与当日地支、出生年支、出生日支比较，六合 +3、同属三合组且不同支 +2、六冲 -4、其他 0。同支本身不加分。

当日地支的权重为 2，出生年支和日支各为 1。排除与当日地支六冲的候选，取总分最高者。并列时按日期序数轮换，规则只提供娱乐意义的“今日相合生肖”。当前没有生肖到 Lucky 6 等具体玩法的映射。

## 今日数字

主题五行对应两枚数字，按日期序数奇偶轮换。

| 五行 | 数字 |
| --- | --- |
| 水 | 1、6 |
| 火 | 2、7 |
| 木 | 3、8 |
| 金 | 4、9 |
| 土 | 5、0 |

数字 0 是本产品对土主题数字 10 的单数字化配置。

## 今日颜色

| 五行 | 颜色 |
| --- | --- |
| 木 | Green、Jade |
| 火 | Red、Purple |
| 土 | Yellow、Brown |
| 金 | Gold、White |
| 水 | Blue、Black |

根据选定五行取得两个主题色，再按日期序数轮换。颜色只依赖日运五行和目标日期。色值在 lucky_color.py 中固定。旧数据中的 preferred_colors 会在构造模型输入时移除。

## 今日物品与餐厅

先由 SQL 取 active=true 的目录。目录 metadata 约定如下，标签应由运营维护，拼写一致。

```json
{
  "elements": ["metal"],
  "colors": ["gold"],
  "materials": ["gold"],
  "category": "jewelry"
}
```

餐厅可以使用以下标签。elements 属于运营主题标签。

```json
{
  "elements": ["fire"],
  "colors": ["red"],
  "cuisine": "sichuan",
  "allergens": ["peanut"],
  "dietary_options": ["vegetarian"]
}
```

先排除 excluded_catalog_ids。物品再排除 excluded_materials；餐厅排除 excluded_cuisines，检查 allergens 和 dietary_requirements。客人声明过敏时，缺少 allergens 标签的餐厅不能入选，已知过敏原相交也不能入选。餐厅 dietary_options 必须覆盖客人全部饮食要求。这些判断依赖目录数据的真实性，代表目录层面的匹配。

剩余候选按主题五行匹配 +5、当日颜色匹配 +2、个人偏好品类或菜系匹配 +3 排序。排序后取前 20 个合格候选交给 Qwen。模型结合个人日运、偏好和候选的标签选择一个 ID，并返回理由，选择可以与分数第一名不同。程序校验 ID 属于实际提供的候选，选择理由保存在 audit_json.catalog_decisions。主题匹配为零仍可推荐符合限制的其他候选。没有合格候选时整份 Fortune 失败，其他已发布记录保留。

支持的 preferences 字段均为字符串数组。标签采用小写英文。

```json
{
  "preferred_item_categories": ["jewelry"],
  "excluded_materials": ["nickel"],
  "preferred_cuisines": ["sichuan"],
  "excluded_cuisines": [],
  "allergens": ["peanut"],
  "dietary_requirements": ["vegetarian"],
  "excluded_catalog_ids": []
}
```

## 发布与复现

五项全部成功才写入 my_fortunes。审计字段保存实际排盘、日运、主题候选与规则版本。历史结果缺少 rules_version、personalization 时兼容读取。已有成功结果默认不会因为重跑或规则升级而覆盖。


固定 SQL 测试结果仍使用生成时的确定性排名，标记 fixture-no-llm。运行 app.seed --with-llm 或 app.precalculate 才走当前真实模型生成流程。
