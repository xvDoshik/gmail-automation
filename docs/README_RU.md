[EN](../README.md) | RU

## gmail-automation 📧

Standalone Gmail browser automation - без зависимости от `work/` и `retriever-shared`.

## ✨ Features

- **Вход по cookies** 🔑 - Netscape cookie bundle
- **Поиск писем Roblox** 📬 - inbox + spam через Gmail search URL
- **Poll recovery-кода** ⏱️ - после send-code
- **Диагностика мёртвых cookies** 🩺 - `cookiemismatch`, `signin_redirect`, …
- **Отключение conversation view** ⚙️ - стабильный парсинг

## 🚀 Quick start

```bash
cd ~/Desktop/gmail-automation
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Нужен Google Chrome.

## 📋 Commands

Проверка cookie:

```bash
gmail-check /path/to/cookie.txt
gmail-check /path/to/cookie.txt --json
gmail-check /path/to/cookie.txt --no-headless
```

Poll recovery-кода (после send-code на Roblox):

```bash
gmail-poll /path/to/cookie.txt --reset-now --timeout 120
```

## 🐍 Python API

```python
from pathlib import Path
from gmail_automation import GmailSession

with GmailSession(Path("cookie.txt"), headless=True) as session:
    auth, email, rows = session.auth, session.email, session.rows
    print(email, len(rows))
    code, body, html = session.poll_recovery_code(reset_ms=..., timeout_s=90)
```

Низкоуровневые функции - в `gmail_automation.gmail_cookie`.

## 📁 Structure

```
gmail-automation/
  gmail_automation/
    gmail_cookie.py   # ядро: driver, inject, poll, spam search
    mail_parse.py     # парсинг писем Roblox
    proxy.py          # Chrome proxy extension
    session.py        # GmailSession wrapper
    tools/
      check_cookie.py
      poll_recovery.py
```
