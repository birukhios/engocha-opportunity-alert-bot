"""Main entry point for the GitHub Actions Telegram opportunity alert bot."""

from __future__ import annotations

import argparse
import logging
import sys

from scoring import MIN_SCORE, is_relevant_match, score_opportunity, why_it_fits
from sources import fetch_all_sources
from storage import append_sent_opportunities, ensure_data_files, load_seen, save_seen
from telegram import format_opportunity_message, send_telegram_message, telegram_configured


MAX_ALERTS_PER_RUN = 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and alert matching opportunities.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and score opportunities without sending Telegram messages or updating seen state.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    ensure_data_files()
    seen_ids = load_seen()

    collected = fetch_all_sources()
    scored = []
    for opportunity in collected:
        if opportunity["id"] in seen_ids:
            continue
        result = score_opportunity(opportunity)
        if result.score < MIN_SCORE:
            continue
        if not is_relevant_match(opportunity, result.matched_keywords):
            continue
        opportunity["score"] = result.score
        opportunity["matched_keywords"] = result.matched_keywords
        opportunity["why_it_fits"] = why_it_fits(opportunity, result.matched_keywords)
        scored.append(opportunity)

    top_matches = sorted(scored, key=lambda item: item.get("score", 0), reverse=True)[:MAX_ALERTS_PER_RUN]
    logging.info("Found %s new matches; alerting on top %s", len(scored), len(top_matches))

    if args.dry_run:
        for item in top_matches:
            logging.info("DRY RUN match: [%s] %s (%s)", item["score"], item["title"], item["link"])
        return 0

    if not top_matches:
        logging.info("No new matching opportunities to send.")
        return 0

    if not telegram_configured():
        logging.warning("Telegram credentials are missing; no alerts will be sent or marked seen.")
        return 0

    sent_items = []
    for opportunity in top_matches:
        message = format_opportunity_message(opportunity)
        if send_telegram_message(message):
            sent_items.append(opportunity)
            seen_ids.add(opportunity["id"])
        else:
            logging.warning("Message was not sent for %s", opportunity["title"])

    if sent_items:
        append_sent_opportunities(sent_items)
        save_seen(seen_ids)
        logging.info("Saved %s sent opportunities.", len(sent_items))

    return 0


if __name__ == "__main__":
    sys.exit(main())
