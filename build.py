import json, html, re, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

SGT = timezone(timedelta(hours=8))
UTC = timezone.utc
NOW = datetime.now(SGT)
PER_FEED = 6
UA = "Mozilla/5.0 (compatible; fnb-feed/1.0)"
SG_WORDS = re.compile(r"\b(singapore|singaporean|sg|raffles|orchard|sentosa|jurong|tampines|bugis|geylang|kampong|hawker|changi)\b", re.I)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

def parse_date(s):
    if not s: return EPOCH
    try: d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return EPOCH
    return d if d.tzinfo else d.replace(tzinfo=UTC)

def find(el, *names):
    for n in names:
        for e in el.iter():
            if e.tag.split("}")[-1] == n and (e.text or e.attrib):
                return e
    return None

def fetch(url):
    if "news.google.com" in url: url += "&hl=en-SG&gl=SG&ceid=SG:en"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return ET.fromstring(r.read())

def score(i):
    age_h = max(0, (NOW - i["date"]).total_seconds() / 3600)
    s = max(0, 40 - age_h / 6)
    if i["sg"] or SG_WORDS.search(i["title"]): s += 60
    if i["sg"] and SG_WORDS.search(i["title"]): s += 20
    return s

def items(root, f):
    out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"): continue
        t, l = find(it, "title"), find(it, "link")
        d = find(it, "pubDate", "published", "updated")
        if t is None or l is None: continue
        link = l.attrib.get("href") or (l.text or "").strip()
        img = ""
        for e in it.iter():
            if e.tag.split("}")[-1] in ("thumbnail", "content", "enclosure") and e.attrib.get("url", "").startswith("http"):
                img = e.attrib["url"]; break
        if not img:
            c = find(it, "content", "description", "summary")
            m = re.search(r'<img[^>]+src="([^"]+)"', html.unescape(c.text or "")) if c is not None else None
            if m: img = m.group(1)
        i = {"title": (t.text or "").strip(), "link": link, "date": parse_date(d.text if d is not None else None),
             "source": f["name"].replace("GNews: ", "News · "), "img": img, "sg": bool(f.get("sg"))}
        i["score"] = score(i)
        out.append(i)
    return sorted(out, key=lambda x: x["date"], reverse=True)[:PER_FEED]

sections = {}
for cat, lst in json.load(open("feeds.json")).items():
    seen, rows = set(), []
    for f in lst:
        try:
            for i in items(fetch(f["url"]), f):
                k = re.sub(r"\W+", "", i["title"].lower())[:60]
                if i["link"] not in seen and k not in seen:
                    seen.add(i["link"]); seen.add(k); rows.append(i)
        except Exception as e:
            print(f"skip {f['name']}: {e}")
    sections[cat] = sorted(rows, key=lambda x: x["score"], reverse=True)

def when(d):
    return d.astimezone(SGT).strftime("%b %d") if d.year > 1970 else ""

def card(i, big=False):
    img = f'<img src="{html.escape(i["img"])}" loading="lazy" alt="">' if i["img"] else ""
    badge = '<span class="sg">SG</span>' if (i["sg"] or SG_WORDS.search(i["title"])) else ""
    return (f'<a class="card{" big" if big else ""}" href="{html.escape(i["link"])}" target="_blank" rel="noopener">{img}'
            f'<div class="tx">{badge}<b>{html.escape(i["title"])}</b><small>{html.escape(i["source"])} · {when(i["date"])}</small></div></a>')

def holidays():
    today = NOW.date(); rows = []
    for h in json.load(open("holidays.json")):
        if "date" in h: d = datetime.fromisoformat(h["date"]).date()
        else:
            m, dd = map(int, h["md"].split("-")); d = today.replace(month=m, day=dd)
            if d < today: d = d.replace(year=today.year + 1)
        if d >= today: rows.append((d, h))
    rows.sort(key=lambda x: x[0])
    li = "".join(f'<li><span class="dl">{(d - today).days}<i>days</i></span><div><b>{html.escape(h["name"])}</b>'
                 f'<small>{h["tag"]} · {d.strftime("%b %d, %Y")}</small></div></li>' for d, h in rows[:8])
    return f'<div class="box"><h2>Upcoming Holidays</h2><ul class="hol">{li}</ul></div>'

pool = [i for c, r in sections.items() if c != "Memes" for i in r]
top, seen = [], set()
for i in sorted(pool, key=lambda x: x["score"], reverse=True):
    if i["link"] not in seen and len(top) < 6: seen.add(i["link"]); top.append(i)

def sec(c):
    r = sections.get(c, [])
    return f'<section><h2>{html.escape(c)}</h2><div class="grid">{"".join(card(i) for i in r) or "<p class=empty>Nothing yet, check back later.</p>"}</div></section>'

main = "".join(sec(c) for c in sections if c != "Memes")
memes = f'<div class="box"><h2>Memes</h2><div class="stack">{"".join(card(i) for i in sections.get("Memes", [])) or "<p class=empty>No memes loaded.</p>"}</div></div>'
stamp = NOW.strftime("%a, %b %d %Y · %I:%M %p") + " SGT"

CSS = """
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#fff;color:#111}
header{background:#000;color:#fff;border-bottom:6px solid #d90429}.wrap{max-width:1180px;margin:0 auto;padding:0 18px}
header .wrap{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;padding:18px}
.logo{font-size:28px;font-weight:900;letter-spacing:1px}.logo em{color:#d90429;font-style:normal}
header small{color:#bbb}
h2{font-size:15px;text-transform:uppercase;letter-spacing:1.5px;margin:28px 0 12px;padding-left:10px;border-left:5px solid #d90429}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.top .grid{grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}
.card{display:block;text-decoration:none;color:#111;background:#fff;border:2px solid #111;border-radius:6px;overflow:hidden;transition:.15s}
.card:hover{border-color:#d90429;transform:translateY(-2px);box-shadow:4px 4px 0 #d90429}
.card img{width:100%;height:130px;object-fit:cover;display:block;border-bottom:2px solid #111}.big img{height:180px}
.tx{padding:10px}.tx b{display:block;font-size:14px;line-height:1.3}.big .tx b{font-size:16px}
small{display:block;color:#666;margin-top:6px;font-size:12px}
.sg{float:right;background:#d90429;color:#fff;font-size:10px;font-weight:800;padding:2px 6px;border-radius:3px;margin:0 0 4px 6px}
.cols{display:grid;grid-template-columns:1fr 330px;gap:26px;align-items:start}
.box{background:#000;color:#fff;border-radius:8px;padding:4px 16px 16px;margin-bottom:22px}.box h2{color:#fff}
.hol{list-style:none;margin:0;padding:0}.hol li{display:flex;gap:12px;align-items:center;padding:10px 0;border-top:1px solid #333}
.hol small{color:#aaa;margin-top:2px}.dl{min-width:52px;text-align:center;background:#d90429;border-radius:6px;padding:6px 0;font-size:20px;font-weight:900}
.dl i{display:block;font-size:9px;font-style:normal;font-weight:600;text-transform:uppercase}
.stack{display:grid;gap:10px}.box .card{border-color:#fff}.box .card:hover{box-shadow:4px 4px 0 #d90429}
.empty{color:#888;font-size:13px}footer{padding:30px 18px;text-align:center;color:#888;font-size:12px}
@media(max-width:860px){.cols{grid-template-columns:1fr}.top .grid{grid-template-columns:1fr}}
"""
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>F&amp;B Radar · SG</title><style>{CSS}</style></head><body>
<header><div class="wrap"><div class="logo">F&amp;B <em>RADAR</em> SG</div><small>Updated {stamp}</small></div></header>
<div class="wrap"><section class="top"><h2>Trending in Singapore</h2><div class="grid">{"".join(card(i, True) for i in top)}</div></section>
<div class="cols"><div>{main}</div><aside>{holidays()}{memes}</aside></div></div>
<footer>Singapore stories ranked first, then freshness. Auto-updates every 6 hours.</footer></body></html>"""
open("docs/index.html", "w", encoding="utf-8").write(page)
print("done")
