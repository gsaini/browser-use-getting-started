"""Command line: `hn-digest --section show --count 10` (or `python -m hn_digest ...`)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from bu_starter.llm import MissingCredentials
from hn_digest.agent import SECTIONS, collect
from hn_digest.report import RunMeta, render_markdown, to_record
from hn_digest.verify import verify

EXIT_OK, EXIT_UNVERIFIED, EXIT_FAILED = 0, 1, 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hn-digest",
        description="Read a Hacker News listing with a browser-use agent, then verify it.",
    )
    parser.add_argument("--section", choices=sorted(SECTIONS), default="front")
    parser.add_argument("--count", type=int, default=10, help="stories to collect (1-30)")
    parser.add_argument("--topic", help="keep only stories about this topic, e.g. 'databases'")
    parser.add_argument("--out", type=Path, default=Path("digests"), help="output folder")
    parser.add_argument("--max-steps", type=int, default=25, help="hard cap on agent steps")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    args = parser.parse_args(argv)
    if not 1 <= args.count <= 30:
        parser.error("--count must be between 1 and 30")
    return args


async def run(args: argparse.Namespace) -> int:
    result = await collect(
        args.section,
        args.count,
        args.topic,
        headless=not args.headed,
        max_steps=args.max_steps,
    )
    if result.digest is None:
        errors = [e for e in result.history.errors() if e]
        print(f"The agent returned no digest. Last error: {errors[-1] if errors else 'none'}")
        return EXIT_FAILED

    checks = await verify(result.digest)
    usage = result.history.usage
    meta = RunMeta(
        section=args.section,
        topic=args.topic,
        model=result.model,
        steps=result.history.number_of_steps(),
        seconds=result.history.total_duration_seconds(),
        tokens=usage.total_tokens if usage else None,
        cost_usd=usage.total_cost if usage else None,
        generated_at=datetime.now(UTC),
    )

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"hn-{args.section}-{meta.generated_at:%Y%m%d-%H%M%S}"
    markdown = render_markdown(checks, meta)
    stem.with_suffix(".md").write_text(markdown, encoding="utf-8")
    stem.with_suffix(".json").write_text(
        json.dumps(to_record(checks, meta), indent=2), encoding="utf-8"
    )

    print("\n" + markdown)
    print(f"Saved {stem}.md and {stem}.json")
    return EXIT_OK if all(c.ok for c in checks) else EXIT_UNVERIFIED


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except MissingCredentials as exc:
        print(exc, file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
