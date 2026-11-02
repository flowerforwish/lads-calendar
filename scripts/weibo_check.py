#!/usr/bin/env python3
"""
微博官號模組 v3（多來源備援；唯讀核對 + 產生月曆「微博公告」區塊用的 weibo.json）
來源依序嘗試，取得第一個有貼文的就停：
  A  m.weibo.cn 手機版介面（匿名）
  B  先「暖機」取得 Cookie 再呼叫同一個介面（有些匿名請求被放行要先有 Cookie）
  C  新浪新聞的官方微博鏡像頁 https://www.sina.cn/media/7484247626（HTML，解析『日期 時間 來自』格式）
每個來源的結果（含回傳內容前 160 字）都會印在 log 與 Job Summary，方便判斷是被擋、空回應還是格式變了。
被擋或失敗時不會讓排程變紅，且保留上次取得的公告。

用法：python scripts/weibo_check.py [--pools pools.json] [--feed weibo.json] [--uid 7484247626] [--pages 2] [--mock FILE] [--mock-html FILE] [--today YYYY-MM-DD]
環境變數：WEIBO_COOKIE（選填）、WEIBO_BASE / SINA_BASE（測試用）、GITHUB_STEP_SUMMARY（Actions 自動提供）
"""
import json, os, re, sys, time, hashlib, argparse, urllib.request, urllib.error, http.cookiejar
from datetime import datetime, timezone, timedelta, date

TW = timezone(timedelta(hours=8))
UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")
UA_D = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36")

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
          "将將戏戲游遊对對个個们們会會发發内內么麼见見觉覺应應术術记記马馬总總务務员員厅廳县縣师師带帶帮幫帅帥干幹广廣庆慶库庫样樣极極构構标標机機权權条條杂雜"
          "检檢欢歡没沒济濟满滿渐漸温溫湿濕灭滅牵牽猎獵环環监監盖蓋着著础礎稳穩竞競粮糧紧緊约約绑綁综綜罚罰胜勝营營虽雖袭襲讨討训訓议議诗詩询詢诚誠谁誰谊誼谜謎谱譜"
          "贡貢负負贩販贯貫贵貴买買贺賀赖賴赶趕转轉辅輔辆輛辈輩辉輝迈邁违違遗遺邻鄰郑鄭酱醬里裡钉釘钮鈕铁鐵铜銅销銷锐銳锦錦镇鎮闯闖阴陰险險隶隸顿頓颁頒颗顆额額飘飄驻駐驾駕"
          "骗騙鸣鳴恶惡烦煩灾災灿燦炼煉牺犧爷爺脚腳筹籌吗嗎吨噸响響哗嘩圣聖块塊坏壞声聲够夠夺奪奋奮奖獎妇婦妈媽学學宁寧宠寵审審宫宮宽寬导導尔爾尝嘗层層属屬岛島币幣"
          "帘簾并並亚亞产產亲親仅僅从從仓倉仪儀众眾优優伤傷伦倫体體价價侠俠债債偿償兑兌兰蘭兴興兽獸册冊写寫军軍农農冲衝决決况況冻凍净淨减減几幾凤鳳击擊划劃刘劉则則刚剛"
          "删刪别別剑劍劝勸办辦励勵劳勞势勢勋勳区區医醫华華协協单單卖賣卢盧卫衛却卻厂廠历歷压壓厌厭参參变變叙敘叶葉叹嘆吓嚇吕呂听聽吴吳咏詠咙嚨唤喚喷噴嘱囑园園围圍国國图圖"
          "坚堅坛壇墙牆壮壯壳殼壶壺备備毕畢迹跡")
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

# ---------- 共用 ----------
def strip_html(t):
    t = re.sub(r"<br\s*/?>", "\n", t or "")
    return re.sub(r"&nbsp;", " ", re.sub(r"<[^>]+>", "", t)).strip()

def snippet(body, n=160):
    return re.sub(r"\s+", " ", (body or "")[:n * 3]).strip()[:n]

def synth_id(pub, text):
    return "s" + hashlib.sha1(f"{pub}|{text[:60]}".encode("utf-8")).hexdigest()[:11]

# ---------- 圖片（只記網址，不下載、不存檔；網頁端再載入縮圖） ----------
SIZE_SEGS = {"large", "mw2000", "mw1024", "mw690", "mw480", "orj1080", "orj960", "orj480", "orj360", "bmiddle", "thumbnail",
             "thumb150", "thumb180", "thumb300", "small", "woriginal", "original", "wap180", "wap360", "wap720", "middle", "square"}
MAX_IMGS = 6
IMG_MARK = re.compile("\x01IMG:([^\x02]+)\x02")
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
ATTR = re.compile(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
BAD_IMG = re.compile(r"crop\.|//face\.|/face/|emoticon|emoji|/icon|icon[_-]|/logo|avatar|/default|h5\.sinaimg\.cn/upload|img\.t\.sinajs\.cn|/(?:orj|thumb|wap)50/|/orj30/|\.gif(?:\?|$)", re.I)
GOOD_HOST = re.compile(r"^https?://[^/]*(?:sinaimg\.(?:cn|com)|sina\.cn|sina\.com\.cn)/", re.I)

def img_pair(url):
    """回傳 {'t': 縮圖網址, 'l': 大圖網址}；weibo 圖床（…sinaimg.cn/<尺寸>/<檔名>）可換尺寸，其他網址 t=l。"""
    u = (url or "").strip().replace("&amp;", "&")
    if u.startswith("//"): u = "https:" + u
    u = re.sub(r"^http://", "https://", u)
    m = re.match(r"^(https://[^/]*sinaimg\.(?:cn|com)/)([^/]+)/(.+)$", u, re.I)
    if m and m.group(2).lower() in SIZE_SEGS:
        return {"t": f"{m.group(1)}orj360/{m.group(3)}", "l": f"{m.group(1)}large/{m.group(3)}"}
    return {"t": u, "l": u}

def uniq_pairs(urls):
    out, seen = [], set()
    for u in urls:
        p = img_pair(u)
        key = re.sub(r"^https://[^/]+/[^/]+/", "", p["l"])
        if not p["t"].startswith("https://") or key in seen: continue
        seen.add(key); out.append(p)
        if len(out) >= MAX_IMGS: break
    return out

def mark_images(html):
    """把貼文圖片的 <img> 換成不可見記號（\x01IMG:網址\x02），其餘 <img>（頭像、表情、圖示）直接丟掉。"""
    def one(m):
        tag = m.group(0)
        at = {k.lower(): (a or b) for k, a, b in ATTR.findall(tag)}
        src = at.get("data-src") or at.get("data-original") or at.get("data-lazy-src") or at.get("src") or ""
        if not src or src.startswith("data:"): return ""
        if src.startswith("//"): src = "https:" + src
        if not GOOD_HOST.match(src) or BAD_IMG.search(src): return ""
        if re.search(r"avatar|face|icon|logo|emoji|head|portrait", (at.get("class", "") + " " + at.get("alt", "")), re.I): return ""
        for k in ("width", "height"):
            v = re.sub(r"\D", "", at.get(k, ""))
            if v and int(v) < 100: return ""
        return f"\x01IMG:{src}\x02"
    return IMG_TAG.sub(one, html)

class Result:
    def __init__(self, name): self.name, self.verdict, self.why, self.posts, self.hint = name, "SKIP", "", [], ""

# ---------- 來源 A / B：m.weibo.cn JSON 介面 ----------
def opener_with_jar():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar

def http_get(op, url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, (e.read() or b"").decode("utf-8", "replace")

def classify_json(status, final_url, body):
    if status in (403, 418, 429, 432): return "BLOCKED", f"HTTP {status}（被拒絕）"
    if "passport.weibo" in final_url or "visitor" in final_url: return "VISITOR_REDIRECT", "被導向訪客驗證頁"
    if re.search(r"验证码|驗證碼|captcha|安全验证", body[:3000], re.I): return "CAPTCHA", "頁面要求驗證碼"
    try: j = json.loads(body)
    except Exception: return "NOT_JSON", f"HTTP {status}，回傳不是預期格式"
    cards = (j.get("data") or {}).get("cards") or []
    if j.get("ok") == 1 and cards: return "OK", f"{len(cards)} 張卡片"
    return "EMPTY", f"回傳空內容（ok={j.get('ok')}）"

def parse_created(s):
    try: return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").astimezone(TW)
    except Exception: return None

def posts_from_json(j):
    out = []
    for c in (j.get("data") or {}).get("cards") or []:
        m = c.get("mblog")
        if not m: continue
        urls = []
        for pc in (m.get("pics") or []):
            if isinstance(pc, dict):
                urls.append(((pc.get("large") or {}).get("url")) or pc.get("url") or (f"https://wx1.sinaimg.cn/large/{pc['pid']}.jpg" if pc.get("pid") else ""))
        if not urls:
            pp = ((m.get("page_info") or {}).get("page_pic") or {}).get("url")      # 影片貼文的封面
            if pp: urls.append(pp)
        out.append(dict(id=str(m.get("id") or m.get("mid") or ""), created=parse_created(m.get("created_at", "")),
                        text=s2t(strip_html(m.get("text") or m.get("raw_text") or "")),
                        url=f"https://m.weibo.cn/detail/{m.get('id') or m.get('mid')}", imgs=uniq_pairs([u for u in urls if u])))
    return out

def fetch_api(name, base, uid, pages, cookie, warm, mock_body=None):
    r = Result(name)
    hdr = {"User-Agent": UA_M, "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-CN,zh;q=0.9",
           "Referer": "https://m.weibo.cn/", "X-Requested-With": "XMLHttpRequest", "MWeibo-Pwa": "1"}
    if cookie: hdr["Cookie"] = cookie
    op, jar = opener_with_jar()
    if warm and mock_body is None:
        try:
            st, fu, b = http_get(op, base + "/", {**hdr, "Accept": "text/html"}, 20)
            r.hint = f"暖機 HTTP {st}，取得 Cookie：{', '.join(c.name for c in jar) or '無'}"
            print(f"[{name}] {r.hint}")
        except Exception as ex:
            r.hint = f"暖機失敗 {type(ex).__name__}"
    for page in range(1, pages + 1):
        if mock_body is not None: status, final, body = 200, "mock", mock_body
        else:
            qs = f"type=uid&value={uid}&containerid=107603{uid}" + (f"&page={page}" if page > 1 else "")
            t0 = time.time()
            try: status, final, body = http_get(op, f"{base}/api/container/getIndex?{qs}", hdr)
            except Exception as ex:
                r.verdict, r.why = "ERROR", f"{type(ex).__name__}: {ex}"; print(f"[{name}] {r.verdict}：{r.why}"); return r
            print(f"[{name}] 第 {page} 頁：HTTP {status}，{time.time()-t0:.1f}s，{len(body)} bytes；內容開頭：{snippet(body)!r}")
        v, w = classify_json(status, final, body)
        if page == 1: r.verdict, r.why = v, w
        if v != "OK": break
        r.posts += posts_from_json(json.loads(body))
        if mock_body is not None: break
        time.sleep(2.5)
    print(f"[{name}] 判定：{r.verdict}（{r.why}）；貼文 {len(r.posts)} 則")
    return r

# ---------- 來源 C：新浪新聞鏡像（HTML，解析『YYYY-MM-DD HH:MM 來自』） ----------
SINA_SPLIT = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})\s*来自\s*[^\s#]{0,12}")
TAIL_NUMS = re.compile(r"(?:\s+[\d.]+万?){2,}\s*$")

def parse_sina_html(html):
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<noscript[\s\S]*?</noscript>", " ", html or "")
    text = mark_images(text)
    text = strip_html(re.sub(r"</(p|div|li|h\d)>", "\n", text))
    text = re.sub(r"[ \t\u200b]+", " ", text)
    parts = SINA_SPLIT.split(text)
    # parts = [前置, 時間1, 內文1, 時間2, 內文2, ...]
    out = []
    for i in range(1, len(parts) - 1, 2):
        ts, body = parts[i], parts[i + 1]
        imgs = uniq_pairs(IMG_MARK.findall(body))
        body = re.sub(r"[ \t\u200b]+", " ", IMG_MARK.sub("", body))      # 先拿掉圖片記號，文字與先前版本完全相同（貼文 id 不變）
        body = re.sub(r"^\s*(?:微博网页版|恋与深空超话|[^\s]{0,8}超话)\s*", "", body)
        body = re.sub(r"^\s*(?:已编辑|置顶)\s*", "", body)
        body = re.sub(r"\s*《?云·恋与深空》?点击即玩[:：]?\s*(?:https?://\S+|O?\s*网页链接)?", " ", body)
        body = TAIL_NUMS.sub("", re.sub(r"\s*展开全文.*$", "", body, flags=re.S)).strip()
        body = re.sub(r"\s*(?:恋与深空\s*)?$", "", body).strip()
        if not body: continue
        try: created = datetime.strptime(ts.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=TW)
        except Exception: continue
        t = s2t(body)
        out.append(dict(id=synth_id(created.isoformat(), t), created=created, text=t, url="https://weibo.com/u/7484247626", imgs=imgs))
    return out

def fetch_sina(base, uid, cookie, mock_html=None):
    r = Result("主來源 新浪鏡像")
    if mock_html is not None: status, final, body = 200, "mock", mock_html
    else:
        hdr = {"User-Agent": UA_D, "Accept": "text/html,*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
        op, _ = opener_with_jar()
        try: status, final, body = http_get(op, f"{base}/media/{uid}", hdr)
        except Exception as ex:
            r.verdict, r.why = "ERROR", f"{type(ex).__name__}: {ex}"; print(f"[{r.name}] {r.verdict}：{r.why}"); return r
        print(f"[{r.name}] HTTP {status}，{len(body)} bytes；內容開頭：{snippet(body)!r}")
    if status in (403, 418, 429): r.verdict, r.why = "BLOCKED", f"HTTP {status}（被拒絕）"; return r
    posts = parse_sina_html(body)
    n_img, n_pic = sum(1 for q in posts if q.get("imgs")), sum(len(q.get("imgs") or []) for q in posts)
    r.hint = f"含圖貼文 {n_img} 則、圖片 {n_pic} 張"
    print(f"[{r.name}] 圖片：{r.hint}")
    if posts and n_pic == 0:
        srcs = [(dict((k.lower(), a or b) for k, a, b in ATTR.findall(t)).get("data-src") or dict((k.lower(), a or b) for k, a, b in ATTR.findall(t)).get("src") or "")
                for t in IMG_TAG.findall(body)]
        print(f"[圖片診斷] 頁面共有 <img> {len(srcs)} 個，沒有符合『貼文圖片』條件的；前 6 個 src：")
        for u in srcs[:6]: print("   ", u[:140])
    if posts: r.verdict, r.why, r.posts = "OK", f"解析出 {len(posts)} 則", posts
    else: r.verdict, r.why = "EMPTY", f"HTTP {status}，沒有解析出任何『日期 時間 來自』貼文（頁面可能由 JS 產生或格式改變）"
    print(f"[{r.name}] 判定：{r.verdict}（{r.why}）")
    return r

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
    txt = re.sub(r"#[^#]{1,30}#", "", q["text"]); txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > 140: txt = txt[:140] + "…"
    fp = dict(id=q["id"], time=pub.strftime("%Y-%m-%d %H:%M"), tag=tg, text=txt, url=q.get("url", ""), periods=pers)
    if q.get("imgs"): fp["img"] = q["imgs"][:MAX_IMGS]
    return fp

def save_feed(path, posts, verdict, why, uid, source):
    try: old = json.load(open(path, encoding="utf-8"))
    except Exception: old = {}
    byid = {p["id"]: p for p in old.get("posts", []) if p.get("id")}
    if verdict == "OK":
        for q in posts:
            fp = to_feed_post(q)
            if fp: byid[fp["id"]] = fp
    cutoff = (datetime.now(TW) - timedelta(days=180)).strftime("%Y-%m-%d %H:%M")
    lst = sorted((p for p in byid.values() if p["time"] >= cutoff), key=lambda p: p["time"], reverse=True)[:150]
    new = dict(uid=uid, verdict=verdict, why=("" if verdict == "OK" else why), source=(source if verdict == "OK" else old.get("source", "")), posts=lst)
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
            res["wb"] = f"{s.isoformat()}～{e.isoformat() if e else '（未寫結束）'}"; res["url"] = q.get("url", "")
            res["status"] = "date_diff" if gap != 0 else ("start_only" if e is None else ("confirmed" if e == pe else "date_diff"))
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
                                  text=q["text"][:80].replace("\n", " "), url=q.get("url", "")))
    return items, unmatched

ICON = {"confirmed": "✅ 一致", "date_diff": "⚠️ 日期不同", "start_only": "ℹ️ 微博只寫開始日", "no_post": "— 微博沒找到"}

def summary_md(results, used, nposts, items, unmatched, newest_txt="—", img_txt=""):
    L = ["## 微博官號核對", "", "### 各來源嘗試結果", "", "| 來源 | 結果 | 說明 |", "|---|---|---|"]
    if len(results) == 1 and results[0].verdict == "OK": L.append("| （備援 1、2 未使用：主來源已成功，沒有額外請求微博） | | |")
    for r in results: L.append(f"| {r.name} | **{r.verdict}** | {r.why or '—'}{('；' + r.hint) if r.hint else ''} |")
    L += ["", f"- 本次採用：**{used or '無（全部失敗）'}**；取得貼文 {nposts} 則；最新一則發布於 {newest_txt}；{img_txt}",
          "- ⚠️ 微博是**大陸服**公告，台服日期可能不同；本表只做交叉核對，不會自動改日曆。", ""]
    if not used:
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
    ap.add_argument("--mock"); ap.add_argument("--mock-html"); ap.add_argument("--today")
    a = ap.parse_args()
    today = date.fromisoformat(a.today) if a.today else datetime.now(TW).date()
    wbase = os.environ.get("WEIBO_BASE", "https://m.weibo.cn").rstrip("/")
    sbase = os.environ.get("SINA_BASE", "https://www.sina.cn").rstrip("/")
    cookie = os.environ.get("WEIBO_COOKIE", "").strip()
    print(f"[微博] UID {a.uid}；{'使用 Cookie' if cookie else '匿名請求'}；日期基準 {today}")
    mock_json = open(a.mock, encoding="utf-8").read() if a.mock else None
    mock_html = open(a.mock_html, encoding="utf-8").read() if a.mock_html else None
    results, used, posts = [], "", []
    # 順序：主來源（新浪鏡像）成功就不再碰微博；失敗才依序用備援 1、備援 2
    sina = lambda: fetch_sina(sbase, a.uid, cookie, mock_html)
    api_a = lambda: fetch_api("備援1 手機介面", wbase, a.uid, a.pages, cookie, False, mock_json)
    api_b = lambda: fetch_api("備援2 暖機後介面", wbase, a.uid, a.pages, cookie, True, mock_json)
    plan = [sina, api_a, api_b]
    if mock_json is not None and mock_html is None: plan = [api_a]      # 只給 JSON 模擬資料：測試手機介面解析
    if mock_html is not None and mock_json is None: plan = [sina]       # 只給 HTML 模擬資料：測試鏡像解析
    for f in plan:
        r = f(); results.append(r)
        if r.verdict == "OK" and r.posts: used, posts = r.name, r.posts; break
    verdict = "OK" if used else (results[0].verdict if results else "EMPTY")
    why = "" if used else "; ".join(f"{r.name}:{r.verdict}" for r in results)
    newest = max((q["created"] for q in posts if q.get("created")), default=None)
    newest_txt = newest.strftime("%Y-%m-%d %H:%M") if newest else "—"
    n_img = sum(1 for q in posts if q.get("imgs")); n_pic = sum(len(q.get("imgs") or []) for q in posts)
    print(f"[圖片] 含圖貼文 {n_img} 則、圖片 {n_pic} 張")
    print(f"[微博] 貼文 {len(posts)} 則；最新一則 {newest_txt}；採用來源：{used or '無'}")
    items, unmatched = [], []
    if used and os.path.exists(a.pools):
        pools = json.load(open(a.pools, encoding="utf-8")).get("pools", [])
        items, unmatched = crosscheck(pools, posts, today)
        for r in items: print(f"[核對] {('↻' if r['rerun'] else '')}{r['name']} | 日曆 {r['cal']} | 微博 {r['wb'] or '-'} | {ICON[r['status']]}")
        for u in unmatched: print(f"[新活動?] {u['period']} | {u['post_time']} | {u['text']}")
    wrote = save_feed(a.feed, posts, verdict, why, a.uid, used)
    print(f"[公告] {a.feed}：{'已更新' if wrote else '無變更'}")
    md = summary_md(results, used, len(posts), items, unmatched, newest_txt, f"含圖貼文 {n_img} 則、圖片 {n_pic} 張")
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        with open(sp, "a", encoding="utf-8") as f: f.write(md)
    json.dump(dict(checked=datetime.now(TW).isoformat(timespec="seconds"), used=used, verdict=verdict,
                   sources=[dict(name=r.name, verdict=r.verdict, why=r.why) for r in results], posts=len(posts),
                   items=items, unmatched=unmatched, with_images=n_img, images=n_pic), open("weibo_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[結論] {verdict}（{used or '無來源可用'}）")

if __name__ == "__main__":
    try: main()
    except Exception as ex:
        print(f"[結論] ERROR（{type(ex).__name__}: {ex}）")
    sys.exit(0)
