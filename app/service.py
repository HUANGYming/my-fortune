from datetime import date, datetime, timezone
from app.config import Settings
from app.llm import QwenClient
from app.models import Fortune, Patron
from app.repository import Repository
from app.taibu import TaibuClient
from app.rules import RULES_VERSION, theme_candidates, select_daily_element
from app.recommendations import lucky_zodiac, lucky_number, lucky_color, lucky_item, lucky_dining


class FortuneService:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self.llm = QwenClient(settings)
        self.taibu = TaibuClient(settings)

    async def generate(self, patron: Patron, target_date: date) -> Fortune:
        # 第 1 步：查询该客人、该日期的已发布结果。存在时直接复用，支持批任务安全重跑。
        existing = self.repository.get_fortune(patron.patron_id, target_date)
        if existing:
            return existing

        # 第 2 步：读取有效物品和餐厅目录。两类目录都需要有候选才能生成完整推荐。
        item_catalog = self.repository.catalog("item")
        dining_catalog = self.repository.catalog("dining")
        if not item_catalog or not dining_catalog:
            raise ValueError("Both item and dining catalogs require active entries")

        # 第 3 步：执行 Python 命理计算，取得个人命盘、当天黄历及岁运干支关系。
        # 当前每次重新排盘，出生资料不足时返回标记为 general 的一般黄历上下文。
        facts = await self.taibu.context(patron, target_date)

        # 第 4 步：组装供各模块共享的 context，包括目标日期、出生资料和计算事实。
        # Patron ID 仅用于关联存储，模型输入只包含出生资料。
        profile = patron.model_dump(mode="json", exclude={"patron_id"})
        context = {"date": target_date.isoformat(), "profile": profile, "facts": facts}

        # 第 5 步：按日干五行 +2、日主五行 +2、生扶日主的五行 +1 计算候选得分。
        # 评分和后续选择均使用固定规则。
        context["theme_candidates"] = theme_candidates(facts)

        # 第 6 步：选择得分最高的五行；平分时按目标日期轮换。
        # daily_reading 只保留 element，数字、颜色及目录评分共用该结果。
        element = select_daily_element(context["theme_candidates"], target_date)
        context["daily_reading"] = {"element": element}

        # 第 7 步：按地支关系选择生肖，按日运五行与日期选择数字及颜色。
        # 将幸运色加入 context，供后续物品和餐厅的目录评分使用。
        zodiac = lucky_zodiac.generate(context)
        number = lucky_number.generate(context)
        color = lucky_color.generate(context)
        context["lucky_color"] = color.model_dump()

        # 第 8 步：物品与餐厅模块分别将评分后的前 20 个候选交给 Qwen 选择。
        # 各模块校验返回的目录 ID 并记录理由；餐厅还会收到已选择的物品。
        item = await lucky_item.generate(self.llm, context, item_catalog)
        context["selected_item"] = item.model_dump()
        dining = await lucky_dining.generate(self.llm, context, dining_catalog)

        # 第 9 步：五项全部成功后组装 Fortune，保存展示结果、版本及计算审计依据。
        # Repository.save 在一个数据库事务内发布，前面任何一步失败都不会写入部分结果。
        fortune = Fortune(
            patron_id=patron.patron_id, fortune_date=target_date,
            lucky_zodiac=zodiac, lucky_number=number, lucky_color=color,
            lucky_item=item, lucky_dining=dining, generated_at=datetime.now(timezone.utc),
            model=self.settings.qwen_model, prompt_version=self.settings.prompt_version,
            rules_version=RULES_VERSION, personalization=facts["personalization"],
        )
        self.repository.save(fortune, {"facts": facts, "reading": {"element": element}, "rules_version": RULES_VERSION,
                                     "theme_candidates": context["theme_candidates"],
                                     "catalog_decisions": context["catalog_decisions"]})

        # 第 10 步：重新读取数据库中的最终结果并返回。
        # 并发任务可能已先完成发布，因此以数据库实际保存的那一份为准。
        saved = self.repository.get_fortune(patron.patron_id, target_date)
        if saved is None:
            raise RuntimeError("Published fortune could not be read")
        return saved
