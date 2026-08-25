# 3C Content Intelligence Hub · HUAWEI Edition V2

## V2 upgrades
- Market filters: Global / Malaysia / UK / Indonesia / Japan
- Apple / Samsung / Garmin priority monitoring
- Google / Xiaomi / Sony / Bose discovery
- YouTube campaign discovery
- Reddit discussion discovery
- SEO / How-to radar
- HUAWEI action board
- Content-mix seed benchmark
- Source health
- Daily GitHub Actions refresh at 09:00 MYT target
- Mobile-responsive dashboard

## Deploy
1. Create a GitHub repository.
2. Upload all files.
3. Settings → Pages → Deploy from branch → main / root.
4. Settings → Secrets and variables → Actions → New repository secret:
   `OPENAI_API_KEY`
5. Actions → Update 3C Intelligence → Run workflow.
6. Bookmark the generated GitHub Pages URL.

## Important
GitHub scheduled Actions can start later than the exact cron minute. The dashboard therefore shows the actual data timestamp rather than pretending it refreshed exactly at 09:00.

The initial dashboard data is a verified 24 Aug 2026 snapshot. Discovery feeds are not exhaustive. Verify original source pages before publishing factual claims.

## Next possible upgrades
- Real YouTube channel RSS feeds instead of discovery search
- More precise Reddit subreddit feeds
- PDP change detection with page snapshots
- Weekly and monthly trend aggregation
- Copy bank for Apple/Garmin/Samsung headlines
- HUAWEI content backlog with status and owners
- Export to CSV / Google Sheets
