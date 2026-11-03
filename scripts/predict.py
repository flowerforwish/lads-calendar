#!/usr/bin/env python3
"""
predict.py — 戀與深空卡池「規則式」預測（只改 pools.json 裡 pred=true 的項目，不動任何已發生／已公告的資料）

設計：不是叫 AI 亂猜，而是把歷史資料裡量得出來的規律寫成規則，每條規則都附依據與把握度，並可回測。
  規則 A 年度檔期   ：去年同一天附近出現的新池（日卡／月卡／混池），今年同日再出現（連續年數越多越有把握）
  規則 B 附掛復刻   ：新日卡／新月卡／新混池收尾時，常搭配一檔 7 天的月卡復刻；復刻對象照「原池順序」，且受「原池→復刻間隔」限制
  規則 C 角色輪序   ：日卡角色照 祁→沈→黎→秦→夏 輪；月卡取「最久沒當月卡的角色」（近 8 次命中 7 次）
  規則 D 互斥       ：新池不會和另一檔新池重疊（歷史上沒發生過）；已被現實資料「占掉」的年度檔期不再預測
  已知但未定日期    ：官方只說「11 月更新」之類的，放在 KNOWN_UNDATED，以區間中點畫一條虛線，並註明日期未定
不處理（把握度太低，只列在報告裡）：生日池（固定日期，視野內沒有）、跟在月卡／混池後面的日卡／混池復刻、新月卡角色以外的細節

用法：python scripts/predict.py [--pools pools.json] [--today YYYY-MM-DD] [--horizon 100] [--min-p 0.30] [--dry]
輸出：更新 pools.json 中的預測；GitHub Actions 的 Job Summary 會列出每一檔預測與依據；--dry 只印不寫。
"""
import json, os, re, sys, argparse
from datetime import date, datetime, timedelta, timezone
from collections import Counter, defaultdict

D = date.fromisoformat
TW = timezone(timedelta(hours=8))
MAIN = ("日卡", "月卡", "混池", "生日", "自選")
NEWKINDS = ("日卡", "月卡", "混池")
CHARS = ["夏以晝", "祁煜", "沈星回", "黎深", "秦徹"]
CN = "一二三四五六七八"

# 官方已預告但沒給日期的事件（手動維護；有日期後 update_pv.py 會把真實資料加進來，這裡的預測就會因同名而自動隱藏）
KNOWN_UNDATED = [
    dict(name="秦徹主線分線", kind="劇情", chars="秦徹", window=("2026-11-01", "2026-11-30"), length=10,
         source="官方 YouTube 說明欄（9/14）：「秦徹分線將於 11 月更新」"),
]

def yplus(d, n=1):
    try: return d.replace(year=d.year + n)
    except ValueError: return d.replace(year=d.year + n, day=28)

def bucket(p):
    return "高" if p >= 0.80 else "中高" if p >= 0.60 else "中" if p >= 0.45 else "中低" if p >= 0.30 else "低"

class Ctx:
    def __init__(self, pools):
        self.real = [p for p in pools if not p.get("pred")]
        self.main = sorted([p for p in self.real if p["kind"] in MAIN], key=lambda p: (p["start"], p["rerun"]))
        self.new = [p for p in self.main if not p["rerun"]]
        self.reruns = [p for p in self.main if p["rerun"]]
        self.story = [p for p in self.real if p["kind"] == "劇情"]

# ---------------- 規則 C：角色輪序 ----------------
def next_daily_char(ctx, asof):
    ev = [p for p in ctx.new if p["kind"] == "日卡" and D(p["start"]) < asof]
    last = {}
    for p in ev: last[p["chars"]] = D(p["start"])
    if not ev: return None, 0.0, "沒有日卡歷史"
    order = sorted(CHARS, key=lambda c: (c in last, last.get(c, date(1900, 1, 1))))
    seq = [p["chars"] for p in ev]
    hits = tot = 0
    seen = {}
    for a, b in zip(seq, seq[1:]):
        if a in seen: hits += (seen[a] == b); tot += 1
        seen[a] = b
    return order[0], (hits + 1) / (tot + 2), f"日卡角色輪序（歷史 {hits}/{tot} 次照輪序）"

def next_monthly_char(ctx, asof, window=8):
    ev = [p for p in ctx.new if p["kind"] == "月卡" and D(p["start"]) < asof]
    if len(ev) < 6: return None, 0.0, ""
    def pick(hist):
        last = {}
        for p in hist: last[p["chars"]] = D(p["start"])
        return sorted(CHARS, key=lambda c: (c in last, last.get(c, date(1900, 1, 1))))[0]
    recent = ev[-window:]; hits = 0
    for i, p in enumerate(recent):
        hist = ev[:len(ev) - len(recent) + i]
        hits += (pick(hist) == p["chars"])
    return pick(ev), (hits + 1) / (len(recent) + 2), f"月卡取最久沒當月卡的角色（近 {len(recent)} 次命中 {hits} 次）"

# ---------------- 規則 A：年度檔期 ----------------
def annual_slots(ctx, today, horizon):
    out, end_day = [], today + timedelta(days=horizon)
    for q in ctx.new:
        if q["kind"] not in NEWKINDS: continue
        qs = D(q["start"]); tgt = yplus(qs, 1)
        if not (today <= tgt <= end_day): continue
        # 往前數：這個檔期連續幾年在同一天（±3）出現過同類新池
        recur, cur = 1, qs
        while True:
            prev = [x for x in ctx.new if x["kind"] == q["kind"] and abs((D(x["start"]) - yplus(cur, -1)).days) <= 3]
            if not prev: break
            recur += 1; cur = D(prev[0]["start"])
        out.append(dict(kind=q["kind"], start=tgt, length=(D(q["end"]) - qs).days, recur=recur, tmpl=q))
    # 同一天附近同類只留一個（取連續年數多者）
    out.sort(key=lambda s: (-s["recur"], s["start"]))
    kept = []
    for s in out:
        if any(k["kind"] == s["kind"] and abs((k["start"] - s["start"]).days) <= 3 for k in kept): continue
        kept.append(s)
    return sorted(kept, key=lambda s: s["start"])

ANNUAL_MODE = "regime"   # "regime"（看最近幾檔對不對得上去年）或 "trailing"（近一年命中率）；由回測的 Brier 分數決定
REGIME_K = 3      # 年度檔期規則：看「最近 K 檔新日卡／月卡／混池」有幾檔和去年同日對得上（連續對得上＝照去年排；對不上＝這段時間沒在照去年排）
HALF_LIFE = 120   # 天：越近的命中／落空權重越大（回測用 Brier 分數選出，見 backtest.py --halflife）

def annual_precision(pools_all, today, lookback=365, half_life=None):
    """用「過去一年」每個起點的年度檔期預測對照實際，得到這條規則最近的命中率（±3 天、同類新池）。
    每個 (類型, 目標日) 只算一次，避免相鄰起點重複計分。回傳 (命中, 筆數)。"""
    real = [p for p in pools_all if not p.get("pred") and p["kind"] in MAIN]
    new_all = [p for p in real if not p["rerun"] and p["kind"] in NEWKINDS]
    if not new_all: return 0.0, 0.0, 0, 0
    last_known = max(D(p["start"]) for p in real)
    cut = min(today, last_known)
    origins = sorted({D(p["start"]) for p in real if not p["rerun"] and today - timedelta(days=lookback) <= D(p["start"]) <= cut - timedelta(days=30)})
    half_life = HALF_LIFE if half_life is None else half_life
    seen = {}
    for o in origins:
        c = Ctx([p for p in pools_all if not p.get("pred") and D(p["start"]) <= o])
        for sl in annual_slots(c, o, 100):
            if not (o < sl["start"] <= cut): continue
            key = (sl["kind"], sl["start"])
            if key in seen: continue
            seen[key] = any(q["kind"] == sl["kind"] and abs((D(q["start"]) - sl["start"]).days) <= 3 for q in new_all)
    w = {k: (0.5 ** ((cut - k[1]).days / half_life) if half_life else 1.0) for k in seen}
    return sum(w[k] for k, v in seen.items() if v), sum(w.values()), sum(seen.values()), len(seen)

def annual_regime(pools_all, today, k=None):
    """最近 k 檔新日卡／月卡／混池，有幾檔「去年同日（±3 天）也有同類新池」。回傳 (對得上, 檔數)。"""
    k = REGIME_K if k is None else k
    real = [p for p in pools_all if not p.get("pred") and p["kind"] in NEWKINDS and not p["rerun"] and D(p["start"]) <= today]
    real.sort(key=lambda p: p["start"])
    if not real: return 0, 0
    first = D(real[0]["start"]); allnew = real
    cand = [p for p in real if D(p["start"]) >= yplus(first, 1)][-k:]
    m = sum(1 for p in cand if any(q["kind"] == p["kind"] and abs((D(q["start"]) - yplus(D(p["start"]), -1)).days) <= 3 for q in allnew if q is not p))
    return m, len(cand)

def p_annual(slot, prec, regime=None):
    if slot["kind"] == "混池" and slot["start"].month == 12 and slot["start"].day == 31:
        return 0.85, "週年混池（2024、2025 都是 12/31 同日開，且為大版本更新日）"
    if regime is not None and ANNUAL_MODE == "regime":
        m, n = regime
        return min(0.50, (m + 0.5) / (n + 1.0)), f"去年同日（±3 天）有同類新池；但最近 {n} 檔新池只有 {m} 檔和去年同日對得上（這段時間{'有' if m * 2 >= n else '沒有'}在照去年排）"
    wh, wn, h, n = prec
    return (wh + 0.5) / (wn + 1.0), f"去年同日（±3 天）有同類新池；這條規則近一年命中 {h}/{n} 檔（越近的結果權重越大）"

# ---------------- 規則 B：附掛的月卡復刻 ----------------
def tail_stats(ctx, kind, since="2025-10-01"):
    hosts = [h for h in ctx.new if h["kind"] == kind and h["start"] >= since and D(h["end"]) < date.fromisoformat(ctx.last_real_end)]
    k = 0
    for h in hosts:
        he = D(h["end"])
        if any(r["kind"] == "月卡" and D(h["start"]) <= D(r["start"]) and he - timedelta(days=1) <= D(r["end"]) <= he + timedelta(days=5) for r in ctx.reruns): k += 1
    return k, len(hosts)

def monthly_lags(ctx):
    orig = {p["name"]: p for p in ctx.new if p["kind"] == "月卡"}
    return [(D(r["start"]) - D(orig[r["name"]]["start"])).days for r in ctx.reruns if r["kind"] == "月卡" and r["name"] in orig]

def tail_reruns(ctx, hosts, today, horizon, all_hosts=None):
    """hosts: [(start,end,kind,p_host,label)]，依時間排序（含已確定的與預測的新池）"""
    lags = monthly_lags(ctx)
    if not lags: return []
    lo, hi = min(lags) - 20, max(lags) + 40
    orig = sorted([p for p in ctx.new if p["kind"] == "月卡"], key=lambda p: p["start"])
    done = {r["name"] for r in ctx.reruns if r["kind"] == "月卡"}
    todo = [p for p in orig if p["name"] not in done]
    out = []
    for i, (hs, he, hk, ph, lab) in enumerate(hosts):
        if hk not in NEWKINDS or not todo: continue
        k, n = tail_stats(ctx, hk)
        if n == 0: continue
        p_tail = (k + 1) / (n + 2)
        pool = all_hosts or hosts
        later = [h[0] for h in pool if h[0] > hs and h[3] >= 0.5]
        nxt = min(later) if later else None
        te = nxt if (nxt and 0 <= (nxt - he).days <= 5) else he
        ts = te - timedelta(days=7)
        if ts < today or ts > today + timedelta(days=horizon): continue
        if any(r["kind"] == "月卡" and abs((D(r["start"]) - ts).days) <= 4 for r in ctx.reruns): continue   # 已有真實復刻
        cand = todo[0]; lag = (ts - D(cand["start"])).days
        ok = lo <= lag <= hi
        out.append(dict(card=cand, start=ts, end=te, p=min(0.65, p_tail) * ph * (1.0 if ok else 0.4), k=k, n=n, hk=hk, lag=lag, lag_ok=ok,
                        host=lab, lag_range=(min(lags), max(lags))))
        todo = todo[1:]
    return out

# ---------------- 規則 E：混池結束後的接續 ----------------
def follow_stats(ctx):
    gaps, kinds = [], Counter()
    mixes = [p for p in ctx.new if p["kind"] == "混池"]
    for m in mixes:
        nx = [q for q in ctx.new if D(q["start"]) > D(m["start"]) and q is not m]
        if not nx: continue
        q = nx[0]; g = (D(q["start"]) - D(m["end"])).days
        gaps.append(g)
        if g <= 7 and q["kind"] != "生日": kinds[q["kind"]] += 1
    within = sum(1 for g in gaps if g <= 7)
    return within, len(gaps), kinds

def birthday_dates(ctx):
    return sorted({(D(p["start"]).month, D(p["start"]).day) for p in ctx.new if p["kind"] == "生日"})

def birthday_due(ctx, d0, d1):
    """生日池是固定日期（每位男主每年同一天）；d0~d1 之間有沒有生日？"""
    days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    bd = birthday_dates(ctx)
    return any(any(abs((date(x.year, m, dd) - x).days) <= 1 for (m, dd) in bd) for x in days)

def transitions(ctx):
    tr = defaultdict(Counter)
    for a, b in zip(ctx.new, ctx.new[1:]): tr[a["kind"]][b["kind"]] += 1
    return tr

def typical_len(ctx, kind):
    ls = sorted((D(p["end"]) - D(p["start"])).days for p in ctx.new if p["kind"] == kind and p["start"] >= "2025-01-01")
    return ls[len(ls) // 2] if ls else {"日卡": 14, "月卡": 9, "混池": 18}.get(kind, 9)

def median_gap(ctx):
    g = sorted((D(b["start"]) - D(a["end"])).days for a, b in zip(ctx.new, ctx.new[1:]) if (D(b["start"]) - D(a["end"])).days >= 0)
    return g[len(g) // 2] if g else 2

def chain_precision(pools_all, today):
    """規則 E 第一檔的實際命中率：對每個「已經結束且接續者已知」的混池，只用當時的資料預測下一檔，再對照實際（同類、開池日差 ≤5 天）。"""
    real = [p for p in pools_all if not p.get("pred") and p["kind"] in MAIN]
    new_all = sorted([p for p in real if not p["rerun"] and p["kind"] in NEWKINDS or (not p["rerun"] and p["kind"] in ("生日", "自選"))], key=lambda p: p["start"])
    h = n = 0
    for m in [p for p in new_all if p["kind"] == "混池" and D(p["end"]) < today]:
        nxt = [q for q in new_all if q["start"] > m["start"]]
        if not nxt: continue
        c = Ctx([p for p in pools_all if not p.get("pred") and D(p["start"]) <= D(m["start"])])
        ch = chain_after_mix(c, D(m["start"]), None, use_precision=False)
        if not ch: continue
        e1 = ch[0]; n += 1
        h += any(q["kind"] == e1["kind"] and abs((D(q["start"]) - e1["start"]).days) <= 5 for q in nxt[:3])
    return h, n

def chain_after_mix(ctx, today, anchor_start=None, use_precision=True, pools_all=None):
    """規則 E：最後一檔真實新池是混池 -> 預測它之後接續的新池（第一檔靠『混池後 7 天內接續』的歷史；第二檔靠『前一檔的種類 → 下一檔種類』的歷史）"""
    if not ctx.new: return []
    last = max(ctx.new, key=lambda p: (p["start"], p["end"]))
    if last["kind"] != "混池" or D(last["end"]) < today - timedelta(days=7): return []
    me = D(last["end"]); gap = median_gap(ctx)
    fw, fn, fk = follow_stats(ctx)
    if not fn: return []
    pool = {k: fk.get(k, 0) for k in ("月卡", "日卡")}
    tot = sum(fk.values())
    if birthday_due(ctx, me, me + timedelta(days=9)) or tot == 0: return []   # 生日池會先接上，不是這條規則的範圍
    out = []
    k1 = max(pool, key=lambda k: pool[k])
    p_within = (fw + 0.5) / (fn + 1.0); share = (pool[k1] + 0.5) / (tot + 1.0)
    prec_txt = ""
    if use_precision and pools_all is not None:
        ph, pn = chain_precision(pools_all, today)
        if pn: p_first = (ph + 0.5) / (pn + 1.0); prec_txt = f"；這條規則實際回測 {ph}/{pn} 次命中（同類、開池日差 ≤5 天）"
        else: p_first = p_within * share
    else: p_first = p_within * share
    s1 = max(me + timedelta(days=gap), today + timedelta(days=1)); e1 = s1 + timedelta(days=typical_len(ctx, k1))
    out.append(dict(kind=k1, rerun=False, start=s1, end=e1, p=p_first, joint=p_first, annual=False, chain=1,
                    why=f"混池結束後 {fw}/{fn} 次在 7 天內接續新池；沒有生日池時接續的是 " + "、".join(f"{k}{v}" for k, v in fk.most_common()) + f"（所以最可能是{k1}，中位數間隔 {gap} 天）" + prec_txt))
    tr = transitions(ctx)[k1]
    cand = {k: tr.get(k, 0) for k in ("日卡", "月卡")}
    if sum(cand.values()) > 0:
        k2 = max(cand, key=lambda k: cand[k]); tt = sum(tr.values())
        s2 = e1 + timedelta(days=gap); e2 = s2 + timedelta(days=typical_len(ctx, k2))
        if anchor_start is None or e2 < anchor_start:
            p2 = (cand[k2] + 0.5) / (tt + 1.0)
            out.append(dict(kind=k2, rerun=False, start=s2, end=e2, p=p2, joint=out[0]["joint"] * p2, annual=False, chain=2,
                            why=f"若前一檔是{k1}：歷史上{k1}之後接續{'、'.join(f'{k}{v}' for k, v in tr.most_common())}，其中{k2}最多（條件把握度）；連同前一檔本身不確定，整體約 {out[0]['joint'] * p2:.2f}"))
    return out

# ---------------- 主流程 ----------------
def predict(pools, today, horizon=100, min_p=0.25):
    ctx = Ctx(pools)
    ctx.last_real_end = max((p["end"] for p in ctx.main), default=today.isoformat())
    end_day = today + timedelta(days=horizon)
    preds, skipped = [], []

    # 已確定（含進行中、已公告）的新池 = 占用檔期
    occupied = [(D(p["start"]), D(p["end"]), p["kind"], 1.0, p["name"]) for p in ctx.new if D(p["end"]) >= today]

    # 規則 A
    slots = annual_slots(ctx, today, horizon)
    prec = annual_precision(pools, today)
    regime = annual_regime(pools, today)
    accepted = []
    for s in slots:
        p, why = p_annual(s, prec, regime)
        # 規則 D：已被現實占掉（同類新池在 [目標-30, 目標+14] 內已開）或和已確定的新池重疊
        real_near = [q for q in ctx.new if q["kind"] == s["kind"] and -30 <= (D(q["start"]) - s["start"]).days <= 14 and D(q["start"]) <= today + timedelta(days=60)]
        end = s["start"] + timedelta(days=s["length"])
        clash = [o for o in occupied + [(a["start"], a["end"], a["kind"], 0, "") for a in accepted] if o[0] <= end and s["start"] <= o[1] and not (o[1] == s["start"])]
        tag = f"{s['start']:%m/%d} {s['kind']}"
        if real_near:
            skipped.append(f"{tag}：年度檔期已被 {real_near[0]['name']}（{real_near[0]['start']}）占用，不重複預測"); continue
        if clash:
            skipped.append(f"{tag}：和已確定的新池重疊，不預測"); continue
        item = dict(kind=s["kind"], rerun=False, start=s["start"], end=end, p=p, why=why, tmpl=s["tmpl"], annual=True)
        if s["kind"] in ("日卡", "月卡"):
            fake = [dict(kind=a["kind"], rerun=False, chars=a["chars"], start=a["start"].isoformat(), end=a["end"].isoformat()) for a in accepted if a["kind"] in ("日卡", "月卡") and a.get("chars")]
            ctx2 = Ctx([p_ for p_ in pools if not p_.get("pred")] + fake)
            f = next_daily_char if s["kind"] == "日卡" else next_monthly_char
            ch, pc, wc = f(ctx2, s["start"] + timedelta(days=1)); item["chars"] = ch or ""; item["why2"] = wc
        else: item["chars"] = ""
        accepted.append(item)

    # 規則 E 生成器：混池之後的接續（優先於年度檔期；兩者重疊時留把握度高的）
    anniv = [a for a in accepted if a["kind"] == "混池" and a["start"].month == 12 and a["start"].day == 31]
    anchor = min((a["start"] for a in accepted if a["kind"] == "混池"), default=None)
    for c in chain_after_mix(ctx, today, anchor, True, pools):
        clash = [a for a in accepted if a["start"] <= c["end"] and c["start"] <= a["end"] and not a["rerun"]]
        if any(a["p"] >= c["p"] for a in clash):
            skipped.append(f"{c['start']:%m/%d} 接續新{c['kind']}：和把握度更高的預測重疊，不採用"); continue
        for a in clash: accepted.remove(a); skipped.append(f"{a['start']:%m/%d} 年度檔期新{a['kind']}：和把握度更高的接續預測重疊，改採接續預測")
        if c["kind"] in ("日卡", "月卡"):
            fake = [dict(kind=a["kind"], rerun=False, chars=a["chars"], start=a["start"].isoformat(), end=a["end"].isoformat()) for a in accepted if a["kind"] in ("日卡", "月卡") and a.get("chars")]
            ctx2 = Ctx([p_ for p_ in pools if not p_.get("pred")] + fake)
            f = next_daily_char if c["kind"] == "日卡" else next_monthly_char
            ch, pc, wc = f(ctx2, c["start"] + timedelta(days=1)); c["chars"] = ch or ""; c["why2"] = wc
        else: c["chars"] = ""
        accepted.append(c)

    # 規則 B：附掛復刻
    hosts = sorted([(D(p["start"]), D(p["end"]), p["kind"], 1.0, p["name"]) for p in ctx.new if D(p["end"]) >= today and p["kind"] in NEWKINDS]
                   + [(a["start"], a["end"], a["kind"], a.get("joint", a["p"]), f"預測 {a['start']:%m/%d} {a['kind']}") for a in accepted if a["kind"] in NEWKINDS and not a["rerun"]],
                   key=lambda h: h[0])
    # 週年／春節混池本身歷史上沒有附掛復刻 -> 不當 host（資料導向：該日期的去年同檔沒有）
    def host_ok(h):
        hs, he, hk, ph, lab = h
        if hk != "混池": return True
        # 去年同檔（±3 天）的混池有沒有附掛月卡復刻？沒有就不預測
        prev = [q for q in ctx.new if q["kind"] == "混池" and abs((D(q["start"]) - yplus(hs, -1)).days) <= 3]
        if prev:
            qe = D(prev[0]["end"])
            return any(r["kind"] == "月卡" and D(prev[0]["start"]) <= D(r["start"]) and qe - timedelta(days=1) <= D(r["end"]) <= qe + timedelta(days=5) for r in ctx.reruns)
        return True
    hosts_f = [h for h in hosts if host_ok(h)]
    for t in tail_reruns(ctx, hosts_f, today, horizon, hosts):
        c = t["card"]
        accepted.append(dict(kind="月卡", rerun=True, start=t["start"], end=t["end"], p=t["p"], chars=c["chars"], name=c["name"], annual=False,
                             why=f"附掛在「{t['host']}」收尾：{t['hk']}新池近期 {t['k']}/{t['n']} 檔有月卡復刻；照原池順序輪到「{c['name']}」，"
                                 f"原池→復刻間隔 {t['lag']} 天（歷史 {t['lag_range'][0]}–{t['lag_range'][1]}）" + ("" if t["lag_ok"] else "，超出歷史範圍")))

    # 規則 E：混池剛結束 -> 第一檔新池通常在 7 天內接上
    fw, fn, fk = follow_stats(ctx)
    cur_mix = [p for p in ctx.new if p["kind"] == "混池" and D(p["end"]) >= today]
    if cur_mix and fn:
        me = D(cur_mix[-1]["end"])
        firsts = sorted([a for a in accepted if not a["rerun"] and a["kind"] in NEWKINDS and a["start"] > me], key=lambda a: a["start"])
        if firsts:
            f0 = firsts[0]
            gap = (f0["start"] - me).days
            if gap > 7:
                f0["early"] = me + timedelta(days=2)
                kd = "、".join(f"{k}{v}" for k, v in fk.most_common())
                f0["why2"] = (f0.get("why2", "") + f"｜混池結束後 7 天內接續新池的比例 {fw}/{fn}，這檔距離 {gap} 天偏晚，實際可能提早到 {f0['early']:%m/%d} 起"
                              f"（歷史上接續的非生日新池：{kd}）").lstrip("｜")

    # 命名與輸出
    for a in accepted:
        if a["p"] < min_p:
            skipped.append(f"{a['start']:%m/%d} {'復刻 ' if a['rerun'] else ''}{a['kind']}{a.get('name','')}：把握度 {bucket(a['p'])}（{a['p']:.2f}）低於門檻，只列在報告"); continue
        if a["rerun"]: name = a["name"]
        elif a["kind"] == "混池" and a["start"].month == 12 and a["start"].day == 31: name = f"{CN[min(a['start'].year - 2024, 7)]}週年混池"
        elif a["kind"] == "混池": name = "新混池"
        elif a["kind"] == "日卡": name = "新日卡"
        else: name = "新月卡"
        span = (D(a["tmpl"]["end"]) - D(a["tmpl"]["start"])).days if a.get("tmpl") else 7
        jitter = 3 if a["annual"] else 4
        lo, hi = a["start"] - timedelta(days=jitter), a["start"] + timedelta(days=jitter)
        if a.get("early"): lo = min(lo, a["early"])
        note = f"預測｜把握度{bucket(a['p'])}（{a['p']:.2f}）｜{a['why']}" + (f"｜{a['why2']}" if a.get("why2") else "") + "｜非官方排期"
        rule = "B" if a["rerun"] else ("E1" if a.get("chain") == 1 else "E2" if a.get("chain") == 2 else "A")
        preds.append(dict(name=name, kind=a["kind"], rerun=a["rerun"], chars=a["chars"], start=a["start"].isoformat(), end=a["end"].isoformat(),
                          pv=None, pvTime=None, pred=True, conf=bucket(a["p"]), p=round(a["p"], 2), rule=rule, predFrom=lo.isoformat(), predTo=hi.isoformat(),
                          note=note, id=f"pred-{a['start'].isoformat()}-{'r' if a['rerun'] else 'n'}-{a['kind']}"))

    # 已知但未定日期
    have = {p["name"] for p in ctx.real}
    for k in KNOWN_UNDATED:
        w0, w1 = D(k["window"][0]), D(k["window"][1])
        arrived = None
        if k["name"] in have:
            arrived = next(p for p in ctx.real if p["name"] == k["name"])
        else:
            for s_ in ctx.story:
                if not (w0 - timedelta(days=3) <= D(s_["start"]) <= w1 + timedelta(days=3)): continue
                if s_["chars"] == k["chars"]: arrived = s_; break
                if s_["chars"] == "" and arrived is None: arrived = s_      # 沒抓到角色：先當作它（見下方說明）
        if arrived is not None:
            why = "" if arrived["chars"] == k["chars"] or arrived["name"] == k["name"] else "（該活動沒標角色，若不是這個事件，請把 pools.json 裡它的 chars 改成實際角色，預測會自動回來）"
            skipped.append(f"{k['name']}：官方已公布『{arrived['name']}』（{arrived['start']}～{arrived['end']}），預測退場{why}")
            continue
        if w1 <= today: continue
        mid = w0 + (w1 - w0) // 2                                   # 區間中點（固定，避免每天都變）
        if mid <= today:                                            # 中點已過、區間還沒結束：固定放在區間尾段，也不會每天變
            mid = max(today + timedelta(days=1), w1 - timedelta(days=3))
        gaps = sum(1 for s_ in ctx.story if any(q["kind"] == "混池" and D(q["start"]) <= D(s_["end"]) and D(s_["start"]) <= D(q["end"]) for q in ctx.new))
        note = (f"預測｜日期未定｜{k['source']}｜日期取 {w0:%m/%d}–{w1:%m/%d} 區間中點，實際可能在區間內任一天｜"
                f"歷史 {len(ctx.story)} 個主線分線有 {gaps} 個和新混池重疊（免費五星，不占主檔）｜非官方排期")
        preds.append(dict(name=k["name"], kind=k["kind"], rerun=False, chars=k["chars"], start=mid.isoformat(), end=(mid + timedelta(days=k["length"])).isoformat(),
                          pv=None, pvTime=None, pred=True, conf="日期未定", p=None, rule="K", predFrom=w0.isoformat(), predTo=w1.isoformat(), note=note,
                          id=f"pred-{k['name']}-劇情"))
    preds.sort(key=lambda p: (p["start"], p["rerun"]))
    return preds, skipped

def report(preds, skipped, today):
    L = ["## 卡池預測（規則式，非官方排期）", "", f"- 資料基準日 {today}；預測 {len(preds)} 檔", "",
         "| 預計開池 | 範圍 | 池 | 把握度 | 依據 |", "|---|---|---|---|---|"]
    for p in preds:
        nm = ("↻" if p["rerun"] else "") + p["name"] + (f"（{p['chars']}）" if p["chars"] else "")
        L.append(f"| {p['start'][5:]}～{p['end'][5:]} | {p['predFrom'][5:]}～{p['predTo'][5:]} | {nm} | {p['conf']}{'' if p['p'] is None else ' ' + format(p['p'], '.2f')} | {p['note'].split('｜',2)[-1][:150]} |")
    if not preds: L.append("| （沒有） | | | | |")
    if skipped: L += ["", "### 未納入或略過", ""] + [f"- {s}" for s in skipped]
    L += ["", "> 把握度是依歷史規律與回測估的，不是機率保證；官方通常只提前約 3 天公布。", ""]
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pools", default="pools.json"); ap.add_argument("--today"); ap.add_argument("--horizon", type=int, default=100)
    ap.add_argument("--min-p", type=float, default=0.25); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    today = D(a.today) if a.today else datetime.now(TW).date()
    data = json.load(open(a.pools, encoding="utf-8"))
    pools = data["pools"]
    preds, skipped = predict(pools, today, a.horizon, a.min_p)
    md = report(preds, skipped, today); print(md)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp and not a.dry: open(sp, "a", encoding="utf-8").write(md)
    old_preds = sorted([p for p in pools if p.get("pred")], key=lambda p: p["id"])
    if json.dumps(old_preds, ensure_ascii=False, sort_keys=True) == json.dumps(sorted(preds, key=lambda p: p["id"]), ensure_ascii=False, sort_keys=True):
        print("預測無變更"); return
    if a.dry: print("（--dry：不寫檔）"); return
    data["pools"] = sorted([p for p in pools if not p.get("pred")] + preds, key=lambda p: (p["start"], p["rerun"], p["name"]))
    data["updated"] = today.isoformat()
    json.dump(data, open(a.pools, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已更新 {a.pools} 的預測（{len(preds)} 檔）")

if __name__ == "__main__":
    try: main()
    except Exception as ex:
        print(f"[預測失敗] {type(ex).__name__}: {ex}"); sys.exit(0)
