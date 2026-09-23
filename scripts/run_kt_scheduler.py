from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kt_scheduler.service import run_scheduler


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the KT Scheduler Bot.")
    parser.add_argument(
        "input_path",
        nargs="?",
        default=None,
        help=(
            "Path to CSV/XLSX KT plan file. If omitted, uses "
            "KT_SCHEDULER_DEFAULT_INPUT_PATH."
        ),
    )
    dry_run_group = parser.add_mutually_exclusive_group()
    dry_run_group.add_argument(
        "--send",
        action="store_true",
        help=(
            "Force a real SMTP send for this run, overriding KT_SCHEDULER_DRY_RUN "
            "from .env."
        ),
    )
    dry_run_group.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Force dry-run for this run, overriding KT_SCHEDULER_DRY_RUN from "
            ".env."
        ),
    )
    parser.add_argument(
        "--live-recipients",
        action="store_true",
        help=(
            "Deprecated/no-op: live recipients from the KT file are now the default."
        ),
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Redirect all invites to KT_SCHEDULER_TEST_RECIPIENTS.",
    )
    parser.add_argument(
        "--force-resend",
        action="store_true",
        help="Send even when the invite UID already exists in scheduler state.",
    )
    args = parser.parse_args()

    # Only force dry_run to a specific value when the caller explicitly asks
    # via --send or --dry-run. Otherwise leave it as None so run_scheduler()
    # falls back to KT_SCHEDULER_DRY_RUN from .env / the environment.
    if args.send:
        resolved_dry_run: bool | None = False
    elif args.dry_run:
        resolved_dry_run = True
    else:
        resolved_dry_run = None

    # --test-mode is a store_true flag, so it can only ever force test mode
    # *on*. Leave it as None (defer to .env) when the flag isn't passed, so
    # KT_SCHEDULER_TEST_MODE=false in .env isn't silently overridden.
    resolved_test_mode = True if args.test_mode else None

    result = run_scheduler(
        args.input_path,
        dry_run=resolved_dry_run,
        test_mode=resolved_test_mode,
        force_resend=args.force_resend,
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
