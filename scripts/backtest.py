#!/usr/bin/env python3
"""
backtest.py — 用「滾動起點」回測 predict.py：每個起點只看當時已開始的池，預測之後 100 天，再對照實際。
用法：python scripts/backtest.py [--pools pools.json] [--from 2025-02-01] [--horizon 100]
注意：規則是在看過全部歷史之後才設計的（樣本內），所以數字偏樂觀；它能告訴你『哪類預測比較準』，不是未來的保證。
"""
import json, sys, argparse
from datetime import date, timedelta
from collections import defaultdict
import predict as PR
PR.KNOWN_UNDATED = []
D = date.fromisoformat

def pct(a, b): return "—" if b == 0 else f"{a}/{b} ({a / b:.0%})"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--pools", default="pools.json"); ap.add_argument("--from", dest="frm", default="2025-02-01")
    ap.add_argument("--horizon", type=int, default=100); ap.add_argument("--halflife", type=float, default=None); ap.add_argument("--mode", default=None); ap.add_argument("--k", type=int, default=None); ap.add_argument("--min-p", type=float, default=0.25)
    a = ap.parse_args()
    if a.halflife is not None: PR.HALF_LIFE = a.halflife
    if a.mode: PR.ANNUAL_MODE = a.mode
    if a.k: PR.REGIME_K = a.k
    data = json.load(open(a.pools, encoding="utf-8"))
    pools = [p for p in data["pools"] if not p.get("pred")]
    real = [p for p in pools if p["kind"] != "劇情"]
    last_known = max(D(p["start"]) for p in real)
    new_all = [p for p in real if not p["rerun"] and p["kind"] in PR.NEWKINDS]
    origins = sorted({D(p["start"]) for p in real if not p["rerun"] and p["kind"] in PR.MAIN and D(p["start"]) >= D(a.frm) and D(p["start"]) <= last_known - timedelta(days=30)})
    rows = []   # per prediction
    recall = defaultdict(lambda: [0, 0])
    for O in origins:
        known = [p for p in pools if D(p["start"]) <= O]
        preds, _ = PR.predict(known, O, a.horizon, a.min_p)
        lo, hi = O + timedelta(days=1), min(O + timedelta(days=a.horizon), last_known)
        for p in preds:
            ps = D(p["start"])
            if not (lo <= ps <= hi): continue
            if p["rerun"]:
                actual = [r for r in real if r["rerun"] and r["kind"] == "月卡" and abs((D(r["start"]) - ps).days) <= 10]
                strict = any(r["name"] == p["name"] and abs((D(r["start"]) - ps).days) <= 4 for r in actual)
                loose_name = any(r["name"] == p["name"] and abs((D(r["start"]) - ps).days) <= 10 for r in actual)
                rows.append(dict(O=O, rule="B 附掛月卡復刻", conf=p["conf"], p=p["p"], strict=strict, loose=loose_name, kind_only=bool(actual), char=None, name=p["name"], ps=ps))
            else:
                act = [q for q in new_all if q["kind"] == p["kind"]]
                d3 = [q for q in act if abs((D(q["start"]) - ps).days) <= 3]; d7 = [q for q in act if abs((D(q["start"]) - ps).days) <= 7]
                ch = None
                if p["chars"] and d7: ch = any(q["chars"] == p["chars"] for q in d7)
                label = {"A": "A 年度檔期", "E1": "E1 混池後第一檔", "E2": "E2 混池後第二檔"}.get(p.get("rule"), "A 年度檔期")
                rows.append(dict(O=O, rule=f"{label}（{p['kind']}）", conf=p["conf"], p=p["p"], strict=bool(d3), loose=bool(d7), kind_only=bool(d7), char=ch, name=p["name"], ps=ps))
        # recall：實際開池的新日卡／月卡／混池，有沒有被同類預測抓到（±7）
        for q in new_all:
            qs = D(q["start"])
            if not (O + timedelta(days=4) <= qs <= hi): continue
            hit = any((not p["rerun"]) and p["kind"] == q["kind"] and abs((D(p["start"]) - qs).days) <= 7 for p in preds)
            recall[q["kind"]][1] += 1; recall[q["kind"]][0] += hit
    # base rates：隨機一天，±3 天內有同類新池開池的機率
    span = (last_known - D(a.frm)).days
    base = {k: min(1.0, sum(1 for q in new_all if q["kind"] == k and q["start"] >= a.frm) * 7 / span) for k in PR.NEWKINDS}
    L = ["# 預測回測", "", f"- 起點 {len(origins)} 個（{origins[0]} ~ {origins[-1]}），每個起點預測之後 {a.horizon} 天；共 {len(rows)} 筆預測有答案可對照",
         "- ⚠️ 樣本內回測：規則是看過這份資料才設計的，數字偏樂觀；相鄰起點的預測窗口重疊，筆數不是獨立樣本。", "",
         "## 1. 依把握度分組：預測的開池日是否命中", "", "| 把握度 | 筆數 | ±3 天命中 | ±7 天命中 | 角色也對（有角色者） |", "|---|---|---|---|---|"]
    for b in ("高", "中高", "中", "中低"):
        g = [r for r in rows if r["conf"] == b]
        cg = [r for r in g if r["char"] is not None]
        L.append(f"| {b} | {len(g)} | {pct(sum(r['strict'] for r in g), len(g))} | {pct(sum(r['loose'] for r in g), len(g))} | {pct(sum(bool(r['char']) for r in cg), len(cg))} |")
    L += ["", "## 2. 依規則與類型分組", "", "| 規則 | 筆數 | ±3 天命中 | ±7 天命中 | 隨機亂猜的基準（±3 天） |", "|---|---|---|---|---|"]
    for rule in sorted({r["rule"] for r in rows}):
        g = [r for r in rows if r["rule"] == rule]
        kk = rule.split("（")[-1].rstrip("）") if rule.startswith(("A", "E")) else None
        L.append(f"| {rule} | {len(g)} | {pct(sum(r['strict'] for r in g), len(g))} | {pct(sum(r['loose'] for r in g), len(g))} | {('%.0f%%' % (base[kk] * 100)) if kk in base else '—'} |")
    g = [r for r in rows if r["rule"].startswith("B")]
    if g: L.append(f"| B（只看『是不是月卡復刻』，不管哪一張） | {len(g)} | — | {pct(sum(r['kind_only'] for r in g), len(g))} | — |")
    L += ["", "## 3. 年度檔期：連續幾年同日出現 vs. 命中", "", "（以預測筆數的 p 值近似連續年數：0.30＝1 年、0.55＝2 年、0.75＝3 年以上、0.90＝週年混池）", "", "| p | 筆數 | ±3 天 | ±7 天 |", "|---|---|---|---|"]
    for pv in sorted({r["p"] for r in rows if r["rule"].startswith("A")}):
        g = [r for r in rows if r["rule"].startswith("A") and r["p"] == pv]
        L.append(f"| {pv} | {len(g)} | {pct(sum(r['strict'] for r in g), len(g))} | {pct(sum(r['loose'] for r in g), len(g))} |")
    L += ["", "## 4. 召回：實際開池的新池，有沒有被同類預測抓到（±7 天）", "", "| 類型 | 抓到 |", "|---|---|"]
    for k in PR.NEWKINDS: L.append(f"| {k} | {pct(*recall[k])} |")
    L += ["", "## 5. 分時期（年度檔期規則）", "", "| 時期 | 筆數 | ±3 天命中 | ±7 天命中 |", "|---|---|---|---|"]
    for nm, f in (("2026-05 以前（事件前）", lambda r: r["ps"] < date(2026, 6, 1)), ("2026-06 起（事件後）", lambda r: r["ps"] >= date(2026, 6, 1))):
        g = [r for r in rows if r["rule"].startswith("A") and f(r)]
        L.append(f"| {nm} | {len(g)} | {pct(sum(r['strict'] for r in g), len(g))} | {pct(sum(r['loose'] for r in g), len(g))} |")
    ann = [r for r in rows if r["rule"].startswith("A") and r["p"] != 0.85]
    if ann:
        br = sum((r["p"] - (1 if r["strict"] else 0)) ** 2 for r in ann) / len(ann)
        base_rate = sum(1 for r in ann if r["strict"]) / len(ann)
        brb = sum((base_rate - (1 if r["strict"] else 0)) ** 2 for r in ann) / len(ann)
        L += ["", "## 6. 校準：預測給的把握度準不準（年度檔期、不含週年混池）", "",
              f"- Brier 分數 {br:.3f}（越小越準；永遠猜『全體平均命中率 {base_rate:.0%}』是 {brb:.3f}）",
              "", "| 預測給的把握度 | 筆數 | 實際 ±3 天命中 |", "|---|---|---|"]
        for lo, hi in ((0, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.7), (0.7, 1.01)):
            g = [r for r in ann if lo <= r["p"] < hi]
            if g: L.append(f"| {lo:.1f}–{min(hi,1):.1f} | {len(g)} | {pct(sum(r['strict'] for r in g), len(g))} |")
    md = "\n".join(L) + "\n"; print(md)
    json.dump([{**r, "O": r["O"].isoformat(), "ps": r["ps"].isoformat()} for r in rows], open("backtest_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)

if __name__ == "__main__":
    main()
