#!/usr/bin/env python3

from __future__ import annotations

import argparse

import sys

import time

from pathlib import Path

from gmail_automation import GmailSession

def main() -> int:

    p = argparse.ArgumentParser(description="Poll Roblox recovery code from Gmail")

    p.add_argument("cookie", type=Path, help="Path to cookie .txt bundle")

    p.add_argument("--timeout", type=float, default=120.0, help="Poll timeout seconds")

    p.add_argument("--headless", action="store_true", default=True)

    p.add_argument("--no-headless", action="store_false", dest="headless")

    p.add_argument(

        "--reset-now",

        action="store_true",

        help="Treat reset as now (use right after send-code)",

    )

    args = p.parse_args()

    if not args.cookie.is_file():

        print(f"file not found: {args.cookie}", file=sys.stderr)

        return 2

    reset_ms = int(time.time() * 1000) if args.reset_now else None

    session = GmailSession(args.cookie, headless=args.headless, log=print)

    try:

        session.open()

        code, body, html = session.poll_recovery_code(

            reset_ms=reset_ms,

            timeout_s=args.timeout,

        )

        if code:

            print(f"CODE={code}")

            return 0

        from gmail_automation import get_last_poll_abort_reason

        reason = get_last_poll_abort_reason() or "NO_CODE"

        print(f"FAIL: {reason}")

        return 1

    finally:

        session.close()

if __name__ == "__main__":

    raise SystemExit(main())
