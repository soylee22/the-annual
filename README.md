# The Annual

A real £1,000 Sandisk holding against a hypothetical £1,000 SPY allocation. Static GitHub Pages with dated free quote snapshots, a fixed entry stop, current-member YTD leaders and a frozen historical replay.

## Run

Install `requirements.txt`. Run `python scripts/refresh.py --leaders` for a complete scan, or `python scripts/refresh.py` for quotes and a once-daily scan. Serve `site/` with `python -m http.server 8521 --directory site`.

The confirmed entry is 12 October 2026 at 11:47 BST. Fill price is $1,557.71 for 0.8481779 shares. £1,000 debit includes a £1.50 FX fee. Broker FX is $1.32319999 per £1. The displayed broker average rounds to $1,557.72. No order identifiers or screenshot files are published.

The hypothetical benchmark uses the latest completed SPY minute at or before entry, fractional shares and the confirmed entry FX. Fees are zero for the benchmark. Modelled dividend adjustment uses the fixed entry date and re-reads its adjusted-close factor after new dividends. GBP valuations include later currency moves. Quotes are indicative exchange values, not the broker's OTC bid.

The GitHub workflow checks data about every 20 minutes on weekdays from 08:00 through 22:59 UTC. The browser reloads the published snapshot every minute. The daily ranking scans current constituents using adjusted-close return from the previous December close. Missing endpoints and mismatched latest sessions are excluded and disclosed. Runs can be delayed by GitHub or the data provider. Retained quotes keep their original source timestamps. Nothing executes trades.

## Research and design

The frozen backtest replays supplied winner selections from 2005 to 9 October 2026. Historical membership is checked, but missing competitor prices prevent certification of true winners. Exact stop fills and zero costs are assumptions. The common-pool endpoint, smooth and K-ratio arms have identical full-history eligibility. Chart replay has different partial-listing eligibility.

Editorial design references: [FT Visual Vocabulary](https://ft-interactive.github.io/visual-vocabulary-templates/), [Observable direct labels](https://old.observablehq.com/plot/marks/text), [Pentagram Igluu](https://www.pentagram.com/work/igluu). Original HTML, CSS and SVG chart implementation. Fonts are DM Serif Display, DM Sans and IBM Plex Mono, served by Google Fonts with local fallbacks.

Run `python -m pytest tests -q` for accounting, baseline look-ahead, quote timestamps and endpoint checks. `scripts/export_backtest.py` freezes checked outputs in the SecondBrain workspace. It is not needed by the published refresh workflow.

## Daily email

`scripts/daily.py` composes a dated portfolio digest. Sending requires an explicit `--send` and `GMAIL_APP_PASSWORD`. It reports the actual GBP holding versus SPY, fixed entry stop, observed peak drawdown, the separate January model, year-end countdown and five provisional YTD candidates. Source timestamps and failures remain visible. A receipt suppresses successful reruns on the same London date.

The dedicated `annual-daily.yml` workflow in `soylee22/lodestar` runs at 07:00 UTC on weekdays, using its existing protected Gmail credential. It checks out this public repository, runs tests, refreshes quotes and rankings, then sends as **The Annual**. This keeps the credential in its existing repository and leaves Lodestar's strategy and emails unchanged. This job does not publish or commit its temporary refreshed data. The separate Pages workflow continues to refresh the website. GitHub may delay scheduled runs. An SMTP acceptance confirms submission, not inbox delivery.

Preview locally with `python scripts/daily.py`. Preview and receipt folders are ignored by Git. GitHub keeps a daily receipt cache and a rendered preview artifact. This is a daily digest, not an immediate stop alert or an order service.
