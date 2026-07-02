---
name: live-monitor
description: "Real-time monitoring: fetch live data (scores, stocks, prices, news) and alert on changes or thresholds."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [monitoring, alerts, real-time, cron, stocks, scores, news]
    related_skills: []
---

# Live Monitor: Real-Time Data Monitoring & Alerts

## Overview

This skill enables Zeus to monitor live data sources in real time — sports
scores, stock prices, cryptocurrency, news, weather, and more — and send
alerts when conditions are met or values change.

Monitors run as recurring cron jobs. Each tick, Zeus fetches the latest
data using `web_search` or connected MCP servers, checks it against any
configured conditions, and delivers an alert to the user's preferred
channel (Telegram, Discord, CLI, etc.).

## How Monitors Work

1. **Fetch**: Use `web_search` to find the latest value for the query
   (e.g., "Lakers score today", "AAPL stock price", "BTC price USD")
2. **Parse**: Extract the relevant data from search results — the score,
   price, headline, or status
3. **Evaluate**: Check against any threshold or condition:
   - Price above/below a target
   - Score changed since last check
   - Keyword appeared in news
   - Any change at all (for "notify me when X changes")
4. **Alert or Suppress**:
   - If the condition is met → format a concise alert and deliver it
   - If nothing changed / condition not met → output `[SILENT]` to
     suppress delivery (the cron system recognizes this marker)

## Data Fetching Strategies

### Sports Scores
```
Query: "{team} score today" or "{team1} vs {team2} score"
Search for: latest game score, game status (in progress, final, scheduled)
Alert when: score changes, game starts, game ends, key plays
```

### Stock Prices
```
Query: "{ticker} stock price" or "{ticker} NASDAQ"
Search for: current price, change %, day range
Alert when: price crosses threshold, significant movement (>2%)
```

### Cryptocurrency
```
Query: "{symbol} price USD" or "{symbol} coinmarketcap"
Search for: current price, 24h change
Alert when: price crosses threshold, significant movement
```

### News & Events
```
Query: "{topic} news latest" or "{topic} breaking"
Search for: headlines, timestamps
Alert when: new article published, keyword match
```

### Weather
```
Query: "{location} weather current"
Search for: temperature, conditions, alerts
Alert when: severe weather, temperature threshold
```

### Custom / MCP Sources
If MCP servers are configured (e.g., a finance MCP, a sports API MCP),
use those tools instead of web_search for structured, reliable data.
MCP tools provide cleaner data than web scraping.

## Alert Format

Keep alerts concise and scannable:

```
📊 Lakers 112 - 108 Warriors (Q4 2:31)
   Game in progress — Lakers lead by 4
```

```
📈 AAPL $198.45 (+2.3%)
   Above your $195 threshold
```

```
₿ BTC $67,234 (-1.2%)
   24h range: $66,800 - $68,100
```

```
📰 "Fed cuts rates by 0.5%" — Reuters, 12 min ago
   Keyword match: "fed rates"
```

## Suppression

When there is nothing to report (no change, condition not met, game not
started yet), output exactly:

```
[SILENT]
```

This tells the cron system to skip delivery — the user won't get a
notification. This is critical for high-frequency monitors (every 5
minutes) that would otherwise spam the user with "no change" messages.

## Workflow

### When a monitor cron job fires

1. Read the prompt to understand what to monitor and any thresholds
2. Use `web_search` (or MCP tools if available) to fetch the latest data
3. Parse the search results to extract the key value(s)
4. Compare against any threshold or change condition
5. If the condition is met or there's a notable change:
   - Format a concise alert (see formats above)
   - Include the current value and any relevant context
6. If nothing to report:
   - Output `[SILENT]` to suppress delivery

### When the user says "monitor X" or "watch X"

1. Ask for the monitoring interval (default: every 5 minutes for scores,
   every 30 minutes for stocks, hourly for news)
2. Ask for the delivery channel (default: same platform they're on)
3. Ask for any threshold or condition (optional)
4. Create the monitor using `hermes monitor add`
5. Confirm the monitor is active and when they'll get alerts

### When the user says "stop monitoring X" or "remove monitor X"

1. Find the monitor by name: `hermes monitor list`
2. Remove it: `hermes monitor remove <name>`
3. Confirm removal

### When the user says "what am I monitoring" or "show monitors"

1. Run `hermes monitor list`
2. Show each monitor with its schedule, query, and delivery channel

## Important Notes

- **Use [SILENT]**: Always suppress delivery when there's nothing to
  report. This prevents notification spam for high-frequency monitors.
- **Concise alerts**: Keep messages short — users read these on their
  phone via Telegram/Discord. One line of data + one line of context.
- **MCP over web_search**: When an MCP server is available for the data
  source, prefer it over web_search — structured data is more reliable
  than parsing search results.
- **Rate limits**: Don't set intervals shorter than 1 minute. Web search
  providers have rate limits. For most use cases, 5-15 minutes is fine.
- **Time zones**: For stock market monitors, use market hours
  (9:30 AM - 4:00 PM ET, Mon-Fri) to avoid checking when markets are
  closed. Use cron expressions like `0 9-16 * * 1-5`.
