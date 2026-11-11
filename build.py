import json, re, html, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ===== EDIT ME: branding, categories, relevance rules =====
CFG = {"title": "Donergy Daily", "subtitle": "Fresh news. Better content ideas.", "keep_days": 30, "per_feed": 8}
CAT_MAP = {"Latest F&B": "Singapore F&B", "Promos & Deals": "Promotions & Inspiration", "Turkish & Halal": "Halal Dining",
           "Social & Trends": "Social & Marketing", "Memes": "Promotions & Inspiration"}
EXTRA = {"Local Events": r"event|festival|concert|exhibition|countdown|bazaar|national day|christmas|new year|grand prix|marina bay|expo|pop-up|carnival|parade",
         "Dining Trends": r"trend|viral|new (restaurant|cafe|opening)|opens|opening|menu|launch|chef|popular"}
RESTO = r"\b(restaurants?|cafes?|café|kebabs?|kebap|döner|doner|turkish|halal|hawker|dining|menu|chef|f&b|food|meals?|lunch|dinner|brunch|buffet|delivery|grabfood|foodpanda|deliveroo|tiktok|reels?|instagram|viral|promo\w*|deals?|1-for-1|discounts?|ramadan|eid|hari raya|mall|millenia|suntec|marina bay|promenade|dessert|ice cream)\b"
JUNK = r"limousine|chauffeur|market (report|size|share|to 20|analysis|forecast)|cagr|manufactur|additive|glass jar|industrial|investment|\bstocks?\b|press ?release|presswire|openpr"
NEAR = r"millenia|suntec|promenade|marina bay|turkish|kebab|döner|doner|halal|raffles|esplanade"
SG_WORDS = r"\b(singapore|singaporean|sg|raffles|orchard|sentosa|jurong|tampines|bugis|geylang|hawker|changi)\b"
TRUSTED = {"SETHLUI", "Eater", "r/SingaporeEats"}
# ==========================================================
SGT, UTC = timezone(timedelta(hours=8)), timezone.utc
NOW = datetime.now(SGT)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
UA = "Mozilla/5.0 (compatible; fnb-feed/2.0)"

def pdate(s):
    if not s: return EPOCH
    try: d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return EPOCH
    return d if d.tzinfo else d.replace(tzinfo=UTC)

def find(el, *names):
    for n in names:
        for e in el.iter():
            if e.tag.split("}")[-1] == n and (e.text or e.attrib): return e

def fetch(url):
    if "news.google.com" in url: url += "&hl=en-SG&gl=SG&ceid=SG:en"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20) as r:
        return ET.fromstring(r.read())

def relevant(title, src, cat):
    if re.search(JUNK, title, re.I): return False
    return cat == "Memes" or src in TRUSTED or bool(re.search(RESTO, title, re.I))

def parse(root, f, cat):
    out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"): continue
        t, l = find(it, "title"), find(it, "link")
        if t is None or l is None: continue
        title = (t.text or "").strip(); link = l.attrib.get("href") or (l.text or "").strip()
        if not link.startswith("http") or not relevant(title, f["name"], cat): continue
        d = find(it, "pubDate", "published", "updated"); img = ""
        for e in it.iter():
            if e.tag.split("}")[-1] in ("thumbnail", "content", "enclosure") and e.attrib.get("url", "").startswith("http"):
                img = e.attrib["url"]; break
        if not img:
            c = find(it, "content", "description", "summary")
            m = re.search(r'<img[^>]+src="([^"]+)"', html.unescape(c.text or "")) if c is not None else None
            img = m.group(1) if m and m.group(1).startswith("http") else ""
        cats = {CAT_MAP.get(cat, cat)} | {k for k, v in EXTRA.items() if re.search(v, title, re.I)}
        sg = bool(f.get("sg")) or bool(re.search(SG_WORDS, title, re.I))
        out.append({"t": title, "l": link, "d": pdate(d.text if d is not None else None).isoformat(),
                    "s": f["name"].replace("GNews: ", "News: "), "i": img, "sg": sg, "c": sorted(cats)})
    return out

def key(a):
    age = max(0, (NOW - datetime.fromisoformat(a["d"])).total_seconds() / 3600)
    return round(max(0, 40 - age / 6) + (60 if a["sg"] else 0), 1)

# previous data (kept if a refresh fails)
prev = {"articles": [], "updated": None}
try:
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', open("docs/index.html", encoding="utf-8").read(), re.S)
    if m: prev = json.loads(m.group(1).replace("<\\/", "</"))
except Exception: pass

new, ok, failed = {}, 0, 0
for cat, lst in json.load(open("feeds.json")).items():
    for f in lst:
        try:
            for a in parse(fetch(f["url"]), f, cat)[:CFG["per_feed"]]: new.setdefault(a["l"], a)
            ok += 1
        except Exception as e:
            failed += 1; print(f"skip {f['name']}: {e}")

cut = NOW - timedelta(days=CFG["keep_days"])
merged = {a["l"]: a for a in prev.get("articles", []) if relevant(a["t"], a["s"], "x") or "Promotions & Inspiration" in a["c"]}
merged.update(new)
arts = [a for a in merged.values() if datetime.fromisoformat(a["d"]) > cut]
seen, uniq = set(), []
for a in sorted(arts, key=lambda a: a["d"], reverse=True):
    k = re.sub(r"\W+", "", a["t"].lower())[:60]
    if k not in seen: seen.add(k); uniq.append(a)
for a in uniq: a["k"] = key(a)

recent = [a for a in uniq if datetime.fromisoformat(a["d"]) > NOW - timedelta(days=14)]
near = [a for a in recent if re.search(NEAR, a["t"], re.I)]
feat = (near[0]["l"], "Relevant to Donergy") if near else ((uniq[0]["l"], "Latest story") if uniq else (None, ""))

occ, today = [], NOW.date()
for h in json.load(open("holidays.json")):
    try:
        if h.get("date"): d = datetime.fromisoformat(h["date"]).date()
        elif h.get("md"):
            mo, dd = map(int, h["md"].split("-")); d = today.replace(month=mo, day=dd)
            if d < today: d = d.replace(year=today.year + 1)
        else: continue
    except Exception: continue
    if d >= today: occ.append({"n": h["name"], "d": d.isoformat(), "g": h["tag"], "e": bool(h.get("est")), "s": h.get("src", "")})
occ.sort(key=lambda o: o["d"])

data = {"cfg": CFG, "updated": NOW.isoformat() if ok else prev.get("updated"), "failed": failed, "ok": ok,
        "feat": feat[0], "featLabel": feat[1], "cats": ["Singapore F&B", "Social & Marketing", "Local Events", "Dining Trends", "Halal Dining", "Promotions & Inspiration"],
        "articles": uniq, "occasions": occ[:10]}
blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
open("docs/index.html", "w", encoding="utf-8").write(open("template.html", encoding="utf-8").read().replace("__DATA__", blob).replace("__TITLE__", html.escape(CFG["title"])))
print("done", len(uniq), "articles")
