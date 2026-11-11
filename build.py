import json, html, re, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, date
from email.utils import parsedate_to_datetime

PER_FEED = 6
UA = "Mozilla/5.0 (compatible; fnb-feed/1.0)"

def parse_date(s):
    if not s: return datetime.min.replace(tzinfo=timezone.utc)
    try: return parsedate_to_datetime(s)
    except Exception: pass
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return datetime.min.replace(tzinfo=timezone.utc)

def txt(el, *names):
    for n in names:
        for e in el.iter():
            if e.tag.split("}")[-1] == n and (e.text or e.attrib):
                return e
    return None

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return ET.fromstring(r.read())

def items(root, source):
    out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"): continue
        t = txt(it, "title"); l = txt(it, "link")
        d = txt(it, "pubDate", "published", "updated")
        if t is None or l is None: continue
        link = l.attrib.get("href") or (l.text or "").strip()
        img = ""
        for e in it.iter():
            tag = e.tag.split("}")[-1]
            if tag in ("thumbnail", "content", "enclosure") and e.attrib.get("url", "").startswith("http"):
                img = e.attrib["url"]; break
        if not img:
            c = txt(it, "content", "description", "summary")
            m = re.search(r'<img[^>]+src="([^"]+)"', html.unescape(c.text or "")) if c is not None else None
            if m: img = m.group(1)
        out.append({"title": (t.text or "").strip(), "link": link, "date": parse_date(d.text if d is not None else None),
                    "source": source, "img": img})
    return sorted(out, key=lambda x: x["date"], reverse=True)[:PER_FEED]

feeds = json.load(open("feeds.json"))
sections = {}
for cat, lst in feeds.items():
    seen, rows = set(), []
    for f in lst:
        try:
            for i in items(fetch(f["url"]), f["name"]):
                if i["link"] not in seen:
                    seen.add(i["link"]); rows.append(i)
        except Exception as e:
            print(f"skip {f['name']}: {e}")
    sections[cat] = sorted(rows, key=lambda x: x["date"], reverse=True)

def card(i):
    img = f'<img src="{html.escape(i["img"])}" loading="lazy" alt="">' if i["img"] else ""
    when = i["date"].strftime("%b %d") if i["date"].year > 1 else ""
    return (f'<a class="card" href="{html.escape(i["link"])}" target="_blank" rel="noopener">{img}'
            f'<div><b>{html.escape(i["title"])}</b><small>{html.escape(i["source"])} · {when}</small></div></a>')

def holidays():
    today = date.today(); rows = []
    for h in json.load(open("holidays.json")):
        if "date" in h:
            d = date.fromisoformat(h["date"])
        else:
            m, dd = map(int, h["md"].split("-")); d = date(today.year, m, dd)
            if d < today: d = date(today.year + 1, m, dd)
        if d >= today: rows.append((d, h))
    rows.sort(key=lambda x: x[0])
    cards = "".join(f'<div class="card"><div><b>{html.escape(h["name"])}</b><small>{h["tag"]} · {d.strftime("%b %d, %Y")} · {(d - today).days} days left</small></div></div>' for d, h in rows[:8])
    return f'<h2>Upcoming Holidays</h2><div class="grid">{cards}</div>'

body = holidays() + "".join(f'<h2>{html.escape(c)}</h2><div class="grid">{"".join(card(i) for i in rows)}</div>' for c, rows in sections.items())
now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>F&amp;B Feed</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--card:#f4f4f2;--mut:#777}}
@media(prefers-color-scheme:dark){{:root{{--bg:#151515;--fg:#eee;--card:#222;--mut:#999}}}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1000px;margin:0 auto;padding:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}}
.card{{background:var(--card);border-radius:10px;overflow:hidden;text-decoration:none;color:inherit;display:block}}
.card img{{width:100%;height:140px;object-fit:cover}}.card div{{padding:10px}}
small{{display:block;color:var(--mut);margin-top:6px}}</style></head>
<body><h1>F&amp;B Feed</h1><small>Updated {now}</small>{body}</body></html>"""
open("docs/index.html", "w", encoding="utf-8").write(page)
print("done")
