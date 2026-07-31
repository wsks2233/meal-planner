"""API 审计：价格相关接口缺陷扫描（在用户重建镜像、亲自测试之前先发现缺陷）。

运行（项目 venv，需 httpx）：
  backend\\venv\\Scripts\\python.exe tests/api_audit_prices.py

设计：
- 不导入完整 app（避免 apscheduler/playwright 等传递依赖与启动时真实抓取）。
- 仅挂载 prices 路由，用 TestClient + 依赖覆盖指向隔离 SQLite。
- 覆盖 /latest、/trend/{id}、/source 的常态、边界、异常与前后端契约。
"""
import os
import sys
import tempfile
from datetime import date, timedelta

# 必须在导入任何 app 模块之前固定测试库，否则 engine 会绑定到默认 meal.db
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_TMP = tempfile.mkdtemp(prefix="meal_api_audit_")
_DB = os.path.join(_TMP, "audit.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.database as dbmod  # noqa: E402  (engine 已绑定测试库)
from app import models  # noqa: E402
from app.services.price_engine import PriceSourceAdapter, CompositePriceSource  # noqa: E402
from app.routers import prices as prices_router  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# ---------------- 测试基础设施 ----------------
engine = dbmod.engine
models.Base.metadata.drop_all(engine)
models.Base.metadata.create_all(engine)

app = FastAPI()
app.include_router(prices_router.router)


def override_get_db():
    with Session(engine) as s:
        yield s


app.dependency_overrides[dbmod.get_db] = override_get_db
client = TestClient(app)

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((status, name, detail))
    print(f"[{status}] {name}" + (f"  -> {detail}" if detail else ""))


def reset():
    """清空 ingredients / price_records，便于每个场景独立构造。"""
    with Session(engine) as s:
        s.query(models.PriceRecord).delete()
        s.query(models.Ingredient).delete()
        s.commit()


def add_ingredient(name, category="蔬菜", base_price=5.0):
    with Session(engine) as s:
        ing = models.Ingredient(name=name, category=category, base_price=base_price)
        s.add(ing)
        s.commit()
        s.refresh(ing)
        return ing.id


def add_price(iid, price, day, source="模拟数据(演示)", spec="元/500克"):
    with Session(engine) as s:
        s.add(models.PriceRecord(ingredient_id=iid, price=price, date=day,
                                 source=source, spec=spec))
        s.commit()


def keys_of(item):
    return set(item.keys())


# ---------------- 场景 A：/latest 无价（调度未跑/无数据）----------------
def scenario_a_empty():
    reset()
    i1, i2, i3 = (add_ingredient(f"A空{n}") for n in range(3))
    r = client.get("/api/prices/latest")
    check("A1 /latest 无数据时返回 200", r.status_code == 200, f"status={r.status_code}")
    body = r.json()
    check("A2 返回全部食材", len(body) == 3, f"len={len(body)}")
    keyset = keys_of(body[0]) if body else set()
    expected = {"ingredient_id", "name", "icon", "category", "price", "spec",
                "date", "change_7d", "source", "available", "source_url"}
    check("A3 字段集合完整", keyset == expected, f"got={sorted(keyset)}")
    all_unavail = all((not it["available"]) and it["source"] == "暂无可靠价"
                      and it["price"] is None and it["change_7d"] is None for it in body)
    check("A4 无价项 available=False/source=暂无可靠价/price=None/change_7d=None",
          all_unavail)
    consistent = all(keys_of(it) == keyset for it in body)
    check("A5 所有项字段一致（含无价项）", consistent)


# ---------------- 场景 B：/latest 单条记录/ingredient ----------------
def scenario_b_single():
    reset()
    i1 = add_ingredient("B单")
    add_price(i1, 9.9, date.today(), source="政府指导价")
    r = client.get("/api/prices/latest").json()
    it = r[0]
    check("B1 单条记录 available=True", it["available"] is True)
    check("B2 价格透传正确", abs(it["price"] - 9.9) < 1e-9, f"price={it['price']}")
    check("B3 单条记录 change_7d=None（无上一期，前端显示『—』）", it["change_7d"] is None,
          f"change_7d={it['change_7d']}")
    check("B4 source 透传后端真实来源", it["source"] == "政府指导价",
          f"source={it['source']}")


# ---------------- 场景 C：/latest 两条记录（周环比）----------------
def scenario_c_two():
    reset()
    i1 = add_ingredient("C涨")
    i2 = add_ingredient("C跌")
    add_price(i1, 8.0, date.today() - timedelta(days=7))
    add_price(i1, 10.0, date.today())
    add_price(i2, 10.0, date.today() - timedelta(days=7))
    add_price(i2, 5.0, date.today())
    r = {it["name"]: it for it in client.get("/api/prices/latest").json()}
    # (10-8)/8*100 = 25.0
    check("C1 上涨正确 +25.0%", abs(r["C涨"]["change_7d"] - 25.0) < 1e-9,
          f"got={r['C涨']['change_7d']}")
    # (5-10)/10*100 = -50.0
    check("C2 下跌正确 -50.0%", abs(r["C跌"]["change_7d"] - (-50.0)) < 1e-9,
          f"got={r['C跌']['change_7d']}")


# ---------------- 场景 D：old.price==0 防零除 ----------------
def scenario_d_zero():
    reset()
    i1 = add_ingredient("D零基")
    add_price(i1, 0.0, date.today() - timedelta(days=7))
    add_price(i1, 5.0, date.today())
    r = client.get("/api/prices/latest")
    check("D1 old.price=0 不 500", r.status_code == 200, f"status={r.status_code}")
    it = r.json()[0]
    check("D2 old.price=0 时 change 记为 None（不臆造 0%，亦不除零）", it["change_7d"] is None,
          f"change_7d={it['change_7d']}")


# ---------------- 场景 E：14 天窗口边界 ----------------
def scenario_e_boundary():
    reset()
    i_in = add_ingredient("E边界内")   # today-14 应被包含（>=）
    i_out = add_ingredient("E边界外")   # today-15 应被排除 -> 无价
    add_price(i_in, 3.0, date.today() - timedelta(days=14))
    add_price(i_out, 3.0, date.today() - timedelta(days=15))
    r = {it["name"]: it for it in client.get("/api/prices/latest").json()}
    check("E1 today-14 命中（available=True）", r["E边界内"]["available"] is True,
          f"source={r['E边界内']['source']}")
    check("E2 today-15 排除（available=False）", r["E边界外"]["available"] is False,
          f"source={r['E边界外']['source']}")


# ---------------- 场景 F：来源字符串契约（前端 Dashboard 计数依赖）----------------
def scenario_f_contract():
    reset()
    i1 = add_ingredient("FGov")
    i2 = add_ingredient("F电")
    add_price(i1, 2.0, date.today(), source="政府指导价")
    add_price(i2, 12.0, date.today(), source="电商平台参考价")
    r = {it["name"]: it for it in client.get("/api/prices/latest").json()}
    check("F1 政府价来源串与前端契约一致", r["FGov"]["source"] == "政府指导价")
    check("F2 电商来源串与前端契约一致", r["F电"]["source"] == "电商平台参考价")


# ---------------- 场景 G：窗口内 >2 条记录时 change_7d 应为「本期 vs 上一期」 ----------------
def scenario_g_multi():
    reset()
    i1 = add_ingredient("G多")
    # 三周记录，每周一条：6 -> 8 -> 10
    add_price(i1, 6.0, date.today() - timedelta(days=14))
    add_price(i1, 8.0, date.today() - timedelta(days=7))
    add_price(i1, 10.0, date.today())
    it = client.get("/api/prices/latest").json()[0]
    # 修复后：rows[-1]=10 vs rows[-2]=8 -> (10-8)/8*100 = 25.0（真正的周环比）
    current = it["change_7d"]
    check("G1 修复后 change_7d = (本期-上一期)/上一期 = 25.0（而非多周累计 66.7）",
          abs(current - 25.0) < 0.15, f"got={current}")


# ---------------- 场景 H：/trend 正常 ----------------
def scenario_h_trend_ok():
    reset()
    i1 = add_ingredient("H趋")
    for d in range(10, 0, -1):
        add_price(i1, 5.0 + d * 0.1, date.today() - timedelta(days=d),
                  source="政府指导价")
    r = client.get(f"/api/prices/trend/{i1}?days=30")
    check("H1 /trend 正常 200", r.status_code == 200, f"status={r.status_code}")
    body = r.json()
    check("H2 dates 升序", body["dates"] == sorted(body["dates"]), f"dates={body['dates']}")
    check("H3 dates 与 prices 等长", len(body["dates"]) == len(body["prices"]),
          f"{len(body['dates'])} vs {len(body['prices'])}")
    check("H4 source 取最新一条来源", body["source"] == "政府指导价",
          f"source={body['source']}")


# ---------------- 场景 I：/trend 无数据 ----------------
def scenario_i_trend_empty():
    reset()
    i1 = add_ingredient("I空趋")
    r = client.get(f"/api/prices/trend/{i1}?days=30")
    check("I1 /trend 无数据仍 200", r.status_code == 200, f"status={r.status_code}")
    body = r.json()
    check("I2 空列表", body["dates"] == [] and body["prices"] == [])
    # 契约不一致：/latest 无价为『暂无可靠价』，/trend 无数据却回『模拟数据(演示)』
    check("I3 修复后空趋势 source='暂无可靠价'（与 /latest 一致）",
          body["source"] == "暂无可靠价", f"source={body['source']}")


# ---------------- 场景 J：/trend 非法 id -> 404 ----------------
def scenario_j_trend_404():
    r = client.get("/api/prices/trend/999999?days=30")
    check("J1 非法 ingredient_id 返回 404", r.status_code == 404, f"status={r.status_code}")
    check("J2 404 带 detail", bool(r.json().get("detail")), f"detail={r.json().get('detail')}")


# ---------------- 场景 K：/trend days 参数校验（Query(ge=1, le=365)）----------------
def scenario_k_days():
    reset()
    i1 = add_ingredient("K天")
    add_price(i1, 7.0, date.today())           # 仅今天
    add_price(i1, 6.0, date.today() - timedelta(days=5))
    r_valid = client.get(f"/api/prices/trend/{i1}?days=10")
    check("K1 合法 days=10 正常 200", r_valid.status_code == 200, f"status={r_valid.status_code}")
    check("K2 days=10 命中今天与 5 天前两条", len(r_valid.json()["dates"]) == 2,
          f"len={len(r_valid.json()['dates'])}")
    r0 = client.get(f"/api/prices/trend/{i1}?days=0")
    check("K3 days=0 被校验拒绝 422", r0.status_code == 422, f"status={r0.status_code}")
    rn = client.get(f"/api/prices/trend/{i1}?days=-5")
    check("K4 days=-5 被校验拒绝 422", rn.status_code == 422, f"status={rn.status_code}")
    rh = client.get(f"/api/prices/trend/{i1}?days=9999")
    check("K5 days=9999 被校验拒绝 422", rh.status_code == 422, f"status={rh.status_code}")


# ---------------- 场景 L：/source 结构（stub 真实工厂，规避 playwright 依赖）----------------
def scenario_l_source():
    class _Stub(PriceSourceAdapter):
        source_name = "X"
        def fetch(self, ingredients, day):
            return {}

    fake = CompositePriceSource([_Stub(), _Stub()])
    orig = prices_router.get_price_source
    prices_router.get_price_source = lambda: fake
    try:
        r = client.get("/api/prices/source")
        check("L1 /source 200", r.status_code == 200, f"status={r.status_code}")
        body = r.json()
        check("L2 composite 结构含 type/sources/note",
              body.get("type") == "composite" and "sources" in body and "note" in body,
              f"body={body}")
    finally:
        prices_router.get_price_source = orig


# ---------------- 执行 ----------------
def main():
    scenario_a_empty()
    scenario_b_single()
    scenario_c_two()
    scenario_d_zero()
    scenario_e_boundary()
    scenario_f_contract()
    scenario_g_multi()
    scenario_h_trend_ok()
    scenario_i_trend_empty()
    scenario_j_trend_404()
    scenario_k_days()
    scenario_l_source()

    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print("\n==== 审计汇总 ====")
    print(f"总检查项: {len(RESULTS)}  通过: {len(RESULTS)-len(fails)}  失败: {len(fails)}")
    # 缺陷/提示已由各场景 print 输出
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
