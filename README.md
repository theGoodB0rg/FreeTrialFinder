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

## Alert Dispatch Sample

When a qualifying deal or credit tier is discovered, an immediate alert is dispatched:

```text
[VERIFIED DEVELOPER/API CREDIT]
Title: Together AI $25 Free Developer Credits for Claude & Llama
Provider: Together AI
Usability Score: 92/100
Category: api_credits
Promo Code: DEV25 (tap to copy)
Value: $25
Signals: mentions_api_endpoints, mentions_credits_tokens, has_promo_code

Summary:
Enter promo code DEV25 at billing to receive $25 in API credits usable with OpenAI-compatible endpoint.

Link: https://together.ai/signup?promo=DEV25
```

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

---

## Cloud Deployment (GitHub Actions)

The repository includes a ready-to-run scheduled workflow in `.github/workflows/poll.yml`.

Because the repository is public, workflow execution incurs **zero cost and utilizes unlimited public runner minutes**.

### Workflow Configuration:
1. In the repository settings, navigate to **Settings** -> **Secrets and variables** -> **Actions**.
2. Add repository secrets:
   - `TELEGRAM_BOT_TOKEN`: Telegram bot token from BotFather.
   - `TELEGRAM_CHAT_ID`: Numeric user ID from userinfobot.
   - `DISCORD_WEBHOOK_URL` (optional): Webhook URL for Discord notifications.
3. The workflow executes automatically every 30 minutes, runs tests, polls candidate sources, dispatches alerts, and commits updated deduplication state back to `data/seen_deals.json`.

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
