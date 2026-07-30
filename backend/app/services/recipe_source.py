"""HowToCook（《程序员做饭指南》）菜谱 Markdown 解析器。

HowToCook 仓库把每道菜存成一个 Markdown 文件（路径 dishes/<分类>/<菜名>.md），
包含：
  # 菜名 的做法                       -> 标题（去掉「 的做法」即菜名）
 预估烹饪难度：★★★★                  -> 难度（数星）
 预估卡路里：107 大卡                 -> 卡路里（整道菜）
  ## 必备原料和工具                    -> 原料+工具（含锅/灶，需过滤，且无用量）
  ## 计算                              -> 用量公式（关键结构化来源）
      一份正好够 1 个人食用            -> 单人份提示
      总量：/每份：                    -> 用量列表，形如「黄瓜 200 克 * 份数」「醋 7.5 ml + 4 ml * 份数」
  ## 操作                              -> 有序步骤
  ## 附加内容                          -> 备注/参考

本模块只做纯解析，不依赖数据库，便于单测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# HowToCook 分类目录 -> (meal-planner 分类, 适用餐次)
CATEGORY_MAP = {
    "vegetable_dish": ("副菜", ["lunch", "dinner"]),
    "meat_dish": ("主菜", ["lunch", "dinner"]),
    "aquatic": ("主菜", ["lunch", "dinner"]),
    "soup": ("汤", ["lunch", "dinner"]),
    "staple": ("主食", ["lunch", "dinner"]),
    "breakfast": ("早餐", ["breakfast"]),
    "dessert": ("甜品", ["breakfast", "dinner"]),
    "drink": ("饮料", ["breakfast"]),
    "condiment": ("调味", ["lunch", "dinner"]),
    "semi-finished": ("半成品", ["lunch", "dinner"]),
}

# 自动建表时，未知食材的粗略归类
ING_CATEGORY_MAP = {
    "vegetable_dish": "蔬菜", "meat_dish": "肉类", "aquatic": "水产",
    "soup": "其他", "staple": "粮油", "breakfast": "其他", "dessert": "其他",
    "drink": "其他", "condiment": "调味", "semi_finished": "其他",
    "semi-finished": "其他",
}

# 单位归一：克/g -> g，毫升/ml -> ml，个/颗/只/瓣 -> 个，勺类 -> ml，斤两换算
UNIT_NORMALIZE = {
    "克": "g", "g": "g", "千克": "g", "公斤": "g",
    "毫升": "ml", "ml": "ml",
    "个": "个", "颗": "个", "只": "个", "瓣": "个", "根": "个", "把": "个",
    "块": "个", "片": "个", "条": "个", "段": "个", "尾": "个", "枚": "个",
    "勺": "ml", "茶匙": "ml", "汤匙": "ml",
    "斤": "g", "两": "g",
}
# 需要乘的换算系数（针对「斤/两」这类非 g/ml/个 的单位）
UNIT_FACTOR = {"斤": 500.0, "两": 50.0}

_KNOWN_UNITS = sorted(UNIT_NORMALIZE.keys(), key=len, reverse=True)

# 安全求值的允许字符（代入 份数=1 后只允许这些）
_SAFE_FORMULA = re.compile(r"^[\d\.\s\+\-\*\(\)]+$")


@dataclass
class ParsedIngredient:
    raw_name: str
    amount: float          # 单人份用量（份数=1 代入后）
    unit: str              # 归一化后的单位 g/ml/个


@dataclass
class ParsedRecipe:
    name: str
    category: str
    meal_types: list[str]
    steps: list[str] = field(default_factory=list)
    ingredients: list[ParsedIngredient] = field(default_factory=list)
    difficulty: int = 1
    kcal: float = 0.0
    cook_minutes: Optional[int] = None
    note: str = ""
    servings_hint: Optional[int] = None
    source: str = "HowToCook"


class HowToCookParser:
    """把单个 HowToCook 菜谱 Markdown 解析为 ParsedRecipe。"""

    def parse(self, text: str, folder: str = "") -> ParsedRecipe:
        text = text.replace("\r\n", "\n")
        name = self._parse_title(text)
        cat, meal_types = CATEGORY_MAP.get(folder, ("其他", ["lunch", "dinner"]))
        difficulty = self._parse_difficulty(text)
        kcal = self._parse_kcal(text)
        servings = self._parse_servings(text)
        cook = self._parse_cook_minutes(text, difficulty)
        steps = self._parse_steps(text)
        ingredients = self._parse_ingredients(text)
        note = self._parse_note(text)
        return ParsedRecipe(
            name=name, category=cat, meal_types=meal_types, steps=steps,
            ingredients=ingredients, difficulty=difficulty, kcal=kcal,
            cook_minutes=cook, note=note, servings_hint=servings, source="HowToCook",
        )

    # ---------- 标题 ----------
    def _parse_title(self, text: str) -> str:
        m = re.search(r"^#\s+(.+?)\s*的做法\s*$", text, re.M)
        if m:
            return m.group(1).strip()
        # 退化：取首个一级标题
        m = re.search(r"^#\s+(.+)$", text, re.M)
        return (m.group(1).strip() if m else "未命名菜谱").rstrip("的做法").strip()

    # ---------- 难度 ----------
    def _parse_difficulty(self, text: str) -> int:
        m = re.search(r"预估烹饪难度[:：]\s*([★☆]+)", text)
        if m:
            return len(re.findall(r"★", m.group(1))) or len(m.group(1))
        return 1

    # ---------- 卡路里 ----------
    def _parse_kcal(self, text: str) -> float:
        m = re.search(r"预估卡路里[:：]\s*([\d.]+)\s*大卡", text)
        return float(m.group(1)) if m else 0.0

    # ---------- 单人份提示 ----------
    def _parse_servings(self, text: str) -> Optional[int]:
        # 「一份正好够 N 个人食用 / 吃」或「够 N 个人」
        m = re.search(r"一份正好够\s*(\d+)\s*个人", text)
        if m:
            return int(m.group(1))
        m = re.search(r"够\s*(\d+)\s*个人", text)
        return int(m.group(1)) if m else None

    # ---------- 烹饪时长 ----------
    def _parse_cook_minutes(self, text: str, difficulty: int) -> Optional[int]:
        # 优先从正文抓「约 N 分钟」「N 分钟以内」
        m = re.search(r"约\s*(\d+)\s*分钟", text)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+)\s*分钟以内", text)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+)\s*分钟", text)
        if m:
            return int(m.group(1))
        # 退化：按难度给默认值
        return {1: 15, 2: 20, 3: 30, 4: 45, 5: 60}.get(difficulty, 30)

    # ---------- 步骤 ----------
    def _parse_steps(self, text: str) -> list[str]:
        sec = self._section(text, "操作")
        if not sec:
            return []
        steps = []
        for line in sec.splitlines():
            line = line.strip()
            m = re.match(r"^\d+[\.、]\s*(.+)$", line)
            if m:
                steps.append(m.group(1).strip())
            elif line.startswith(("-", "*")) and steps:
                # 兼容无序列表写法
                steps.append(line.lstrip("-* ").strip())
        return [s for s in steps if s]

    # ---------- 食材用量 ----------
    def _parse_ingredients(self, text: str) -> list[ParsedIngredient]:
        sec = self._section(text, "计算")
        if not sec:
            return []
        out: list[ParsedIngredient] = []
        seen = set()
        for line in sec.splitlines():
            line = line.strip()
            if not (line.startswith("-") or line.startswith("*")):
                continue
            body = line.lstrip("-* ").strip()
            if not body:
                continue
            parsed = self._parse_one_ingredient(body)
            if parsed and parsed.raw_name not in seen:
                seen.add(parsed.raw_name)
                out.append(parsed)
        return out

    def _parse_one_ingredient(self, body: str) -> Optional[ParsedIngredient]:
        # 去掉括号里的补充说明，如「土豆 2 个（每个土豆大约重 120g）」
        body = re.sub(r"（.*?）", "", body)
        body = re.sub(r"\(.*?\)", "", body)
        # 名称 = 第一个数字之前的部分
        m = re.match(r"^([^\d]+?)\s*([\d].*)$", body)
        if not m:
            # 没有数字（例如纯工具「菜刀」）——跳过
            return None
        raw_name = m.group(1).strip()
        # 清理尾部噪声字符（原文常见「小龙虾 = 1000 克」式写法）
        raw_name = re.sub(r"[=＝/\\、,，。.：:•\-]+$", "", raw_name).strip()
        raw_name = re.sub(r"^[=＝/\\、,，。.：:•\-]+", "", raw_name).strip()
        if not raw_name:
            return None
        formula = m.group(2).strip()
        unit, amount = self._eval_formula(formula)
        if amount is None:
            return None
        return ParsedIngredient(raw_name=raw_name, amount=round(amount, 3), unit=unit)

    def _eval_formula(self, formula: str):
        """返回 (归一化单位, 单人份用量)。无法解析返回 (默认单位, None)。"""
        # 提取单位：取第一个数字后紧跟的单位词
        um = re.search(r"(\d+(?:\.\d+)?)\s*(" + "|".join(re.escape(u) for u in _KNOWN_UNITS) + r")", formula)
        raw_unit = um.group(2) if um else "g"
        unit = UNIT_NORMALIZE.get(raw_unit, "g")

        f = formula.replace("份数", "1")
        # 把「a-b」范围（无空格）替换为中值，避免被当减法
        f = re.sub(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)",
                   lambda mm: str((float(mm.group(1)) + float(mm.group(2))) / 2), f)
        f = f.replace("×", "*").replace("x", "*")
        # 剥离单位词，只保留纯算术（如「7.5 ml + 4 ml * 1」->「7.5 + 4 * 1」）
        f = re.sub(r"\s*(" + "|".join(re.escape(u) for u in _KNOWN_UNITS) + r")\s*", " ", f)
        f = f.strip()
        if not f or not _SAFE_FORMULA.match(f):
            # 没有可计算的表达式，尝试直接取第一个数字
            nm = re.search(r"(\d+(?:\.\d+)?)", formula)
            return unit, float(nm.group(1)) if nm else None
        try:
            val = eval(f, {"__builtins__": {}}, {})  # noqa: S307 受 _SAFE_FORMULA 约束
        except Exception:
            nm = re.search(r"(\d+(?:\.\d+)?)", formula)
            return unit, float(nm.group(1)) if nm else None
        # 斤/两 换算到 g
        if raw_unit in UNIT_FACTOR:
            val = val * UNIT_FACTOR[raw_unit]
            unit = "g"
        return unit, float(val)

    # ---------- 备注 ----------
    def _parse_note(self, text: str) -> str:
        sec = self._section(text, "附加内容")
        if not sec:
            return ""
        # 去掉「参考资料」链接行与固定免责声明
        lines = [ln.strip() for ln in sec.splitlines()
                 if ln.strip() and "参考资料" not in ln and "Issue" not in ln
                 and "Pull request" not in ln and "遵循本指南" not in ln]
        return "；".join(lines[:4])

    # ---------- 工具 ----------
    @staticmethod
    def _section(text: str, heading: str) -> Optional[str]:
        """提取 `## heading` 到下一个 `## ` 之间的内容。"""
        m = re.search(r"##\s*" + re.escape(heading) + r"\s*\n(.*?)(?=\n##\s|\Z)",
                      text, re.S)
        return m.group(1) if m else None
