#!/usr/bin/env python3
"""
微博官號模組（唯讀核對 + 產生月曆用的公告資料）
  1) 向官方微博（UID 7484247626）取最近貼文（匿名；可選 WEIBO_COOKIE）
  2) 輸出 weibo.json：把「卡池／PV／更新維護／活動」類貼文整理成公告清單，月曆網頁的「微博公告」區塊讀這個檔
  3) 把貼文裡的「活動時間」和 pools.json 比對，結果寫在 GitHub Actions 的 Job Summary（不會改日曆資料）
注意：微博是『大陸服』公告，台服日期可能不同。被擋或失敗時不會讓排程變紅，且保留上次取得的公告。

用法：python scripts/weibo_check.py [--pools pools.json] [--feed weibo.json] [--uid 7484247626] [--pages 2] [--mock weibo.json] [--today YYYY-MM-DD]
環境變數：WEIBO_COOKIE（選填）、WEIBO_BASE（測試用）、GITHUB_STEP_SUMMARY（Actions 自動提供）
"""
import json, os, re, sys, time, argparse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta, date

TW = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")

# ---------- 簡 -> 繁（內建字表；若環境有 opencc 就優先用） ----------
_PAIRS = ("后後许許愿願复復开開启啟时時间間动動线線费費钻鑽获獲领領题題为為与與长長画畫终終揽攬边邊缘緣银銀当當陨隕万萬绝絕爱愛猫貓"
          "双雙叠疊坠墜热熱烟煙处處倾傾脉脈饲飼养養龙龍涌湧尽盡头頭触觸讯訊号號窃竊缱繾绻綣无無来來轻輕续續岁歲占佔彻徹昼晝联聯杀殺"
          "节節剧劇场場储儲乐樂观觀习習礼禮经經验驗纪紀级級称稱让讓专專达達论論书書设設报報实實览覽创創圆圓团團问問门門关關际際过過还還"
          "运運进進选選连連迟遲点點红紅绿綠蓝藍气氣风風云雲伞傘汤湯汉漢汇匯滨濱滚滾灯燈灵靈炽熾烁爍状狀献獻独獨现現电電异異疗療盘盤码碼"
          "离離种種积積笔筆签簽简簡类類纯純纸紙练練组組细細织織绍紹结結给給络絡统統继繼维維缓緩编編缩縮网網罗羅聪聰脑腦舰艦艺藝荣榮药藥"
          "虑慮补補装裝规規视視计計订訂认認讲講访訪证證评評识識诉訴词詞译譯试試话話该該详詳语語误誤说說请請读讀课課调調谈談谢謝贝貝财財"
          "责責贤賢败敗货貨购購贴貼资資赏賞赠贈赛賽车車轨軌轮輪软軟载載较較辑輯输輸迁遷这這远遠适適递遞邮郵释釋针針钟鐘钢鋼钥鑰钱錢铃鈴"
          "链鏈锁鎖错錯键鍵镜鏡闪閃闭閉闲閒阅閱阵陣阳陽阶階陆陸陈陳队隊随隨隐隱难難雾霧静靜页頁顶頂项項顺順须須顾顧预預频頻颜顏飞飛饭飯"
          "饮飲饰飾馆館驱驅骑騎鱼魚鸟鳥鸡雞鹤鶴黄黃齐齊齿齒龄齡恋戀范範"
          "将將戏戲游遊对對个個们們会會发發内內么麼见見觉覺应應术術记記马馬总總务務员員厅廳县縣师師带帶帮幫帅帥干幹广廣庆慶库庫样樣极極构構标標机機权權条條杂雜检檢欢歡没沒济濟满滿渐漸温溫湿濕灭滅牵牽猎獵环環监監盖蓋着著础礎稳穩竞競粮糧紧緊约約绑綁综綜罚罰胜勝营營虽雖袭襲讨討训訓议議诗詩询詢诚誠谁誰谊誼谜謎谱譜贡貢负負贩販贯貫贵貴买買贺賀赖賴赶趕转轉辅輔辆輛辈輩辉輝迈邁违違遗遺邻鄰郑鄭酱醬里裡钉釘钮鈕铁鐵铜銅销銷锐銳锦錦镇鎮闯闖阴陰险險隶隸顿頓颁頒颗顆额額飘飄驻駐驾駕骗騙鸣鳴黑黑恶惡烦煩灾災灿燦炼煉牺犧爷爺脚腳筹籌吗嗎吨噸响響哗嘩圣聖块塊坏壞声聲够夠夺奪奋奮奖獎妇婦妈媽学學宁寧宠寵审審宫宮宽寬导導尔爾尝嘗层層属屬岛島币幣帘簾并並亚亞产產亲親仅僅从從仓倉仪儀众眾优優伤傷伦倫体體价價侠俠债債偿償兑兌兰蘭兴興兽獸册冊写寫军軍农農冲衝决決况況冻凍净淨减減几幾凤鳳击擊划劃刘劉则則刚剛删刪别別剑劍劝勸办辦励勵劳勞势勢勋勳区區医醫华華协協单單卖賣卢盧卫衛却卻厂廠历歷压壓厌厭参參变變叙敘叶葉叹嘆吓嚇吕呂听聽吴吳咏詠咙嚨唤喚喷噴嘱囑园園围圍国國图圖坚堅坛壇墙牆壮壯壳殼壶壺备備")
TBL = {ord(_PAIRS[i]): _PAIRS[i + 1] for i in range(0, len(_PAIRS), 2)}
try:
    from opencc import OpenCC
    _CC = OpenCC("s2t")
except Exception:
    _CC = None

def s2t(t):
    if _CC is not None:
        try: return _CC.convert(t)
        except Exception: pass
    return (t or "").translate(TBL)

def norm(s): return re.sub(r"[\W_]+", "", s2t(s or ""))

# ---------- 活動時間解析 ----------
DATE_RE = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:更新後|(?:上午|凌晨)?\s*\d{1,2}[:：]\d{2})\s*[~～\-–—至到]+\s*"
                     r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:上午|凌晨)?\s*\d{1,2}[:：]\d{2}")
START_ONLY = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:上午|凌晨)?\s*\d{1,2}[:：]\d{2}\s*起")

def periods(text, pub):
    """pub 為 date。回傳 [(開始, 結束或 None)]；只寫開始日時，結束為 None。"""
    out, used = [], []
    for m in DATE_RE.finditer(text):
        y1, m1, d1, y2, m2, d2 = m.groups()
        sy = int(y1) if y1 else pub.year
        s = date(sy, int(m1), int(d1))
        if not y1 and (s - pub).days < -60: s = date(sy + 1, int(m1), int(d1))
        ey = int(y2) if y2 else s.year
        e = date(ey, int(m2), int(d2))
        if e < s and not y2: e = date(ey + 1, int(m2), int(d2))
        out.append((s, e)); used.append(m.span())
    for m in START_ONLY.finditer(text):
        if any(a <= m.start() < b for a, b in used): continue
        y1, m1, d1 = m.groups()
        sy = int(y1) if y1 else pub.year
        s = date(sy, int(m1), int(d1))
        if not y1 and (s - pub).days < -60: s = date(sy + 1, int(m1), int(d1))
        out.append((s, None))
    return out

# ---------- 抓取與判定 ----------
def get(url, cookie=""):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://m.weibo.cn/", "X-Requested-With": "XMLHttpRequest", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, (e.read() or b"").decode("utf-8", "replace")

def classify(status, final_url, body):
    if status in (403, 418, 429, 432): return "BLOCKED", f"HTTP {status}（被拒絕）"
    if "passport.weibo" in final_url or "visitor" in final_url: return "VISITOR_REDIRECT", "被導向訪客驗證頁"
    if re.search(r"验证码|驗證碼|captcha|安全验证", body[:3000], re.I): return "CAPTCHA", "頁面要求驗證碼"
    try: j = json.loads(body)
    except Exception: return "NOT_JSON", f"HTTP {status}，回傳不是預期格式"
    cards = (j.get("data") or {}).get("cards") or []
    if j.get("ok") == 1 and cards: return "OK", f"{len(cards)} 張卡片"
    return "EMPTY", "回傳空內容（匿名請求常見的軟性封鎖）"

def strip_html(t):
    t = re.sub(r"<br\s*/?>", "\n", t or "")
    return re.sub(r"&nbsp;", " ", re.sub(r"<[^>]+>", "", t)).strip()

def parse_created(s):
    try: return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").astimezone(TW)
    except Exception: return None

def posts_from(j):
    out = []
    for c in (j.get("data") or {}).get("cards") or []:
        m = c.get("mblog")
        if not m: continue
        out.append(dict(id=str(m.get("id") or m.get("mid") or ""), created=parse_created(m.get("created_at", "")),
                        created_raw=m.get("created_at", ""), text=s2t(strip_html(m.get("text") or m.get("raw_text") or ""))))
    return out

# ---------- 公告資料（給月曆網頁用） ----------
def tag_of(t):
    if re.search(r"思念|許願|復刻|限定|卡池", t): return "卡池"
    if "PV" in t.upper(): return "PV"
    if re.search(r"更新|維護|停服|版本|公告|補償|測試", t): return "更新維護"
    if re.search(r"活動|生日|聯動|主線|分線|免費|簽到", t): return "活動"
    return None

def to_feed_post(q):
    tg = tag_of(q["text"])
    if not tg or not q["id"]: return None
    pub = q["created"] or datetime.now(TW)
    pers = [dict(start=s.isoformat(), end=(e.isoformat() if e else None)) for s, e in periods(q["text"], pub.date())]
    txt = re.sub(r"#[^#\s]{1,30}#", "", q["text"])
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > 140: txt = txt[:140] + "…"
    return dict(id=q["id"], time=pub.strftime("%Y-%m-%d %H:%M"), tag=tg, text=txt,
                url=f"https://m.weibo.cn/detail/{q['id']}", periods=pers)

def save_feed(path, posts, verdict, why, uid):
    """合併新舊公告；內容沒變就不寫檔（避免每次排程都產生提交）。回傳是否有寫入。"""
    try: old = json.load(open(path, encoding="utf-8"))
    except Exception: old = {}
    byid = {p["id"]: p for p in old.get("posts", []) if p.get("id")}
    if verdict == "OK":
        for q in posts:
            fp = to_feed_post(q)
            if fp: byid[fp["id"]] = fp
    cutoff = (datetime.now(TW) - timedelta(days=180)).strftime("%Y-%m-%d %H:%M")
    lst = sorted((p for p in byid.values() if p["time"] >= cutoff), key=lambda p: p["time"], reverse=True)[:150]
    new = dict(uid=uid, verdict=verdict, why=("" if verdict == "OK" else why), posts=lst)
    if {k: old.get(k) for k in new} == new: return False
    new["updated"] = datetime.now(TW).isoformat(timespec="minutes")
    json.dump(new, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return True

# ---------- 與 pools.json 核對（只寫入 Job Summary） ----------
def same_pool(p, text):
    if norm(p["name"]) and norm(p["name"]) in norm(text): return True
    ch = p.get("chars") or ""
    if ch and "／" not in ch and ch in text:
        is_re = ("復刻" in text) or ("往期" in text)
        if bool(p.get("rerun")) == is_re and (p["kind"] != "生日" or "生日" in text): return True
    if p["kind"] == "混池" and re.search(r"任選\s*[3三]|選\s*[3三]\s*張|混池", text) and bool(p.get("rerun")) == ("復刻" in text): return True
    return False

def crosscheck(pools, posts, today):
    items = []
    for p in pools:
        if p.get("pred") or p.get("kind") == "劇情": continue
        ps, pe = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        if not (today - timedelta(days=14) <= ps <= today + timedelta(days=21)): continue
        res = dict(name=p["name"], rerun=bool(p.get("rerun")), kind=p["kind"], cal=f"{p['start']}～{p['end']}", status="no_post", wb="", url="")
        best = None
        for q in posts:
            pub = (q["created"] or datetime.now(TW)).date()
            if not same_pool(p, q["text"]): continue
            for s, e in periods(q["text"], pub):
                gap = abs((s - ps).days)
                if gap <= 3 and (best is None or gap < best[0]): best = (gap, s, e, q)
        if best:
            gap, s, e, q = best
            res["wb"] = f"{s.isoformat()}～{e.isoformat() if e else '（未寫結束）'}"
            res["url"] = f"https://m.weibo.cn/detail/{q['id']}" if q["id"] else ""
            if gap != 0: res["status"] = "date_diff"
            elif e is None: res["status"] = "start_only"
            elif e == pe: res["status"] = "confirmed"
            else: res["status"] = "date_diff"
        items.append(res)
    unmatched, seen = [], set()
    for q in posts:
        pub = (q["created"] or datetime.now(TW)).date()
        for s, e in periods(q["text"], pub):
            if s < today - timedelta(days=3) or s > today + timedelta(days=60): continue
            if any(not p.get("pred") and abs((date.fromisoformat(p["start"]) - s).days) <= 3 and same_pool(p, q["text"]) for p in pools): continue
            key = (s, e, q["id"])
            if key in seen: continue
            seen.add(key)
            unmatched.append(dict(period=f"{s.isoformat()}～{e.isoformat() if e else '（未寫結束）'}",
                                  post_time=q["created"].strftime("%m/%d %H:%M") if q["created"] else "",
                                  text=q["text"][:80].replace("\n", " "), url=f"https://m.weibo.cn/detail/{q['id']}" if q["id"] else ""))
    return items, unmatched

ICON = {"confirmed": "✅ 一致", "date_diff": "⚠️ 日期不同", "start_only": "ℹ️ 微博只寫開始日", "no_post": "— 微博沒找到"}

def summary_md(verdict, why, nposts, items, unmatched):
    L = ["## 微博官號核對", "", f"- 抓取結果：**{verdict}**（{why}）；取得貼文 {nposts} 則",
         "- ⚠️ 微博是**大陸服**公告，台服日期可能不同；本表只做交叉核對，不會自動改日曆。", ""]
    if verdict != "OK":
        return "\n".join(L + ["本次沒有取得微博資料，因此沒有核對。YouTube 更新不受影響。", ""])
    L += ["### 日曆上的池 vs 微博", "", "| 池 | 日曆 | 微博 | 結果 |", "|---|---|---|---|"]
    for r in items:
        wb = f"[{r['wb']}]({r['url']})" if r["url"] else (r["wb"] or "—")
        L.append(f"| {('↻' if r['rerun'] else '')}{r['name']} | {r['cal']} | {wb} | {ICON[r['status']]} |")
    if not items: L.append("| （近期沒有需要核對的池） | | | |")
    L += ["", "### 微博上有、日曆上沒有的活動（可能是新卡池、聯動或官方公告）", ""]
    if unmatched:
        L += ["| 期間 | 貼文時間 | 內容 |", "|---|---|---|"]
        for u in unmatched: L.append(f"| {u['period']} | {u['post_time']} | " + (f"[{u['text']}]({u['url']})" if u["url"] else u["text"]) + " |")
    else: L.append("沒有。")
    return "\n".join(L) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pools", default="pools.json"); ap.add_argument("--feed", default="weibo.json")
    ap.add_argument("--uid", default="7484247626"); ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--mock"); ap.add_argument("--today")
    a = ap.parse_args()
    today = date.fromisoformat(a.today) if a.today else datetime.now(TW).date()
    base = os.environ.get("WEIBO_BASE", "https://m.weibo.cn").rstrip("/")
    cookie = os.environ.get("WEIBO_COOKIE", "").strip()
    print(f"[微博] UID {a.uid}；{'使用 Cookie' if cookie else '匿名請求'}；最多 {a.pages} 頁；日期基準 {today}")
    posts, verdict, why = [], "EMPTY", ""
    for page in range(1, a.pages + 1):
        if a.mock: body, status, final = open(a.mock, encoding="utf-8").read(), 200, "mock"
        else:
            qs = f"type=uid&value={a.uid}&containerid=107603{a.uid}" + (f"&page={page}" if page > 1 else "")
            t0 = time.time(); status, final, body = get(f"{base}/api/container/getIndex?{qs}", cookie)
            print(f"[微博] 第 {page} 頁：HTTP {status}，{time.time()-t0:.1f}s，{len(body)} bytes")
        v, w = classify(status, final, body)
        print(f"[微博] 第 {page} 頁判定：{v}（{w}）")
        if v != "OK":
            if page == 1: verdict, why = v, w
            break
        posts += posts_from(json.loads(body)); verdict, why = "OK", w
        if a.mock: break
        time.sleep(2.5)
    print(f"[微博] 取得貼文 {len(posts)} 則")
    items, unmatched = [], []
    if verdict == "OK" and os.path.exists(a.pools):
        pools = json.load(open(a.pools, encoding="utf-8")).get("pools", [])
        items, unmatched = crosscheck(pools, posts, today)
        for r in items: print(f"[核對] {('↻' if r['rerun'] else '')}{r['name']} | 日曆 {r['cal']} | 微博 {r['wb'] or '-'} | {ICON[r['status']]}")
        for u in unmatched: print(f"[新活動?] {u['period']} | {u['post_time']} | {u['text']}")
    wrote = save_feed(a.feed, posts, verdict, why, a.uid)
    print(f"[公告] {a.feed}：{'已更新' if wrote else '無變更'}")
    md = summary_md(verdict, why, len(posts), items, unmatched)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        with open(sp, "a", encoding="utf-8") as f: f.write(md)
    json.dump(dict(checked=datetime.now(TW).isoformat(timespec="seconds"), verdict=verdict, why=why, posts=len(posts),
                   items=items, unmatched=unmatched), open("weibo_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[結論] {verdict}")

if __name__ == "__main__":
    try: main()
    except Exception as ex:
        print(f"[結論] ERROR（{type(ex).__name__}: {ex}）")
    sys.exit(0)
