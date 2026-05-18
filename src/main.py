"""Main entry point for the GitHub Actions Telegram opportunity alert bot."""

from __future__ import annotations

import argparse
import logging
import sys

from scoring import FUNDING_MIN_SCORE, MIN_SCORE, is_relevant_match, score_opportunity, why_it_fits
from sources import fetch_all_sources
from storage import append_sent_opportunities, ensure_data_files, load_seen, save_seen
from telegram import format_opportunity_message, format_run_summary, send_telegram_message, telegram_configured


MAX_JOB_ALERTS_PER_RUN = 10
MAX_FUNDING_ALERTS_PER_RUN = 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and alert matching opportunities.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and score opportunities without sending Telegram messages or updating seen state.",
    )
    parser.add_argument(
        "--ignore-seen",
        action="store_true",
        help="Ignore data/seen.json so manual test runs can resend top matches.",
    )
    parser.add_argument(
        "--send-summary",
        action="store_true",
        help="Send a Telegram summary even when no opportunity alerts are sent.",
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a short Telegram test message and exit.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    ensure_data_files()
    if args.test_telegram:
        if send_telegram_message("✅ Engocha opportunity alert bot Telegram test succeeded."):
            logging.info("Telegram test message sent successfully.")
            return 0
        logging.error("Telegram test message failed.")
        return 1

    seen_ids = load_seen()

    collected = fetch_all_sources()
    scored = []
    stats = {
        "collected": len(collected),
        "already_seen": 0,
        "below_score": 0,
        "not_relevant": 0,
        "new_matches": 0,
        "new_job_matches": 0,
        "new_funding_matches": 0,
        "sent": 0,
        "job_alerts_sent": 0,
        "funding_alerts_sent": 0,
    }
    for opportunity in collected:
        if not args.ignore_seen and opportunity["id"] in seen_ids:
            stats["already_seen"] += 1
            continue
        result = score_opportunity(opportunity)
        minimum_score = FUNDING_MIN_SCORE if opportunity.get("type") == "funding" else MIN_SCORE
        if result.score < minimum_score:
            stats["below_score"] += 1
            continue
        if not is_relevant_match(opportunity, result.matched_keywords):
            stats["not_relevant"] += 1
            continue
        opportunity["score"] = result.score
        opportunity["matched_keywords"] = result.matched_keywords
        opportunity["why_it_fits"] = why_it_fits(opportunity, result.matched_keywords)
        scored.append(opportunity)

    job_matches = [item for item in scored if item.get("type") == "job"]
    funding_matches = [item for item in scored if item.get("type") == "funding"]
    top_job_matches = sorted(job_matches, key=lambda item: item.get("score", 0), reverse=True)[:MAX_JOB_ALERTS_PER_RUN]
    top_funding_matches = sorted(funding_matches, key=lambda item: item.get("score", 0), reverse=True)[
        :MAX_FUNDING_ALERTS_PER_RUN
    ]
    top_matches = top_job_matches + top_funding_matches
    stats["new_matches"] = len(scored)
    stats["new_job_matches"] = len(job_matches)
    stats["new_funding_matches"] = len(funding_matches)
    logging.info(
        "Found %s new matches (%s jobs, %s funding); alerting on %s jobs and %s funding",
        len(scored),
        len(job_matches),
        len(funding_matches),
        len(top_job_matches),
        len(top_funding_matches),
    )
    logging.info(
        "Run stats: collected=%s already_seen=%s below_score=%s not_relevant=%s new_matches=%s job_matches=%s funding_matches=%s",
        stats["collected"],
        stats["already_seen"],
        stats["below_score"],
        stats["not_relevant"],
        stats["new_matches"],
        stats["new_job_matches"],
        stats["new_funding_matches"],
    )

    if args.dry_run:
        for item in top_matches:
            logging.info("DRY RUN match: [%s] %s (%s)", item["score"], item["title"], item["link"])
        return 0

    if not top_matches:
        logging.info("No new matching opportunities to send.")
        if args.send_summary and telegram_configured():
            send_telegram_message(format_run_summary(stats))
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
            if opportunity.get("type") == "funding":
                stats["funding_alerts_sent"] += 1
            else:
                stats["job_alerts_sent"] += 1
        else:
            logging.warning("Message was not sent for %s", opportunity["title"])

    if sent_items:
        stats["sent"] = len(sent_items)
        append_sent_opportunities(sent_items)
        save_seen(seen_ids)
        logging.info("Saved %s sent opportunities.", len(sent_items))

    if args.send_summary and telegram_configured():
        send_telegram_message(format_run_summary(stats))

    return 0


if __name__ == "__main__":
    sys.exit(main())
