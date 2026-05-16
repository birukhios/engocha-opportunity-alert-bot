# Engocha Opportunity Alert Bot

A production-ready MVP that uses GitHub Actions as a daily scheduler, GitHub JSON files as storage, public APIs as sources, and Telegram for alerts.

## What It Does

- Checks public opportunity sources for Engocha funding and relevant jobs.
- Scores each opportunity with configured funding and job keywords.
- Sends only new matches with a score of `3` or higher.
- Limits Telegram delivery to the top `10` matches per run.
- Stores sent opportunity IDs in `data/seen.json`.
- Stores sent opportunity details in `data/opportunities.json`.
- Commits updated JSON files back to the repository from GitHub Actions.

## MVP Sources

Active sources:

- ReliefWeb RSS for Ethiopia jobs. This does not require a ReliefWeb app name.
- ReliefWeb API for NGO and humanitarian jobs.
- UNjobs public Ethiopia and remote listings.
- NGOJobs Ethiopia public listings.
- Ethiojobs Info RSS.
- Grants.gov API for funding opportunities.

Future-source placeholders are included for:

- fundsforNGOs
- Devex
- EU Funding & Tenders
- UNjobs
- Ethiojobs
- LinkedIn search links

Those placeholders are intentionally inactive until each source has a legal public API, RSS feed, or explicitly allowed HTML collection path.

## Telegram Setup

### 1. Create a bot with BotFather

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`.
3. Follow the prompts for bot name and username.
4. BotFather will return your bot token.

### 2. Get `TELEGRAM_BOT_TOKEN`

Use the token BotFather gives you. It looks like:

```text
123456789:AAExampleTokenHere
```

Never commit this token to the repository.

### 3. Get `TELEGRAM_CHAT_ID`

1. Start a chat with your new bot and send it any message.
2. Open this URL in your browser, replacing the token:

```text
https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
```

3. Find `chat.id` in the JSON response.
4. Use that number as `TELEGRAM_CHAT_ID`.

For a Telegram group, add the bot to the group, send a message in the group, then call `getUpdates` and use the group `chat.id`.

## GitHub Secrets

In your GitHub repository:

1. Go to `Settings`.
2. Open `Secrets and variables`.
3. Choose `Actions`.
4. Add these repository secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Optional but recommended for ReliefWeb:

```text
RELIEFWEB_APP_NAME
```

ReliefWeb requires an approved app name. Request one from the ReliefWeb API documentation page:

```text
https://apidoc.reliefweb.int/parameters#appname
```

If `RELIEFWEB_APP_NAME` is missing or not approved, the ReliefWeb API source may fail, but the bot will continue running Grants.gov, ReliefWeb RSS, and UNjobs.

## Run Locally

Create and activate a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Export your environment variables:

```bash
export TELEGRAM_BOT_TOKEN="your-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export RELIEFWEB_APP_NAME="your-approved-reliefweb-appname"
```

Run without sending Telegram messages:

```bash
python src/main.py --dry-run
```

Run for real:

```bash
python src/main.py
```

## GitHub Actions Schedule

The workflow is at:

```text
.github/workflows/opportunity-alert.yml
```

It runs three times per day at `05:13`, `10:13`, and `15:13 UTC`, which is `08:13`, `13:13`, and `18:13` in Africa/Addis_Ababa time.

It can also be started manually from the GitHub Actions tab because `workflow_dispatch` is enabled.

The workflow has:

```yaml
permissions:
  contents: write
```

That lets `GITHUB_TOKEN` commit updates to:

```text
data/seen.json
data/opportunities.json
```

## Scoring System

Each opportunity is normalized, then scored against either funding keywords or job keywords.

Funding keywords include:

```text
Ethiopia, Africa, grant, funding, startup, innovation, AI, research,
survey, data collection, civic tech, digital public goods, youth employment,
social impact, market research, community data, fintech, entrepreneurship,
SME, MSME, open data, digital inclusion, financial inclusion
```

Funding alerts use a higher minimum score and an Engocha relevance gate. A funding opportunity must either mention Ethiopia/Africa or match multiple Engocha themes such as startup, civic tech, data collection, market research, community data, fintech, youth employment, digital public goods, AI, or social impact. Generic biomedical or academic research notices are filtered out.

Job keywords include:

```text
Product Manager, Digital Product, UX Research, Research Officer,
Innovation Officer, MEAL, Monitoring and Evaluation, Data Officer,
Program Manager, ICT Officer, Digital Transformation, Fintech, NGO,
Addis Ababa, Ethiopia, Africa, Remote, Home based, Full-time
```

For job alerts, the bot also requires a skill signal in the job title and a work-fit signal such as Ethiopia, Addis Ababa, Africa, remote, home based, or full-time. This keeps broad NGO posts from crowding out roles that better match product, research, MEAL, digital, data, innovation, and fintech skills.

Extra weight is given to:

```text
Ethiopia, Africa, Product Manager, UX Research, grant, funding, AI,
research, digital product
```

Only opportunities with score `>= 3` are eligible for Telegram alerts.

## Add New Sources

Add a new source in `src/sources.py` by subclassing `OpportunitySource`:

```python
class ExampleSource(OpportunitySource):
    name = "Example"

    def fetch(self) -> list[dict]:
        return [
            {
                "id": make_opportunity_id(title, link),
                "title": title,
                "link": link,
                "source": self.name,
                "type": "job",  # or "funding"
                "organization": organization,
                "location": location,
                "deadline": deadline,
                "summary": summary,
                "date_found": utc_today(),
            }
        ]
```

Then add the source to `get_sources()`.

Prefer sources in this order:

1. Official public API.
2. RSS or Atom feed.
3. HTML only when allowed by the site's terms and robots policy.

## Data Files

`data/seen.json` stores sent IDs to prevent duplicate Telegram alerts.

`data/opportunities.json` stores sent opportunities with:

```text
title, link, source, type, score, matched_keywords, deadline, date_found
```

The unique ID is generated from a SHA-256 hash of `title + link`.
