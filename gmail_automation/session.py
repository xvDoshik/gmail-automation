
from __future__ import annotations

import time

from pathlib import Path

from typing import Callable

from selenium.webdriver.support.ui import WebDriverWait

from gmail_automation.gmail_cookie import (

    cleanup_profile,

    count_roblox_letters,

    create_gmail_driver,

    diagnose_gmail,

    fetch_roblox_mail_rows,

    inject_cookies,

    make_temp_profile,

    parse_cookie_bundle,

    poll_roblox_code,

    resolve_gmail_auth_for_email,

    wait_gmail_ready,

)

class GmailSession:

    def __init__(

        self,

        cookie_path: Path | str,

        *,

        headless: bool = False,

        proxy: dict[str, str] | None = None,

        log: Callable[[str], None] | None = None,

    ) -> None:

        self.cookie_path = Path(cookie_path)

        self.headless = headless

        self.proxy = proxy

        self.log = log or (lambda _m: None)

        self._profile: str | None = None

        self.driver = None

        self.wait: WebDriverWait | None = None

        self.auth: str = "0"

        self.email: str = ""

        self.rows: list[dict] = []

    def open(self) -> tuple[str, str, list[dict]]:

        header_email, ident, cookies = parse_cookie_bundle(self.cookie_path)

        expected = (header_email or "").strip().lower()

        prefer = str(ident or "0")

        self._profile = make_temp_profile()

        self.driver = create_gmail_driver(

            headless=self.headless,

            tmp_profile=self._profile,

            session_proxy=self.proxy,

        )

        self.wait = WebDriverWait(self.driver, 30)

        inject_cookies(self.driver, cookies, log=self.log, prefer_auth=prefer)

        self.driver.get(f"https://mail.google.com/mail/u/{prefer}/#inbox")

        wait_gmail_ready(self.driver, 10.0)

        time.sleep(1.5)

        auth, email, merged, reason = resolve_gmail_auth_for_email(

            self.driver,

            self.wait,

            expected,

            prefer_auth=prefer,

            log=self.log,

        )

        if not auth:

            raise RuntimeError(reason or "GMAIL_OPEN_FAILED")

        self.auth = auth

        self.email = email

        self.rows = merged

        self.log(

            f"gmail open auth=u{auth} email={email} "

            f"roblox_letters={count_roblox_letters(merged)}"

        )

        return auth, email, merged

    def diagnose(self) -> dict:

        if not self.driver:

            return {"ok": False, "reason": "not_open"}

        return diagnose_gmail(self.driver)

    def refresh_roblox_rows(self, limit: int = 50) -> list[dict]:

        if not self.driver or not self.wait:

            raise RuntimeError("session not open")

        self.rows = fetch_roblox_mail_rows(

            self.driver, self.wait, self.auth, limit, log=self.log

        )

        return self.rows

    def poll_recovery_code(

        self,

        *,

        reset_ms: int | None = None,

        timeout_s: float = 120.0,

        gentle: bool = True,

    ) -> tuple[str | None, str, str]:

        if not self.driver or not self.wait:

            raise RuntimeError("session not open")

        from gmail_automation.gmail_cookie import (

            baseline_seen_subjects,

            roblox_baseline_ms,

        )

        baseline_ms = roblox_baseline_ms(self.rows)

        seen = baseline_seen_subjects(self.rows)

        now_ms = int(time.time() * 1000)

        reset = reset_ms if reset_ms is not None else now_ms

        min_ms = reset - 8000

        return poll_roblox_code(

            self.driver,

            self.wait,

            self.auth,

            baseline_ms,

            seen,

            min_ms=min_ms,

            reset_ms=reset,

            log=self.log,

            timeout_s=timeout_s,

            gentle=gentle,

        )

    def close(self) -> None:

        if self.driver:

            try:

                self.driver.quit()

            except Exception:

                pass

            self.driver = None

        if self._profile:

            cleanup_profile(self._profile)

            self._profile = None

    def __enter__(self) -> GmailSession:

        self.open()

        return self

    def __exit__(self, *_args) -> None:

        self.close()
