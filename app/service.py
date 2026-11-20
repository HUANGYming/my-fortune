import asyncio
from datetime import date, datetime, timezone
from app.config import Settings
from app.llm import QwenClient
from app.models import Fortune, Patron
from app.repository import Repository
from app.taibu import TaibuClient
from app.rules import RULES_VERSION, daily_element_decision
from app.recommendations import lucky_zodiac, lucky_number, lucky_color, lucky_item, lucky_dining


class FortuneService:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self.llm = QwenClient(settings)
        self.taibu = TaibuClient(settings)

    async def generate(self, patron: Patron, target_date: date) -> Fortune:
        # 第 1 步：查询该客人、该日期的已发布结果。存在时直接复用，支持批任务安全重跑。
        existing = await asyncio.to_thread(self.repository.get_fortune, patron.patron_id, target_date)
        if existing:
            return existing

        # 第 2 步：读取有效物品和餐厅目录。两类目录都需要有候选才能生成完整推荐。
        item_catalog = await asyncio.to_thread(self.repository.catalog, "item")
        dining_catalog = await asyncio.to_thread(self.repository.catalog, "dining")
        if not item_catalog or not dining_catalog:
            raise ValueError("Both item and dining catalogs require active entries")

        # 第 3 步：执行 Python 命理计算，取得个人命盘、当天黄历及岁运干支关系。
        # 当前每次重新排盘，出生资料不足时返回标记为 general 的一般黄历上下文。
        facts = await self.taibu.context(patron, target_date)

        # 第 4 步：组装供各模块共享的 context，包括目标日期、出生资料和计算事实。
        # Patron ID 仅用于关联存储，模型输入只包含出生资料。
        profile = patron.model_dump(mode="json", exclude={"patron_id"})
        context = {"date": target_date.isoformat(), "profile": profile, "facts": facts}

        # 第 5 步：识别当天日干与个人日主的五行关系，执行固定生扶策略。
        # 生我、我生、克我 -> 生我五行；同我、我克 -> 日主五行。
        # 无日主时使用当天五行。决策含输入、关系和理由，供 Qwen 及审计使用。
        context["element_decision"] = daily_element_decision(facts)

        # 第 6 步：取规则确定的五行，不再加分、抽选或按日期打破平分。
        # daily_reading 只保留 element，数字、颜色及目录五行筛选共用该结果。
        element = context["element_decision"]["element"]
        context["daily_reading"] = {"element": element}

        # 第 7 步：个人四支六合生肖作为候选，避开当天六冲，优先当天六合或同组三合。
        # 候选全部被排除时扩展个人三合伙伴；并列按日期轮换，无个人地支时用当天六合。
        # 生肖模块将输入、候选、排除和理由存入 context.zodiac_decision，供 Qwen 及审计使用。
        # 数字和颜色沿用日运五行及日期规则；幸运生肖、颜色供后续目录优先排序使用。
        zodiac = lucky_zodiac.generate(context)
        number = lucky_number.generate(context)
        color = lucky_color.generate(context)
        context["lucky_color"] = color.model_dump()
        context["lucky_zodiac"] = zodiac.value

        # 第 8 步：物品、餐厅强制筛选五行匹配的有效目录；生肖匹配优先，其次颜色匹配。
        # 各取前 20 个交给 Qwen 选择真实 ID，不匹配五行的条目不会进入模型候选。
        # 没有匹配目录则本次失败，不跨五行兜底或伪造商品、餐厅。
        # 独立上下文保存各自的选择理由；共享 QwenClient 将在途请求总数限制为 16。
        item_context = {**context, "catalog_decisions": {}}
        dining_context = {**context, "catalog_decisions": {}}
        async with asyncio.TaskGroup() as tasks:
            item_task = tasks.create_task(lucky_item.generate(self.llm, item_context, item_catalog))
            dining_task = tasks.create_task(lucky_dining.generate(self.llm, dining_context, dining_catalog))
        item = item_task.result()
        dining = dining_task.result()
        context["catalog_decisions"] = {
            **item_context["catalog_decisions"], **dining_context["catalog_decisions"],
        }

        # 第 9 步：五项全部成功后组装 Fortune，保存展示结果、版本及计算审计依据。
        # Repository.save 在一个数据库事务内发布，前面任何一步失败都不会写入部分结果。
        fortune = Fortune(
            patron_id=patron.patron_id, fortune_date=target_date,
            lucky_zodiac=zodiac, lucky_number=number, lucky_color=color,
            lucky_item=item, lucky_dining=dining, generated_at=datetime.now(timezone.utc),
            model=self.settings.qwen_model, prompt_version=self.settings.prompt_version,
            rules_version=RULES_VERSION, personalization=facts["personalization"],
        )
        await asyncio.to_thread(self.repository.save, fortune, {"facts": facts, "reading": {"element": element}, "rules_version": RULES_VERSION,
                                     "element_decision": context["element_decision"],
                                     "zodiac_decision": context["zodiac_decision"],
                                     "catalog_decisions": context["catalog_decisions"]})

        # 第 10 步：重新读取数据库中的最终结果并返回。
        # 并发任务可能已先完成发布，因此以数据库实际保存的那一份为准。
        saved = await asyncio.to_thread(self.repository.get_fortune, patron.patron_id, target_date)
        if saved is None:
            raise RuntimeError("Published fortune could not be read")
        return saved
