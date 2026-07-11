import re

from dataclasses import dataclass

ROBLOX_SENDER_RE = re.compile(r"roblox|no-reply@roblox", re.I)

REVERT_LINK_RE = re.compile(

    r"https?://(?:www\.)?roblox\.com/(?:[a-z]{2}/)?"

    r"(?:login/revertAccount|account/settings/revert-account)\?[^\"'\s<>]+",

    re.I,

)

USERNAME_IN_MAIL_RE = re.compile(

    r"(?:username|user name|логин|account)[:\s]+([A-Za-z0-9_]{3,20})",

    re.I,

)

_ROBLOX_SUBJECT_USER_RE = re.compile(

    r"(?:^|\n)Roblox\s+(?:2-Step Verification|Login Request|Password Reset|One-Time Login|"

    r"Account Recovery|Email Verification|Email Reset|Parental Email Validation)"

    r"(?:\s+Request)?[:\s]+([A-Za-z0-9_]{3,20})\b",

    re.I,

)

_ROBLOX_SUBJECT_TAIL_RE = re.compile(

    r"^Roblox(?:\s+[\w\s]{2,40})?:\s*([A-Za-z0-9_]{3,20})\s*$",

    re.I | re.M,

)

_ROBLOX_LOGIN_FOR_RE = re.compile(

    r"(?:New login for|login for|Novo login para|nuevo login para|"

    r"nouvelle connexion pour|Nuevo inicio de sesión para)\s+([A-Za-z0-9_]{3,20})\b",

    re.I,

)

_LOCALIZED_SUBJECT_USER_RE = re.compile(

    r"(?:Solicitud de inicio de sesión de Roblox|Yêu cầu đăng nhập Roblox|"

    r"Xác minh 2 bước Roblox|Xác Thực Email Roblox|Verificação de e-mail Roblox|"

    r"Đặ Lại Email Roblox|Validación de correo electrónico de Roblox|"

    r"Verificación de correo electrónico de Roblox|"

    r"conta Roblox|cuenta Roblox)[:\s]+([A-Za-z0-9_]{3,20})\b",

    re.I,

)

_ROBLOX_PARA_RE = re.compile(

    r"(?:Intento de gasto de Robux para|gasto de Robux para)\s+([A-Za-z0-9_]{3,20})\b",

    re.I,

)

_ACCOUNT_FOR_RE = re.compile(

    r"(?:for your Roblox account|your Roblox account|Roblox account)[:\s]+"

    r"([A-Za-z0-9_]{3,20})\b",

    re.I,

)

_CJK_ACCOUNT_RE = re.compile(

    r"Roblox\s*(?:帳號|账号|アカウント)\s*([A-Za-z0-9_]{3,20})\b",

    re.I,

)

_ROBLOX_LOCALIZED_RE = re.compile(

    r"(?:conta Roblox|cuenta Roblox|compte Roblox|senha Roblox requisitada|"

    r"entrada na conta Roblox)[:\s]+([A-Za-z0-9_]{3,20})\b",

    re.I,

)

_ROBLOX_FOR_RE = re.compile(

    r"(?:Roblox (?:for|para|pour|für)|da Roblox para)\s+([A-Za-z0-9_]{3,20})\b",

    re.I,

)

CODE_6_RE = re.compile(r"\b(\d{6})\b")

_TWOFA_MARKERS: tuple[str, ...] = (

    "2-step",

    "two-step",

    "two step",

    "2fa",

    "2sv",

    "security code",

    "verification code",

    "one-time code",

    "login code for",

    "verificación en dos pasos",

    "verificacion en dos pasos",

    "código de verificación en dos pasos",

    "codigo de verificacion en dos pasos",

    "solicitud de verificación en dos pasos",

    "solicitud de verificacion en dos pasos",

    "verificación en dos pasos con correo",

    "verificação em duas etapas",

    "verificacao em duas etapas",

    "código de verificação em duas etapas",

    "codigo de verificacao em duas etapas",

    "vérification en deux étapes",

    "verification en deux etapes",

    "vérification en 2 étapes",

    "code de vérification",

    "code de verification",

    "zweistufige verifizierung",

    "zweistufige authentifizierung",

    "zweistufig",

    "zwei-faktor",

    "sicherheitscode",

    "verifica in due passaggi",

    "verifica a due fattori",

    "codice di verifica",

    "codice di sicurezza",

    "weryfikacja dwuetapowa",

    "weryfikacji dwuetapowej",

    "kod weryfikacji",

    "kod bezpieczeństwa",

    "kod bezpieczenstwa",

    "двухшагов",

    "двухэтапн",

    "двухфакторн",

    "код безопасности",

    "xác minh 2 bước",

    "mã xác minh 2 bước",

    "xác thực 2 bước",

    "mã xác nhận",

    "التحقق بخطوتين",

    "رمز التحقق بخطوتين",

    "تحقق بخطوتين",

    "عملية التحقق بخطوتين",

    "iki adımlı doğrulama",

    "iki adimli dogrulama",

    "iki faktörlü",

    "güvenlik kodu",

    "guvenlik kodu",

    "doğrulama kodu",

    "dogrulama kodu",

    "verifikasi dua langkah",

    "verifikasi 2 langkah",

    "kode verifikasi",

    "kode keamanan",

    "การยืนยันตัวตนสองขั้นตอน",

    "รหัสยืนยันตัวตน",

    "ยืนยันตัวตนสองขั้น",

    "2단계 인증",

    "이중 인증",

    "2단계 확인",

    "二段階認証",

    "2段階認証",

    "二段階認証コード",

    "两步验证",

    "兩步驗證",

    "双重验证",

    "雙重驗證",

    "两步验证码",

    "兩步驗證碼",

    "tweestapsverificatie",

    "beveiligingscode",

    "tvåstegsverifiering",

    "tvastegsverifiering",

    "tofaktorgodkendelse",

    "to-trinns",

    "to trinns",

    "tofaktor",

    "kaksivaiheinen",

    "kaksivaiheinen tunnistus",

    "dvoufázové ověření",

    "dvoufazove overeni",

    "dvoustupňové ověření",

    "dvojfaktorové overenie",

    "dvojfaktorove overenie",

    "kétlépcsős",

    "ketlepcsos",

    "kétfaktoros",

    "verificare în doi pași",

    "verificare in doi pasi",

    "cod de securitate",

    "επιβεβαίωση δύο βημάτων",

    "κωδικός επαλήθευσης",

    "אימות דו-שלבי",

    "קוד אבטחה",

    "двофакторн",

    "двоетапн",

    "двокроков",

    "pengesahan dua langkah",

    "kod keselamatan",

    "दो-चरणीय सत्यापन",

    "दो चरण सत्यापन",

    "দুই-ধাপ প্রমাণীকরণ",

    "تأیید دو مرحله",

    "تایید دو مرحله",

    "verificació en dos passos",

    "verificacio en dos passos",

    "двустепенно потвърждение",

    "код за потвърждение",

    "dviejų veiksnių",

    "patvirtinimo kodas",

    "divpakāpju",

    "divpakapju",

    "kaheastmeline",

    "kaheastmeline autentimine",

    "dvofaktorska",

    "dvostruka provjera",

    "dvostruka provera",

    "dvostopenjsko",

    "dalawang-hakbang",

    "dalawahang-hakbang",

)

_PASSWORD_RESET_ONLY: tuple[str, ...] = (

    "password reset",

    "reset your password",

    "сброс пароля",

    "restablecimiento de contraseña",

    "redefinição de senha",

    "redefinicao de senha",

    "réinitialisation du mot de passe",

    "reinitialisation du mot de passe",

    "passwort zurücksetzen",

    "passwort zuruecksetzen",

    "hasło do twojego konta",

    "password del tuo account",

    "mot de passe de votre compte",

    "contraseña de roblox de tu cuenta",

    "passwort für dein roblox-konto",

    "password telah diubah",

    "password changed for your roblox account",

)

def _has_twofa_marker(blob: str) -> bool:

    return any(m in blob for m in _TWOFA_MARKERS)

def _is_password_reset_only(blob: str) -> bool:

    if not any(m in blob for m in _PASSWORD_RESET_ONLY):

        return False

    return not _has_twofa_marker(blob)

@dataclass

class ParsedMail:

    code: str | None = None

    usernames: list[str] | None = None

    revert_links: list[str] | None = None

def _blob(letter_text: str, letter_html: str) -> str:

    return f"{letter_text}\n{letter_html}"

def is_roblox_letter(sender: str, subject: str) -> bool:

    snd = (sender or "").lower()

    subj = (subject or "").lower()

    if any(

        x in snd

        for x in (

            "@roblox.com",

            "accounts@roblox",

            "noreply@roblox",

            "no-reply@roblox",

            "account-security@",

            "roblox password reset",

            "roblox no-reply",

        )

    ):

        return True

    if snd.strip().startswith("roblox") and ("<" in snd or "@" in snd):

        return True

    if "roblox" in subj and "roblox" in snd.split("<")[0]:

        return True

    return False

def is_revert_letter(subject: str, body: str) -> bool:

    blob = f"{subject}\n{body}".lower()

    return (

        "revert" in blob

        or "revertaccount" in blob

        or "revert-account" in blob

        or "revert account" in blob

    )

def is_2fa_status_notification_letter(subject: str, body: str) -> bool:

    subj = (subject or "").lower()

    blob = f"{subject}\n{body}".lower()

    enabled_markers = (

        "authenticator enabled",

        "authenticator has been enabled",

        "authenticator activated",

        "authenticator deactivated",

        "аутентificator включен",

        "аутентificator включена",

        "аутентификатор включен",

        "аутентификатор включена",

        "authenticator включен",

        "authenticator включена",

        "включена для аккаунта roblox",

        "enabled for your roblox account",

        "enabled for roblox account",

        "two-step verification is now enabled",

        "2-step verification is now enabled",

        "двухшаговая проверка включена",

    )

    if any(m in blob for m in enabled_markers):

        return True

    if "двухшаговая проверка" in subj and "включен" in blob:

        return True

    if "two-step verification" in subj and "enabled" in subj:

        head = blob[:700]

        if "code" not in head and "код" not in head and not CODE_6_RE.search(head):

            return True

    return False

def is_recovery_code_letter(subject: str, body: str) -> bool:

    subj = subject.lower()

    blob = body.lower()

    if is_2fa_status_notification_letter(subject, body):

        return False

    if "revert" in subj or "revert" in blob:

        return False

    if "email verification" in subj and "password" not in blob and "recovery" not in blob:

        return False

    markers = (

        "password reset",

        "reset your password",

        "account recovery",

        "recovery request",

        "verification code",

        "security code",

        "one-time code",

        "one time code",

        "one-time login",

        "код",

        "сброс пароля",

        "código de segurança",

        "mã xác minh",

        "xác minh 2 bước",

        "yêu cầu đăng nhập",

        "solicitud de inicio",

        "2-step verification code",

        "two-step verification code",

    )

    if any(m in subj or m in blob for m in markers):

        return True

    if CODE_6_RE.search(subject) and is_roblox_letter("", subject):

        return True

    return False

def is_2fa_code_letter(subject: str, body: str) -> bool:

    subj = (subject or "").lower()

    blob = f"{subject}\n{body}".lower()

    if "authenticator activated" in blob or "authenticator deactivated" in blob:

        return False

    if "activated for roblox account" in subj and "security code" not in blob[:500]:

        if "verification code" not in blob[:500] and "código de verificación" not in blob[:500]:

            return False

    if not _has_twofa_marker(blob):

        return False

    if _is_password_reset_only(blob):

        return False

    return True

def is_2fa_code_letter_for_login(

    subject: str, body: str, login: str, *, sender: str = ""

) -> bool:

    if not is_2fa_code_letter(subject, body):

        return False

    if sender and not is_roblox_letter(sender, subject):

        return False

    if not login:

        return True

    blob = f"{subject}\n{body}"

    login_l = login.lower()

    if login_l in subject.lower():

        return True

    for u in extract_usernames(blob):

        if u.lower() == login_l:

            return True

    return login_l in blob.lower()

def is_email_verify_letter(subject: str, body: str) -> bool:

    blob = f"{subject}\n{body}".lower()

    return any(

        x in blob

        for x in (

            "verify your email",

            "email verification",

            "confirm your email",

            "подтверд",

        )

    )

def is_email_verify_letter_for_login(

    subject: str, body: str, login: str, *, sender: str = ""

) -> bool:

    if not is_email_verify_letter(subject, body):

        return False

    if sender and not is_roblox_letter(sender, subject):

        return False

    if not login:

        return True

    blob = f"{subject}\n{body}"

    login_l = login.lower()

    if login_l in subject.lower():

        return True

    for u in extract_usernames(blob):

        if u.lower() == login_l:

            return True

    return login_l in blob.lower()

def extract_all_verification_codes(text: str) -> list[str]:

    if not text:

        return []

    seen: set[str] = set()

    out: list[str] = []

    for m in CODE_6_RE.finditer(text):

        c = m.group(1)

        if c not in seen and c != "000000":

            seen.add(c)

            out.append(c)

    return out

def extract_2fa_code(text: str) -> str | None:

    if not text:

        return None

    for line in text.splitlines():

        low = line.lower()

        if "recovery code" in low or "account recovery" in low:

            continue

        if "password reset" in low and "2-step" not in low and "two-step" not in low:

            continue

        if any(m in low for m in _TWOFA_MARKERS):

            m = CODE_6_RE.search(line)

            if m:

                return m.group(1)

    m = re.search(r"(\d{6})\s+—\s+твой код двухшаговой", text, re.I)

    if m:

        return m.group(1)

    return None

def _thread_parts(body: str, html: str) -> list[str]:

    full = f"{body}\n{html}".strip()

    if not full:

        return []

    return [p.strip() for p in full.split("---") if p.strip()]

def _part_is_recovery_blob(blob: str) -> bool:

    low = blob.lower()

    if "account recovery" in low[:240] or "recovery request" in low[:240]:

        return "2-step verification code" not in low and "two-step verification code" not in low

    return False

def collect_2fa_codes_from_thread(

    subject: str,

    body: str,

    html: str,

    pred,

) -> set[str]:

    codes: set[str] = set()

    subj = (subject or "").strip()

    for part in _thread_parts(body, html):

        if _part_is_recovery_blob(part):

            continue

        if pred and not pred(subj, part):

            continue

        c = extract_2fa_code(part) or extract_verification_code(part)

        if c:

            codes.add(c)

    return codes

def extract_2fa_code_from_thread(

    subject: str,

    body: str,

    html: str,

    pred,

    *,

    skip_codes: set[str] | None = None,

    newest_only: bool = False,

    min_parts: int = 1,

) -> tuple[str | None, str]:

    skip = skip_codes or set()

    subj = (subject or "").strip()

    parts = _thread_parts(body, html)

    if min_parts > 1 and len(parts) < min_parts:

        return None, ""

    ordered = list(reversed(parts)) if newest_only else parts

    for part in ordered:

        if _part_is_recovery_blob(part):

            continue

        if pred and not pred(subj, part):

            continue

        c = extract_2fa_code(part) or extract_verification_code(part)

        if c and c not in skip:

            return c, part

    return None, ""

def extract_verification_code(text: str) -> str | None:

    if not text:

        return None

    for pat in (

        re.compile(r"(\d{6})\s+is your Roblox Security Code", re.I),

        re.compile(r"(\d{6})\s+is your Roblox One-Time Code", re.I),

        re.compile(r"(\d{6})\s+is the your Roblox Security Code", re.I),

        re.compile(r"Roblox Security Code[:\s]*(\d{6})", re.I),

        re.compile(r"2-Step Verification Code[:\s]*(\d{6})", re.I),

        re.compile(r"Código de verificación en dos pasos[:\s]*(\d{6})", re.I),

        re.compile(r"Mã xác minh 2 bước[:\s]*(\d{6})", re.I),

        re.compile(r"رمز التحقق بخطوتين[:\s]*(\d{6})", re.I),

        re.compile(r"Kod weryfikacji[:\s]*(\d{6})", re.I),

        re.compile(r"Código de verificação[:\s]*(\d{6})", re.I),

        re.compile(r"Codice di verifica[:\s]*(\d{6})", re.I),

        re.compile(r"Güvenlik kodu[:\s]*(\d{6})", re.I),

        re.compile(r"Security Code[:\s]*(\d{6})", re.I),

        re.compile(r"(?:code|код|código)[:\s#*—-]*(\d{6})", re.I),

        re.compile(r"(\d{6})\s+—\s+твой одноразовый код", re.I),

        re.compile(r"(\d{6})\s+is your", re.I),

        re.compile(r"enter\s+(?:the\s+)?code\s+(\d{6})", re.I),

        re.compile(r"verification\s+code[:\s]*(\d{6})", re.I),

        re.compile(r"(\d{6})\s+é o seu código", re.I),

        CODE_6_RE,

    ):

        m = pat.search(text)

        if m:

            return m.group(1)

    return None

_USERNAME_BLOCKLIST = frozenset(

    {

        "roblox",

        "support",

        "account",

        "recovery",

        "request",

        "password",

        "reset",

        "security",

        "verify",

        "verification",

        "login",

        "email",

        "code",

        "hello",

        "authenticator",

    }

)

def extract_usernames(text: str) -> list[str]:

    found: list[str] = []

    seen: set[str] = set()

    lines = (text or "").splitlines()

    subject = lines[0] if lines else (text or "")

    chunks = [subject]

    if text and text != subject:

        chunks.append(text)

    patterns = (

        USERNAME_IN_MAIL_RE,

        _ROBLOX_SUBJECT_USER_RE,

        _ROBLOX_SUBJECT_TAIL_RE,

        _ROBLOX_LOGIN_FOR_RE,

        _LOCALIZED_SUBJECT_USER_RE,

        _ROBLOX_PARA_RE,

        _ACCOUNT_FOR_RE,

        _CJK_ACCOUNT_RE,

        _ROBLOX_LOCALIZED_RE,

        _ROBLOX_FOR_RE,

    )

    for chunk in chunks:

        for pat in patterns:

            for m in pat.finditer(chunk):

                u = m.group(1)

                if u.lower() in _USERNAME_BLOCKLIST or u in seen:

                    continue

                seen.add(u)

                found.append(u)

    if not found and subject and "roblox" in subject.lower():

        m = re.search(r":\s*([A-Za-z0-9_]{3,20})\s*$", subject)

        if m:

            u = m.group(1)

            if u.lower() not in _USERNAME_BLOCKLIST and u not in seen:

                found.append(u)

    return found

def extract_revert_links(text: str) -> list[str]:

    links = REVERT_LINK_RE.findall(text)

    out: list[str] = []

    seen: set[str] = set()

    for link in links:

        if link not in seen:

            seen.add(link)

            out.append(link)

    return out

def parse_letter(subject: str, text: str, html: str) -> ParsedMail:

    blob = _blob(text, html)

    return ParsedMail(

        code=extract_verification_code(blob) or extract_verification_code(subject),

        usernames=extract_usernames(blob),

        revert_links=extract_revert_links(blob),

    )
