# FreeTrialFinder

<p align="center">
  <a href="https://github.com/theGoodB0rg/FreeTrialFinder/actions"><img src="https://github.com/theGoodB0rg/FreeTrialFinder/actions/workflows/poll.yml/badge.svg" alt="Build Status" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" />
  <img src="https://img.shields.io/badge/cost-%240%20%2F%20mo-brightgreen" alt="Cost: $0" />
  <img src="https://img.shields.io/badge/notifications-Telegram%20%7C%20Discord-blue" alt="Notifications" />
</p>

A modular, test-driven polling engine that continuously monitors developer sources for **free trials, API credits, promo vouchers, and developer grants** for foundational AI models (Claude, OpenAI / ChatGPT, Gemini, etc.) specifically usable within developer IDEs and coding agents (Aide, Cursor, Cline, Aider, OpenRouter, AWS Bedrock, Google Vertex AI).

The tool incorporates a heuristic scoring pipeline that filters out browser-locked consumer chatbot interfaces, prioritizing programmatic API access, OpenAI-compatible base URLs, and cloud provider credit tiers.

Runs continuously with **zero server infrastructure costs** via scheduled GitHub Actions workflows with persistent git-backed state deduplication and immediate alert dispatch to Telegram or Discord.

---

## Technical Overview

Generic coupon aggregators typically index non-functional promotional codes or browser-only chatbot wrappers ("chat on our website with Claude"). These interfaces cannot be integrated into programmatic developer workflows or coding IDEs.

FreeTrialFinder addresses this through automated extraction and heuristic developer scoring:

- **Programmatic Accessibility**: Prioritizes offers containing API keys, OpenAI-compatible base URLs, IDE extension integrations (`aide`, `cursor`, `cline`, `continue.dev`), and cloud credits (AWS Bedrock, Google Cloud Vertex AI, Azure OpenAI, OpenRouter).
- **Anti-Chatbot Heuristic Filtering**: Applies negative weights to consumer-only web wrappers, browser extensions, and messaging bot skins lacking API endpoints.
- **Two-Tier Classification**:
  - `DIRECT_IDE` (Score >= 75): High-confidence developer endpoints, API grants, or IDE discounts.
  - `POTENTIAL` (Score 40–74): Legitimate foundational model trials or institutional programs flagged for quick manual verification.
  - `REJECTED` (Score < 40): Out-of-scope entries, irrelevant promotions, or consumer wrappers with no API utility.
- **Deterministic Deduplication**: Maintains persistent SHA-256 fingerprint state (`data/seen_deals.json`) to prevent redundant notifications.

---

## What Reaches Your Phone

An AI triage step reads every new candidate and routes it. Silence is the default:

| Route | When | Delivery |
| --- | --- | --- |
| **now** | A verified, claimable offer that is new, time-limited or has a code, and matches `profile.md` | Telegram immediately |
| **digest** | Verified but not urgent, or could not be verified | One daily summary message |
| **drop** | Discussion posts, showcases, news, expired or paid-only offers | Never sent (remembered as seen) |

Each alert is written by the AI, and promo codes are tap-to-copy (a `📋 Copy` button plus a monospace code):

```text
Together AI: $25 in free API credits                      <- links to the source URL
Covers a few weeks of Llama and DeepSeek calls from Cline or Aider at no cost.

Code     DEV25
Value    $25
Expires  30 Nov 2026

How to claim
Sign up, open Billing and redeem the code. Then set OPENAI_BASE_URL=https://api.together.xyz/v1

Together AI · hacker news
[ 📋 Copy DEV25 ]  [ Open offer ↗ ]
```

Tune what counts as "now" by editing [`profile.md`](profile.md). No code changes needed.

---

## Architecture

```text
                    +----------------------------+
                    |    GitHub Actions Cron     |
                    |   (Every 30m - $0 cost)    |
                    +-------------+--------------+
                                  |
                                  v
                    +----------------------------+
                    |     FinderEngine Core      |
                    +------+------+------+-------+
                           |      |      |
       +-------------------+      |      +-------------------+
       v                          v                          v
+--------------+          +--------------+           +---------------+
|  HackerNews  |          |GitHub Curated|           |  Google News  |
| Algolia API  |          | LLM Repos    |           |   RSS Feeds   |
+------+-------+          +------+-------+           +-------+-------+
       +-------------------+      |      +-------------------+
                           v      v      v
                    +----------------------------+
                    |    DealScorer & Filter     |
                    |  (Anti-Chatbot + IDE Pts)  |
                    +-------------+--------------+
                                  |
                                  v
                    +----------------------------+
                    |    StateManager Cache      |
                    |   (data/seen_deals.json)   |
                    +-------------+--------------+
                                  |
                                  v (New Deals Only)
                    +----------------------------+
                    |   Telegram / Discord Bot   |
                    +----------------------------+
```

---

## Quick Start (Local)

### 1. Installation
```powershell
git clone https://github.com/theGoodB0rg/FreeTrialFinder.git
cd FreeTrialFinder
pip install -r requirements.txt
pip install -e .
```

### 2. Configuration (.env)
```powershell
cp .env.example .env
```

Configure Telegram bot credentials or Discord webhook:
```env
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_numeric_chat_id"
MIN_SCORE=40
```

To set up a Telegram bot:
1. Message `@BotFather` on Telegram, create a bot with `/newbot`, and copy the token.
2. Start a chat with the created bot.
3. Message `@userinfobot` on Telegram to retrieve your numeric user ID (`TELEGRAM_CHAT_ID`).

### 3. Verify Alert Pipeline
```powershell
python -m freetrialfinder.cli test-notify
```

### 4. Inspect Live Deals (Dry-Run)
Scan live endpoints and print a structured summary without modifying state or dispatching alerts:
```powershell
python -m freetrialfinder.cli inspect
```

### 5. Execute Polling Run
Scan sources, evaluate deals, dispatch notifications, and record state:
```powershell
python -m freetrialfinder.cli poll
```

### 6. Quick Runs (Cheat Sheet)
```powershell
# Look without saving or alerting
python -m freetrialfinder.cli inspect --min-score 40

# Fetch, score, alert on new deals, and save to data/seen_deals.json
python -m freetrialfinder.cli poll --state-file data/seen_deals.json --min-score 40

# Verify Telegram / Discord wiring with a sample alert
python -m freetrialfinder.cli test-notify

# Send the daily digest of pending deals
python -m freetrialfinder.cli digest

# Build offline browser report from saved state
python tools/export_html.py --in data/seen_deals.json --out data/report.html

# Run tests
pytest -v
```

---

## Cloud Deployment (GitHub Actions)

`.github/workflows/poll.yml` runs on a schedule (GitHub fires it a few times a day), runs the tests, polls, triages, alerts, sends the digest when the last one is 20+ hours old, and commits `data/seen_deals.json`.

**Secrets** (Settings -> Secrets and variables -> Actions -> Secrets):
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `AGENT_API_KEY`: key for the OpenAI-compatible triage model (default endpoint: Groq's free tier)
- `DISCORD_WEBHOOK_URL` (optional), `PROFILE` (optional: private replacement for `profile.md`)

**Variables** (optional, not secret): `AGENT_BASE_URL`, `AGENT_MODEL`, `AGENT_MAX_PER_RUN`, `MIN_SCORE`.

Security notes: secrets are only exposed to the poll step (never to tests), third-party actions are pinned to commit SHAs, the workflow token is read-only except for the job that commits state, and AI traces are uploaded as a 7-day artifact instead of being committed to this public repo. Run the workflow manually with **force_digest** to get a digest immediately.

---

## AI Triage Agent

Keyword heuristics cannot tell a real offer from a Reddit thread that merely mentions "free credits". The scorer is now only a cheap pre-filter; every new candidate goes to a small tool-calling agent that reads the page and decides.

```text
new deal --> DealVerifier --(fetch_page)--> page text
                  |
            submit_verdict: keep | reject | unsure  (+ urgent, headline, why, action, code, value, expires)
                  |
   keep + urgent -> now      keep -> digest      unsure -> digest ("could not verify")      reject -> drop
```

Guardrails (all in `freetrialfinder/agent/`, all unit-tested offline with a scripted fake model):

- **Bounded loop**: at most 5 model turns and 2 page fetches per deal, plus a per-run budget (`AGENT_MAX_PER_RUN`). Deals over budget wait for the next run instead of going out unchecked.
- **Tool allowlist**: only `fetch_page` and `submit_verdict` execute; any other tool name is refused and flagged.
- **SSRF guard**: `fetch_page` allows only http(s) to public hosts, re-checks after redirects, blocks localhost, private, link-local and cloud metadata addresses, caps size and time, and strips scripts before the model sees the text.
- **Grounded verdicts**: `evidence` must be an exact quote from text the agent actually saw, or the verdict becomes `unsure`. A promo code is shown only if it appears verbatim in that text. Only a grounded `keep` can be urgent.
- **Prompt-injection limits**: page text is treated as data; AI-written text is HTML-escaped and any URL in it is rendered as non-clickable code, so the only link in an alert is the URL from the source.
- **Outages never spam or lose deals**: on API errors the agent stops after 2 consecutive failures, deals are retried next run, and after 3 days they go to the digest marked unverified.
- **Delivery-confirmed state**: a "now" deal is only marked seen once Telegram/Discord accepted it.

Observability and evaluation:

```powershell
# Every model turn, tool call, guard trip and verdict is one JSON line in data/agent_traces.jsonl
python -m freetrialfinder.cli traces --last 10

# Score the agent against hand-labelled real deals (evals/labelled_deals.jsonl)
python -m freetrialfinder.cli eval

# Preview the alert and digest formats on your phone
python -m freetrialfinder.cli test-notify
python -m freetrialfinder.cli test-notify --digest

# After changing a parser or scoring: mark what sources list now as seen, without alerting
python -m freetrialfinder.cli baseline --only github_curated
```

`eval` reports accuracy on decided deals, false-keep rate (spam that would be alerted), `false_urgent` (spam that would buzz your phone; must be 0), false-reject rate, unsure rate, and average tool calls per deal.

Locally, set `ENABLE_AGENT=true` and `AGENT_API_KEY` in `.env` (any OpenAI-compatible endpoint works via `AGENT_BASE_URL`).

---

## Test Suite

The test suite follows test-driven development practices and verifies scoring heuristics, XML/RSS parsing, markdown table extraction, deduplication persistence, and notification payload formats:

```powershell
pytest -v
```

---

## Project Structure

```text
FreeTrialFinder/
├── .github/
│   └── workflows/
│       └── poll.yml             # GitHub Actions cron runner (30m schedule)
├── freetrialfinder/             # Core application package
│   ├── __init__.py              # Package initialization & version
│   ├── models.py                # Schemas: DealItem, RawDeal, ConfidenceLevel
│   ├── config.py                # Environment & settings loader
│   ├── state.py                 # Persistent deduplication cache
│   ├── engine.py                # Pipeline orchestrator
│   ├── cli.py                   # Command-line interface
│   ├── sources/                 # Pluggable data sources
│   │   ├── base.py              # BaseSource interface
│   │   ├── hacker_news.py       # Algolia HN API scraper
│   │   ├── github_curated.py    # Curated markdown repository parser
│   │   ├── google_news.py       # Google News RSS query monitor
│   │   └── reddit.py            # Developer subreddits monitor
│   ├── filters/                 # Scoring and classification
│   │   ├── base.py              # Filter interfaces
│   │   └── scorer.py            # Usability scorer & code extractor
│   └── notifiers/               # Alert notification dispatchers
│       ├── base.py              # BaseNotifier interface
│       ├── telegram.py          # Telegram HTML card dispatcher
│       ├── discord.py           # Discord webhook embed dispatcher
│       └── console.py           # Terminal output renderer
├── tests/                       # Automated test suite
│   ├── test_cli.py
│   ├── test_engine.py
│   ├── test_models.py
│   ├── test_notifiers.py
│   ├── test_scorer.py
│   ├── test_sources_github.py
│   ├── test_sources_google_news.py
│   ├── test_sources_hn.py
│   ├── test_sources_reddit.py
│   └── test_state.py
├── .env.example                 # Environment variable template
├── LICENSE                      # MIT License
├── pyproject.toml               # Build system & pytest configuration
├── README.md                    # Project documentation
└── requirements.txt             # Project dependencies
```

---

## License

MIT © [Olorunfemi John (theGoodB0rg)](https://github.com/theGoodB0rg)
