"""The `jev-qa` command: run one spec and print the verdict.

    uv run jev-qa qa/specs/login.json            # -> qa/runs/login/<ts>/result.json + trace.json
    uv run jev-qa qa/specs/login.json --headed   # watch the browser
    uv run jev-qa qa/specs/login.json --check    # validate the spec only, no browser, no API

Exit codes: 0 = pass · 1 = any other verdict · 2 = never a verdict (a spec, key, browser or
start-page problem).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv

from jev_qa.report import render
from jev_qa.runner import RunnerUnavailable, run
from jev_qa.spec import SpecError, load_spec


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="jev-qa", description="Run a QA spec: Jev chooses, Playwright executes."
    )
    p.add_argument("spec", help="path to a spec .json")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.add_argument(
        "--out", default="qa/runs", help="where result.json, trace.json and screenshots go"
    )
    p.add_argument("--screenshots", choices=["key", "all", "none"], default="key")
    p.add_argument("--max-steps", type=int, help="override the spec's max_steps")
    p.add_argument("--model", help="TypeSafe model id (default: TYPESAFE_MODEL or jev-latest)")
    p.add_argument("--check", action="store_true", help="validate the spec and exit")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    try:
        spec = load_spec(args.spec)
    except SpecError as e:
        print(f"spec problem: {e}", file=sys.stderr)
        return 2
    if args.max_steps:
        spec = spec.model_copy(update={"max_steps": args.max_steps})
    if args.check:
        print(
            f"spec OK: {spec.id} · {len(spec.outcomes)} outcomes"
            f" · {len(spec.assertions)} assertions"
        )
        return 0
    try:
        result = asyncio.run(
            run(
                spec,
                headed=args.headed,
                out_dir=args.out,
                screenshots=args.screenshots,
                model=args.model,
            )
        )
    except RunnerUnavailable as e:
        print(f"could not run: {e}", file=sys.stderr)
        return 2
    print(render(result))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
