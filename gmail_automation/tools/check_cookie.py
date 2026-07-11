#!/usr/bin/env python3

from __future__ import annotations

import argparse

import json

import sys

import time

from pathlib import Path

from gmail_automation import GmailSession

from gmail_automation.gmail_cookie import count_roblox_letters, diagnose_gmail

def main() -> int:

    p = argparse.ArgumentParser(description="Gmail cookie health check")

    p.add_argument("cookie", type=Path, help="Path to cookie .txt bundle")

    p.add_argument("--headless", action="store_true", default=True)

    p.add_argument("--no-headless", action="store_false", dest="headless")

    p.add_argument("--json", action="store_true", help="Print JSON result")

    args = p.parse_args()

    if not args.cookie.is_file():

        print(f"file not found: {args.cookie}", file=sys.stderr)

        return 2

    t0 = time.time()

    result = {

        "cookie": str(args.cookie),

        "status": "ERROR",

        "email": "",

        "auth": "",

        "roblox_letters": 0,

        "reason": "",

        "seconds": 0.0,

    }

    session = GmailSession(args.cookie, headless=args.headless, log=print)

    try:

        auth, email, rows = session.open()

        diag = diagnose_gmail(session.driver)

        rbx = count_roblox_letters(rows)

        if diag.get("ok"):

            result.update(

                status="ALIVE",

                email=email,

                auth=auth,

                roblox_letters=rbx,

            )

        else:

            result.update(

                status="DEAD",

                email=email,

                auth=auth,

                roblox_letters=rbx,

                reason=str(diag.get("reason") or "unknown"),

            )

    except Exception as e:

        result["reason"] = str(e)[:300]

    finally:

        session.close()

        result["seconds"] = round(time.time() - t0, 1)

    if args.json:

        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:

        print(

            f"{result['status']:8} {result['email'] or '-':40} "

            f"rbx={result['roblox_letters']} auth=u{result['auth'] or '-'} "

            f"({result['seconds']}s)"

        )

        if result["reason"]:

            print(f"  reason: {result['reason']}")

    return 0 if result["status"] == "ALIVE" else 1

if __name__ == "__main__":

    raise SystemExit(main())
