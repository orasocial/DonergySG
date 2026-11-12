"""Offline tests: python tests/test_build.py  (no network; feeds come from generated fixtures)."""
import json, os, re, shutil, subprocess, sys, tempfile, html
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
import build
from datetime import datetime
now = build.NOW.isoformat()
A = lambda t, s="SETHLUI", p="", l=None, e="", sgq=True: {"t": t, "l": l or "https://x.com/" + re.sub(r"\W+", "-", t)[:40], "d": now, "s": s, "p": p, "i": "", "e": e, "f": now, "sgq": sgq}
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))

# URL normalisation + headline similarity
ok(build.norm_url("https://www.Site.com/a/?utm_source=x&id=2#top") == build.norm_url("http://site.com/a?id=2"), "tracking params, www, scheme, fragment ignored")
bk1, bk2 = "Burger King Singapore's 11.11 Sale Brings 1-FOR-1 WHOPPER, Long Chicken & More", "Burger King 11.11 Deals: 1-for-1 Whopper, Long Chicken, Truffle Mayo Burgers and More"
ok(build.similar(bk1, bk2), "same promotion, different wording is grouped")
ok(not build.similar(bk1, "McDonald's Singapore launches 11.11 deals with 1-for-1 McSpicy"), "different brand is not grouped")
ok(not build.similar("Mr. Cheesecake pop-up opens in Singapore", "Why queues for pop-ups are getting shorter in Singapore"), "different angle stays separate")

# relevance
drop = ["New Southampton restaurant gives away free food on opening day", "Dover food drive and giveaway hosted by 75 Broadway Laundromat",
        "Up to $250 cash payouts for Singaporeans in Dec 2026", "CJ CheilJedang Steps Up AI Factory Transition for Food and Beverage"]
for t in drop: ok(build.classify(A(t, "GNews: Freebies", "Yahoo")) is None, "filtered: " + t[:50])
ok(not build.classify(A("Singapore property cooling measures explained", "SETHLUI")), "SG publisher alone is not enough")
n = build.classify(A("New Turkish restaurant opens at Millenia Walk with 1-for-1 döner", "GNews: Turkish food SG", "Mothership"))
ok(n and "Near Millenia" in n["c"] and "Halal Dining" in n["c"] and n["x"] and n["w"], "Millenia + Turkish story kept, tagged, has why/idea")
o = build.classify(A("How a London cafe grew with a viral TikTok loyalty campaign", "Eater", sgq=False))
ok(o and o["c"] == ["Overseas ideas"], "overseas marketing example goes only to Overseas ideas")
h = build.classify(A("Hi Bánh Mì: hidden gem in Geylang"))
ok(h is not None, "plain SG food story kept")

t1 = build.classify(A("Why this chicken rice meme is taking over TikTok", "GNews: TikTok trends", "Mothership", sgq=False) | {"tr": True})
ok(t1 and t1["c"] == [build.TRENDS] and t1["reg"] == "tr", "trend/meme items go to the Trends & Memes row only")
ok(build.classify(A("Dover laundromat giveaway goes viral", "GNews: TikTok trends", "Yahoo", sgq=False) | {"tr": True}) is None, "local giveaways filtered from trends too")
ok(build.classify(A("Parliament passes new housing bill", "GNews: Viral trends SG", "CNA", sgq=False) | {"tr": True}) is None, "non-trend news filtered from trends feed")
# grouping keeps clearest original source
g = build.cluster([build.classify(A(bk1, "GNews: 1-for-1 SG", "Danamic", l="https://news.google.com/rss/articles/AAA?oc=5")), build.classify(A(bk2, "SETHLUI", l="https://sethlui.com/bk-1111?utm_source=fb"))])
ok(len(g) == 1 and "sethlui.com" in g[0]["l"] and len(g[0]["rel"]) == 1, "duplicates grouped; original publisher is main, other coverage kept as related")

# end-to-end with a simulated failed source, then a total outage
tmp = tempfile.mkdtemp(); [shutil.copy(f, tmp) for f in ("build.py", "feeds.json", "holidays.json", "template.html")]; os.makedirs(tmp + "/docs"); os.makedirs(tmp + "/fx")
feeds = json.load(open("feeds.json")); names = [f["name"] for l in feeds.values() for f in l]
from email.utils import format_datetime
SAMPLE = ["New Turkish grill opens at Millenia Walk", "Halal-certified burger chain opens in Singapore", "Singapore cafe launches 1-for-1 coffee promo",
          "Marina Bay Christmas market brings food stalls to Suntec", "Hawker stall in Geylang draws long queues", "Singapore restaurant adds lunch set for office workers"]
for i, nme in enumerate(names):
    items = "".join(f"<item><title>{html.escape(t + (' ' + str(i) if j else ''))}</title><link>https://example.com/{i}/{j}</link><pubDate>{format_datetime(build.NOW)}</pubDate></item>" for j, t in enumerate(SAMPLE[:4])) if i % 2 == 0 else "<item><title>TikTok viral meme trend</title><link>https://example.com/t%d</link><pubDate>%s</pubDate></item>" % (i, format_datetime(build.NOW))
    open(f"{tmp}/fx/{build.slug(nme)}.xml", "w", encoding="utf-8").write(f"<rss><channel>{items}</channel></rss>")
run = lambda extra: subprocess.run([sys.executable, "build.py"], cwd=tmp, env={**os.environ, "DD_FIXTURES": tmp + "/fx", **extra}, capture_output=True, text=True)
load = lambda: json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', open(tmp + "/docs/index.html", encoding="utf-8").read(), re.S).group(1).replace("<\\/", "</"))
r0 = run({}); d0 = load()
if r0.returncode: print(r0.stdout, r0.stderr)
ok(r0.returncode == 0 and d0["failed"] == 0, f"baseline build ({d0['ok']} sources ok, {len(d0['articles'])} stories)")
fail_name = names[0]; n0 = sum(1 for a in d0["articles"] if a["s"] == fail_name)
r = run({"DD_FAIL": fail_name}); d1 = load()
ok(r.returncode == 0 and any(s["n"] == fail_name and not s["ok"] and "503" in s["why"] for s in d1["sources"]), "simulated failure recorded with reason")
ok(d1["ok"] == d0["ok"] - 1 and len(d1["articles"]) == len(d0["articles"]), "other sources still loaded; nothing lost")
ok(n0 > 0 and all(a["cached"] for a in d1["articles"] if a["s"] == fail_name) and not any(a["cached"] for a in d1["articles"] if a["s"] != fail_name), f"failed source's {n0} stories kept and marked cached; others not")
r = run({"DD_FAIL": "|".join(names)}); d2 = load()
ok(d2["ok"] == 0 and len(d2["articles"]) == len(d1["articles"]) and d2["updated"] == d1["updated"], "total outage: stories kept, 'last updated' not advanced")
