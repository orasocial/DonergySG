# F&B Feed
Auto-updating page of F&B news, promos, Turkish & halal news, social trends, memes, plus an Upcoming Holidays tracker (Turkish + Muslim). Rebuilds every 6 hours.

## Setup
1. Create a new GitHub repo, upload all these files (keep the `.github` folder).
2. Settings > Pages > Source: Deploy from branch > `main` / `docs`.
3. Actions tab > "Update feed" > Run workflow.
4. Your page: `https://<username>.github.io/<repo>/`

## Add more sources
Edit `feeds.json`. Any RSS/Atom URL works. Google News search feeds:
`https://news.google.com/rss/search?q=YOUR+KEYWORDS+when:7d`

Note: Reddit sometimes blocks GitHub servers. If memes come up empty, that's why.

## Holidays
Edit `holidays.json`. Fixed dates use `"md": "MM-DD"` (repeat yearly). Islamic dates shift ~11 days earlier each year and depend on moon sighting, so update the `"date"` entries every year.
