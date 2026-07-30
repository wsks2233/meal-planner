"""HowToCook 解析器离线单测（不依赖数据库/网络）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.recipe_source import HowToCookParser  # noqa: E402

LIANG_BAN_HUANG_GUA = """# 凉拌黄瓜的做法

这是一道清爽开胃的家常凉菜，口感脆嫩，酸香适口。黄瓜富含水分和维生素，有助于清热解暑、美容养颜。做法非常简单，对新手友好，只需拍碎、调味、腌制 15 分钟，全程约 20 分钟即可完成。

预估烹饪难度：★

预估卡路里：107 大卡

## 必备原料和工具

* 黄瓜
* 醋
* 酱油
* 蒜

## 计算

每次制作前需要确定计划做几份。一份正好够 1 个人食用

总量：

* 黄瓜 200 克  * 份数
* 醋 7.5 ml + 4 ml * 份数
* 酱油 5 ml + 2.5 ml * 份数
* 蒜 3 瓣 * 份数
* 盐 0.4 克 + 0.2 克 * 份数
* 香油 5 ml + 2 ml * 份数
* 蚝油 5 ml

## 操作

1. 用菜刀将黄瓜拍扁，再剁成长 3 厘米的碎块
2. 将碎黄瓜装入碗中
3. 将蒜拍碎切成碎末
4. 将碗中放入 5 克白糖，搅拌均匀腌制 15 分钟
5. 将醋，酱油，盐，蚝油和蒜依次倒入碗中搅拌均匀
6. 将香油倒入碗中并均匀搅拌

## 附加内容

* 部分情况下黄瓜端头有苦味，请洗净切下后确认
* 做好之后直接开吃，亦可先准备好后放入冰箱冷藏后食用
* 参考资料：[世界美食教程的微博视频](http://t.cn/EJ77yFy)
"""

TEMPLATE = """# 示例菜的做法

示例菜是一道简单易做的菜。富含 DHA 和蛋白质。一般初学者只需要 3 小时即可完成。还有美容效果哦~

预估烹饪难度：★★★★

预估卡路里：1265 大卡

## 必备原料和工具

- 咖喱块（推荐品牌好侍）
- 土豆
- 藤椒油（可选）

## 计算

每次制作前需要确定计划做几份。一份正好够 2 个人吃。

每份：

- 咖喱块 115g
- 土豆 2 个（每个土豆大约重 120g，共约 240g）
- 食用油 10-15ml

## 操作

1. 土豆去皮、切成不超过 4cm 的大块，备用
2. 咖喱块切碎，增加接触面积加速溶解，备用
3. 热锅，锅内放入 10ml - 15ml 食用油。等待 10 秒让油温升高
4. 放入土豆，保持翻炒至土豆*变软*
5. 加水没过所有食材，沸腾后，将火调小然后**等待 15 - 20 分钟**
6. 关火，加咖喱并搅拌，等待直至咖喱融化
7. 再开火，缓慢**搅拌 10 分钟**，防止糊锅
8. 在外观*呈粘稠状态*后关火，盛盘

## 附加内容

- 操作时，需要注意观察沸腾的水位线
- 参考资料：[世界美食教程的微博视频](http://t.cn/EJ77yFy)
"""


def _by_name(items, name):
    for it in items:
        if it.raw_name == name:
            return it
    return None


def test_liangbanhuanggua_basic():
    p = HowToCookParser().parse(LIANG_BAN_HUANG_GUA, "vegetable_dish")
    assert p.name == "凉拌黄瓜", p.name
    assert p.category == "副菜"
    assert p.meal_types == ["lunch", "dinner"]
    assert p.difficulty == 1
    assert p.kcal == 107.0
    assert p.servings_hint == 1
    assert p.cook_minutes == 20, p.cook_minutes
    assert len(p.steps) == 6, p.steps


def test_liangbanhuanggua_formula_eval():
    p = HowToCookParser().parse(LIANG_BAN_HUANG_GUA, "vegetable_dish")
    ing = {i.raw_name: i for i in p.ingredients}
    # 公式代入 份数=1 后的单人份用量
    assert ing["黄瓜"].amount == 200 and ing["黄瓜"].unit == "g"
    assert abs(ing["醋"].amount - 11.5) < 1e-6 and ing["醋"].unit == "ml"
    assert abs(ing["酱油"].amount - 7.5) < 1e-6
    assert ing["蒜"].amount == 3 and ing["蒜"].unit == "个"
    assert abs(ing["盐"].amount - 0.6) < 1e-6
    assert abs(ing["香油"].amount - 7.0) < 1e-6
    assert ing["蚝油"].amount == 5 and ing["蚝油"].unit == "ml"


def test_template_structure():
    p = HowToCookParser().parse(TEMPLATE, "meat_dish")
    assert p.name == "示例菜"
    assert p.difficulty == 4
    assert p.kcal == 1265.0
    # 单位归一 + 括号剔除 + 范围取中值
    ing = {i.raw_name: i for i in p.ingredients}
    assert ing["咖喱块"].amount == 115 and ing["咖喱块"].unit == "g"
    assert ing["土豆"].amount == 2 and ing["土豆"].unit == "个"
    assert abs(ing["食用油"].amount - 12.5) < 1e-6 and ing["食用油"].unit == "ml"
    assert len(p.steps) == 8


if __name__ == "__main__":
    test_liangbanhuanggua_basic()
    test_liangbanhuanggua_formula_eval()
    test_template_structure()
    print("ALL OK")
