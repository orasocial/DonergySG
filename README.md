"""Donergy Daily builder. Runs in GitHub Actions; no secrets needed or embedded.
Each source is fetched independently (timeout + retries). Failures never stop the build:
previously fetched stories are kept and the failure is recorded for the status panel."""
import json, hashlib, re, html, os, time, socket, difflib, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# ===== EDIT ME =====
CFG = {"title": "Donergy Daily", "subtitle": "Fresh news. Better content ideas.", "keep_days": 30, "per_feed": 10, "timeout": 12, "retries": 2}
CATS = ["Near Millenia", "Singapore F&B", "Halal Dining", "Promotions & Inspiration", "Social & Marketing", "Local Events", "Dining Trends"]
OVERSEAS = "Overseas ideas"
TRENDS = "Trends & Memes"  # shown in its own row, never mixed into the main story grid
X = lambda p: re.compile(p, re.I)
TRENDRE = X(r"trend|viral|meme|tiktok|challenge|reels?|craze|hashtag")
FOOD = X(r"\b(restaurants?|caf[eé]s?|kebabs?|kebap|d[oö]ner|turkish|mediterranean|halal|hawker|dining|menu|chef|f&b|food|meals?|lunch|dinner|brunch|buffet|delivery|grabfood|foodpanda|deliveroo|1-for-1|set meals?|dessert|bakery|burgers?|chicken|steak|noodles?|rice|coffee|bubble tea|ice cream|banh mi|bánh mì)\b")
PROMO = X(r"promo\w*|deals?|1-for-1|discount|\bsale\b|voucher|\boffers?\b|free |\$\d|s\$\d|11\.11|12\.12")
MKT = X(r"tiktok|instagram|reels?|\bmeta\b|facebook|youtube|google (maps|business|reviews)|social media|influencer|algorithm|loyalty|campaign|marketing|viral|hashtag|shorts")
EVENT = X(r"event|festival|concert|exhibition|countdown|bazaar|national day|christmas|new year|grand prix|\bf1\b|expo|pop-up|carnival|parade|conference|summit|tourism|visitors?")
HALAL = X(r"halal|muis|muslim|ramadan|hari raya|\beid\b|buka puasa|turkish|t[uü]rk")
TREND = X(r"trend|viral|new (restaurant|cafe|opening)|opens?\b|opening|launch|popular|queue")
LOC = X(r"millenia|suntec|promenade|marina bay|marina square|raffles city|citylink|esplanade|gardens by the bay|ritz-carlton|mandarin oriental|pan pacific|conrad|fairmont|swiss[oô]tel|bayfront|shenton|raffles place|downtown|\bcbd\b")
SG = X(r"\b(singapore|singaporean|sg|s'pore|raffles|orchard|sentosa|jurong|tampines|bugis|geylang|hawker|changi|kallang|marina|suntec|millenia|ion orchard|eastpoint|toa payoh|woodlands|bedok)\b")
SGPUB = {"sethlui", "honeycombers", "the straits times", "cna", "mothership", "today", "8days", "little day out", "danamic", "eatbook", "time out singapore", "asiaone", "the smart local", "channelnewsasia", "r/singaporeeats", "straitstimes.com"}
JUNK = X(r"limousine|chauffeur|market (report|size|share|analysis|forecast)|cagr|manufactur|additive|glass|bottle production|industrial|investment|\bstocks?\b|press ?release|presswire|openpr|payouts?|cdc vouchers?|gst voucher|\bbto\b|\bhdb\b|\bcpf\b|crypto|ipo\b|earnings|acquires?|acquisition|\bfactory\b|supply chain|ingredients? (market|supplier)|packaging|conclave")
LOCALJUNK = X(r"giveaway|gives? away|food drive|fundrais|charity|council|school|church|laundromat|obituary|opening day|police|crash|\bfire\b|raffle")
PLAT = X(r"\b(tiktok|instagram|reels?|facebook|meta|youtube shorts|google (maps|business|reviews|search)|whatsapp|threads)\b.*\b(test|tests|launch\w*|updates?|rolls? out|new feature|adds?|introduc\w+|algorithm|ads?)\b")
INSPIRE = X(r"campaign|viral|tiktok|reels?|loyalty|rebrand|marketing|social media|strategy|collab|limited[- ]edition|pop-up|menu innovation|launch|promotion|customer experience|retention")
TRUSTED = {"SETHLUI", "Honeycombers SG", "Social Media Today"}
# ===================
SGT, UTC = timezone(timedelta(hours=8)), timezone.utc
NOW = datetime.now(SGT); EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
UA = "Mozilla/5.0 (compatible; DonergyDaily/3.0; +https://orasocial.github.io/DonergySG/)"
FIX = os.environ.get("DD_FIXTURES"); FAIL = {s for s in os.environ.get("DD_FAIL", "").split("|") if s}
slug = lambda s: re.sub(r"\W+", "_", s.lower()).strip("_")

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

def reason(e):
    if isinstance(e, urllib.error.HTTPError): return f"HTTP {e.code}" + (" (blocked or rate-limited)" if e.code in (403, 429) else "")
    if isinstance(e, (socket.timeout, TimeoutError)) or "timed out" in str(e): return "Timed out"
    if isinstance(e, urllib.error.URLError): return "Network error: " + str(e.reason)[:60]
    if isinstance(e, ET.ParseError): return "Response was not a valid feed"
    return f"{type(e).__name__}: {str(e)[:60]}"

def get(url, name):
    if name in FAIL: raise urllib.error.HTTPError(url, 503, "simulated failure", None, None)
    if FIX:
        p = os.path.join(FIX, slug(name) + ".xml")
        if not os.path.exists(p): raise urllib.error.URLError("fixture missing")
        return open(p, "rb").read()
    if "news.google.com" in url: url += "&hl=en-SG&gl=SG&ceid=SG:en"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=CFG["timeout"]) as r: return r.read()

def fetch(f):
    """Try main URL, then optional alternates; retry only transient errors. Returns (root, error_reason)."""
    err = "Unknown"
    for url in [f["url"]] + f.get("alt", []):
        for n in range(CFG["retries"] + 1):
            try: return ET.fromstring(get(url, f["name"])), None
            except Exception as e:
                err = reason(e)
                transient = isinstance(e, (socket.timeout, TimeoutError, urllib.error.URLError)) or (isinstance(e, urllib.error.HTTPError) and (e.code >= 500 or e.code == 429))
                if not transient or FIX: break
                time.sleep(1.5 * (n + 1))
    return None, err

def parse(root, f):
    out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"): continue
        t, l = find(it, "title"), find(it, "link")
        if t is None or l is None: continue
        title = html.unescape((t.text or "").strip()); link = l.attrib.get("href") or (l.text or "").strip()
        if not link.startswith("http"): continue
        pub = ""; s = find(it, "source")
        if s is not None and s.text: pub = s.text.strip()
        m = re.match(r"^(.*\S)\s+[-–|]\s+([^-–|]{2,40})$", title) if "news.google.com" in f["url"] else None
        if m: title, pub = m.group(1), pub or m.group(2)
        d = find(it, "pubDate", "published", "updated"); img = ""
        if f.get("images", True):
            for e in it.iter():
                if e.tag.split("}")[-1] in ("thumbnail", "content", "enclosure") and e.attrib.get("url", "").startswith("http") and "image" in (e.attrib.get("type", "image") + e.attrib.get("medium", "image")):
                    img = e.attrib["url"]; break
        c = find(it, "description", "summary", "content")
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(c.text or ""))).strip() if c is not None else ""
        if not img and f.get("images", True) and c is not None:
            mm = re.search(r'<img[^>]+src="(https?://[^"]+)"', html.unescape(c.text or "")); img = mm.group(1) if mm else ""
        ex = ""
        if len(body) > 60 and difflib.SequenceMatcher(None, body.lower()[:len(title) + 40], title.lower()).ratio() < .8 and not body.lower().startswith(title.lower()[:40]):
            ex = body[:180].rsplit(" ", 1)[0] + ("…" if len(body) > 180 else "")
        out.append({"t": title, "l": link, "d": pdate(d.text if d is not None else None).isoformat(), "s": f["name"], "p": pub, "i": img, "e": ex, "f": NOW.isoformat(), "sgq": bool(f.get("sg")), "m": bool(f.get("meme")), "tr": bool(f.get("trend"))})
    return out

def norm_url(u):
    p = urlsplit(u); host = p.netloc.lower().removeprefix("www.")
    q = [] if "news.google.com" in host else [(k, v) for k, v in parse_qsl(p.query) if not re.match(r"utm_|fbclid|gclid|ref$|source$|oc$|cmpid|ito$", k, re.I)]
    return urlunsplit(("https", host, p.path.rstrip("/") or "/", urlencode(q), ""))

STOP = set("a an and the of to in on at for with from by is are be as it its this that new more up out amp s".split())
def toks(t): return {w for w in re.findall(r"[a-z0-9$.]+", t.lower().replace("’", "'")) if w not in STOP and len(w) > 1}
def similar(a, b):
    ta, tb = toks(a), toks(b)
    if not ta or not tb: return False
    inter = ta & tb
    return difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() >= .85 or (len(inter) >= 4 and len(inter) / min(len(ta), len(tb)) >= .65)

def classify(a, feedcat=""):
    """Return enriched article, or None if not relevant to Donergy."""
    txt = a["t"] + " " + a.get("e", ""); pub = (a.get("p") or a["s"]).lower()
    if JUNK.search(a["t"]): return None
    if a.get("m") or a.get("tr"):  # trends & memes: separate row, loose filter (must look trend/meme-like, no local giveaways)
        if LOCALJUNK.search(a["t"]) or (a.get("tr") and not a.get("m") and not TRENDRE.search(a["t"]) and "knowyourmeme" not in a["l"]): return None
        age = (NOW - datetime.fromisoformat(a["d"])).total_seconds() / 3600
        a = dict(a); a.update(c=[TRENDS], reg="tr", k=round(4 + max(0, 20 - age / 12), 1), w="Trend or meme format you could adapt. Check it fits the brand before posting.", x=""); return a
    food, promo, mkt, ev, hal, loc = (r.search(txt) for r in (FOOD, PROMO, MKT, EVENT, HALAL, LOC))
    sg = bool(SG.search(txt)) or pub in SGPUB or (a.get("sgq") and not LOCALJUNK.search(txt))
    age = max(0, (NOW - datetime.fromisoformat(a["d"])).total_seconds() / 3600)
    c = set()
    if sg:
        topical = food or mkt or (ev and (loc or SG.search(a["t"])))
        if not topical or (LOCALJUNK.search(txt) and not loc and not hal): return None
        if loc: c.add("Near Millenia")
        if food: c.add("Singapore F&B")
        if hal: c.add("Halal Dining")
        if promo and food: c.add("Promotions & Inspiration")
        if mkt: c.add("Social & Marketing")
        if ev: c.add("Local Events")
        if TREND.search(txt) and food: c.add("Dining Trends")
        sc = 30 + (35 if loc else 0) + (25 if hal else 0) + (15 if promo and food else 0) + (12 if mkt else 0) + (10 if ev else 0) + (5 if a["s"] in TRUSTED else 0)
    elif PLAT.search(a["t"]) and not LOCALJUNK.search(txt):  # global social-platform updates matter wherever they are published
        c = {"Social & Marketing"}; sc = 28
    else:  # overseas: only genuinely useful restaurant-marketing examples, never local giveaways/drives
        if LOCALJUNK.search(txt) or not INSPIRE.search(txt) or not (food or mkt): return None
        c = {OVERSEAS}; sc = 8 + (12 if mkt else 0) + (5 if a["s"] in TRUSTED else 0)
    a = dict(a); a["c"] = [k for k in CATS + [OVERSEAS] if k in c] or ["Singapore F&B"]
    a["reg"] = "sg" if sg else ("gl" if c == {"Social & Marketing"} else "os"); a["k"] = round(sc + max(0, 20 - age / 12), 1)
    a["w"], a["x"] = insight(a, txt, bool(loc), bool(hal), bool(promo and food), bool(mkt), bool(ev), bool(sg))
    return a

def insight(a, txt, loc, hal, promo, mkt, ev, sg):
    """Rule-based (no paid API). 'w' = why it matters; 'x' = optional idea. Both are derived from headline keywords only."""
    w = x = ""
    if loc: w = "Mentions the Marina Bay / Millenia Walk area, so it could affect footfall or competition near Donergy."
    elif hal: w = "Halal and Turkish dining stories show what Muslim-friendly and Turkish-curious diners are looking for."
    elif promo and sg: w = "A nearby brand is running a deal, which can shift where office workers and families choose to eat."
    elif mkt: w = "Platform or marketing changes affect how far Donergy's posts reach."
    elif ev and sg: w = "Events can bring extra crowds, or empty the offices, around Marina Bay."
    elif a["reg"] == "os": w = "Overseas example of a restaurant marketing approach, not specific to Singapore."
    elif sg: w = "Singapore F&B news that shows what diners and competitors are doing."
    if re.search(r"1-for-1|deal|promo|sale|11\.11|12\.12|voucher", txt, re.I) and sg: x = "Instead of matching the discount, try a weekday döner + drink lunch set for Millenia Walk office workers, posted by 10am."
    elif re.search(r"ramadan|hari raya|\beid\b|buka puasa", txt, re.I): x = "Plan a buka puasa or Raya family set, and share the menu 2 to 3 weeks ahead."
    elif hal: x = "Show halal status clearly on Google Business, Instagram bio and delivery listings."
    elif re.search(r"tiktok|instagram|reels?|shorts|google (maps|business)|meta", txt, re.I): x = "Test this on one post: a 15-second clip of the döner being carved."
    elif loc and ev: x = "Offer a pre- or post-event dinner set for families and tourists, with a QR code for nearby hotels."
    elif re.search(r"pop-up|queue|viral|trend", txt, re.I) and sg: x = "Make one shareable dish or photo spot, then ask guests to tag Donergy."
    return w, x

def cluster(arts):
    arts = sorted(arts, key=lambda a: a["d"]); groups = []
    for a in arts:
        for g in groups:
            if any(norm_url(a["l"]) == norm_url(b["l"]) or similar(a["t"], b["t"]) for b in g): g.append(a); break
        else: groups.append([a])
    out = []
    for g in groups:
        orig = lambda a: (("news.google.com" not in a["l"]) * 4 + bool(a.get("i")) * 2 + (a["s"] in TRUSTED))
        main = dict(max(g, key=lambda a: (orig(a), a["k"]))); seen = {norm_url(main["l"])}; rel = []
        for b in g:
            if norm_url(b["l"]) in seen: continue
            seen.add(norm_url(b["l"])); rel.append({"s": b.get("p") or b["s"], "l": b["l"], "t": b["t"]})
        main["rel"] = rel[:4]; main["k"] = max(a["k"] for a in g) + (3 if rel else 0); out.append(main)
    return out

def load_prev():
    try:
        m = re.search(r'<script id="data" type="application/json">(.*?)</script>', open("docs/index.html", encoding="utf-8").read(), re.S)
        return json.loads(m.group(1).replace("<\\/", "</"))
    except Exception: return {"articles": [], "updated": None, "sources": []}

def main():
    prev = load_prev(); feeds = json.load(open("feeds.json")); status, new = [], []
    names = {f["name"] for fl in feeds.values() for f in fl}
    old_ok = {s["n"]: s.get("lastOk") for s in prev.get("sources", [])}
    for cat, lst in feeds.items():
        for f in lst:
            root, err = fetch(f); st = {"n": f["name"], "ok": root is not None, "why": err or "", "lastOk": NOW.isoformat() if root is not None else (old_ok.get(f["name"]) or prev.get("updated"))}
            if root is not None:
                try: items = parse(root, f); st["items"] = len(items); new += items[:CFG["per_feed"]]
                except Exception as e: st.update(ok=False, why=reason(e), lastOk=old_ok.get(f["name"]) or prev.get("updated"))
            print(("ok   " if st["ok"] else "FAIL ") + f["name"] + (": " + st["why"] if st["why"] else "")); status.append(st)
    failed = {s["n"] for s in status if not s["ok"]}
    pool = {}
    for a in prev.get("articles", []):  # cached; re-checked against the current rules every run
        a = {**a}; a["s"] = a["s"].replace("News: ", "GNews: ") if a["s"].replace("News: ", "GNews: ") in names else a["s"]
        a.setdefault("p", ""); a.setdefault("e", ""); a.setdefault("sgq", a.get("sg", False)); pool[norm_url(a["l"])] = a
    for a in new: pool[norm_url(a["l"])] = a
    cut = NOW - timedelta(days=CFG["keep_days"]); keep = []
    for a in pool.values():
        if datetime.fromisoformat(a["d"]) <= cut: continue
        b = classify(a)
        if b: b["cached"] = a["s"] in failed; b["hl"] = not b.get("e"); keep.append(b)
    arts = sorted(cluster(keep), key=lambda a: a["k"], reverse=True)
    for a in arts:
        a.pop("sg", None)  # keep sgq/f/m: needed to re-classify cached stories on the next run
    recent = [a for a in arts if a["reg"] == "sg" and datetime.fromisoformat(a["d"]) > NOW - timedelta(days=14)]
    near = [a for a in recent if "Near Millenia" in a["c"] or "Halal Dining" in a["c"]]
    feat = (near or recent or [None])[0]
    ok = sum(s["ok"] for s in status)
    data = {"cfg": CFG, "updated": NOW.isoformat() if ok else prev.get("updated"), "ok": ok, "failed": len(failed), "sources": status,
            "feat": feat["l"] if feat else None, "featLabel": "Relevant to Donergy" if near else "Top Singapore story",
            "cats": CATS, "overseas": OVERSEAS, "trends": TRENDS, "articles": arts, "occasions": json.load(open("holidays.json"))}
    sig = hashlib.sha1(json.dumps([[a["l"], a["cached"]] for a in arts] + [[x["n"], x["ok"]] for x in status]).encode()).hexdigest(); data["sig"] = sig
    pu = prev.get("updated")
    if prev.get("sig") == sig and pu and (NOW - datetime.fromisoformat(pu)).total_seconds() < 6 * 3600 and not os.environ.get("DD_OUT"):
        print("no new stories; page left unchanged (avoids hourly commit noise)"); return
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = os.environ.get("DD_OUT", "docs/index.html"); os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w", encoding="utf-8").write(open("template.html", encoding="utf-8").read().replace("__DATA__", blob).replace("__TITLE__", html.escape(CFG["title"])))
    print("done:", len(arts), "stories,", ok, "sources ok,", len(failed), "failed")

if __name__ == "__main__":
    try: main()
    except Exception as e:  # never replace the live page with a broken one
        print("BUILD ABORTED, previous page kept:", repr(e)); raise SystemExit(1)
