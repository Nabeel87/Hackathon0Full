"""
mcp_servers/email_server.py — Email MCP Server (Silver Tier)
=============================================================
Send and draft emails via the Gmail API, reusing the same OAuth2
credentials as gmail_watcher.py.

The Gmail OAuth token must include the 'gmail.send' scope.  If the
existing token only has 'gmail.readonly', delete .credentials/token.json
and re-authorise — the browser flow in _get_service() will request both
scopes automatically.

Public API
----------
  send_email(to, subject, body, attachments, vault_path)  → dict
  draft_email(to, subject, body, attachments, vault_path) → str (file path)
  test_send_email()                                        → dict

CLI
---
  python mcp_servers/email_server.py --to x@y.com --subject "Hi" --body "Hello"
  python mcp_servers/email_server.py --draft --to x@y.com --subject "Hi" --body "Hello"
  python mcp_servers/email_server.py --test
"""

import argparse
import base64
import logging
import mimetypes
import re
import sys
from datetime import datetime, timedelta, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────

# Combined scopes: read (used by GmailWatcher) + send (used here).
# If the token on disk was issued for readonly only, delete token.json
# and re-run — the flow below will request both scopes.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

DEFAULT_CREDENTIALS_DIR = (
    _PROJECT_ROOT / ".credentials"
)

DEFAULT_VAULT = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)

LOG_DIR  = _PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "email_sent.log"

# Simple regex for basic email address sanity check
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# ── Logger ────────────────────────────────────────────────────────────────────

def _build_logger() -> logging.Logger:
    """
    Shared email_server logger.
    Log file: logs/email_sent.log  (project root).
    Format: [timestamp] [SUCCESS/FAILED] To: xxx | Subject: xxx
    Body and credentials are never logged.
    """
    logger = logging.getLogger("email_server")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    log_fmt = logging.Formatter(
        "[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_fmt = logging.Formatter(
        "[%(asctime)s] [email_server] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(log_fmt)
    logger.addHandler(fh)

    return logger


def _log_outcome(
    logger: logging.Logger,
    success: bool,
    to: str,
    subject: str,
    extra: str = "",
) -> None:
    """Write a structured outcome line.  Body is never included."""
    status = "SUCCESS" if success else "FAILED"
    line   = f"[{status}] To: {to} | Subject: {subject[:60]}"
    if extra:
        line += f" | {extra}"
    logger.info(line)


# ── Gmail service ─────────────────────────────────────────────────────────────

def _get_service(credentials_dir: Path, logger: logging.Logger):
    """
    Build and return an authenticated Gmail API service object.

    Flow:
      1. Try to load token.json from credentials_dir.
      2. If expired but refreshable → auto-refresh.
      3. If still invalid → open browser OAuth2 flow (requires credentials.json).
      4. Save refreshed/new token back to token.json.
    """
    try:
        from google.auth.exceptions import TransportError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google API libraries not installed.\n"
            "Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    credentials_file = credentials_dir / "credentials.json"
    token_file       = credentials_dir / "token.json"

    if not credentials_file.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {credentials_file}\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs."
        )

    creds = None

    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as exc:
            logger.warning("Could not load token.json: %s — re-authorising.", exc)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing Gmail access token…")
                creds.refresh(Request())
                logger.info("Token refreshed successfully.")
            except TransportError as exc:
                raise RuntimeError(f"Token refresh failed (network error): {exc}") from exc
            except Exception as exc:
                logger.warning("Token refresh failed: %s — re-authorising.", exc)
                creds = None

        if not creds or not creds.valid:
            logger.info("Opening browser for Gmail authorisation (send scope required)…")
            flow  = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
            creds = flow.run_local_server(port=0)

        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Token saved → %s", token_file)

    return build("gmail", "v1", credentials=creds)


# ── Email construction ────────────────────────────────────────────────────────

def _build_mime_message(
    to: str,
    subject: str,
    body: str,
    attachments: list[str | Path] | None,
    logger: logging.Logger,
) -> MIMEMultipart:
    """
    Assemble a MIME multipart message with optional file attachments.
    Raises ValueError for missing attachment files.
    """
    msg            = MIMEMultipart()
    msg["To"]      = to
    msg["Subject"] = subject

    # Detect HTML body
    body_type = "html" if body.lstrip().startswith("<") else "plain"
    msg.attach(MIMEText(body, body_type, "utf-8"))

    if attachments:
        for raw_path in attachments:
            file_path = Path(raw_path)
            if not file_path.exists():
                raise ValueError(f"Attachment file not found: {file_path}")

            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type:
                main_type, sub_type = mime_type.split("/", 1)
            else:
                main_type, sub_type = "application", "octet-stream"

            part = MIMEBase(main_type, sub_type)
            part.set_payload(file_path.read_bytes())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=file_path.name,
            )
            msg.attach(part)
            logger.info("Attachment added: %s (%s/%s)", file_path.name, main_type, sub_type)

    return msg


def _encode_message(msg: MIMEMultipart) -> str:
    """Base64-URL-encode a MIME message for the Gmail API raw field."""
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_recipients(to: str) -> list[str]:
    """
    Split comma-separated recipients and validate each address.
    Returns the list of addresses; raises ValueError on the first bad one.
    """
    addresses = [addr.strip() for addr in to.split(",") if addr.strip()]
    if not addresses:
        raise ValueError("No recipient email address provided.")
    for addr in addresses:
        if not _EMAIL_RE.fullmatch(addr):
            raise ValueError(f"Invalid email address: {addr!r}")
    return addresses


# ── Public API ────────────────────────────────────────────────────────────────

def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list | None = None,
    vault_path: str | Path | None = None,
    credentials_dir: str | Path | None = None,
) -> dict:
    """
    Send an email via the Gmail API.

    Parameters
    ----------
    to              : Recipient address(es), comma-separated for multiple.
    subject         : Email subject line.
    body            : Email body — plain text or HTML (auto-detected).
    attachments     : Optional list of file paths to attach.
    vault_path      : Unused (kept for API compatibility); logs go to logs/.
    credentials_dir : Override for .credentials/ directory.

    Returns
    -------
    dict:
        success     (bool)
        message_id  (str | None)
        sent_to     (str)
        timestamp   (str — ISO UTC)
        error       (str | None)
    """
    logger   = _build_logger()
    creds_dir = Path(credentials_dir) if credentials_dir else DEFAULT_CREDENTIALS_DIR
    now_iso  = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def _fail(error_msg: str) -> dict:
        _log_outcome(logger, False, to, subject, f"error: {error_msg}")
        return {
            "success":    False,
            "message_id": None,
            "sent_to":    to,
            "timestamp":  now_iso,
            "error":      error_msg,
        }

    logger.info("Preparing email | To: %s | Subject: %s", to, subject[:60])

    # ── Validate recipients ───────────────────────────────────────────────────
    try:
        _validate_recipients(to)
    except ValueError as exc:
        return _fail(str(exc))

    # ── Validate attachments exist before touching the API ────────────────────
    if attachments:
        for raw_path in attachments:
            if not Path(raw_path).exists():
                return _fail(f"Attachment file not found: {raw_path}")

    # ── Build Gmail service ───────────────────────────────────────────────────
    try:
        service = _get_service(creds_dir, logger)
    except FileNotFoundError as exc:
        return _fail(f"Gmail credentials not found: {exc}")
    except RuntimeError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(f"Gmail service setup failed: {exc}")

    # ── Assemble MIME message ─────────────────────────────────────────────────
    try:
        mime_msg = _build_mime_message(to, subject, body, attachments, logger)
    except ValueError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(f"Message construction failed: {exc}")

    # ── Send ──────────────────────────────────────────────────────────────────
    try:
        from googleapiclient.errors import HttpError

        raw = _encode_message(mime_msg)
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )

        message_id = sent.get("id")
        _log_outcome(logger, True, to, subject, f"message_id={message_id}")
        return {
            "success":    True,
            "message_id": message_id,
            "sent_to":    to,
            "timestamp":  now_iso,
            "error":      None,
        }

    except Exception as exc:
        # Extract a clean error string from HttpError or generic exceptions
        try:
            from googleapiclient.errors import HttpError
            if isinstance(exc, HttpError):
                error_msg = f"Gmail API error {exc.resp.status}: {exc._get_reason()}"
            else:
                error_msg = str(exc)
        except Exception:
            error_msg = str(exc)

        return _fail(error_msg)


def draft_email(
    to: str,
    subject: str,
    body: str,
    attachments: list | None = None,
    vault_path: str | Path | None = None,
) -> str:
    """
    Create an email draft approval file in Pending_Approval/.

    The human reviewer moves the file to Approved/ to trigger sending,
    or to Rejected/ to cancel — following the same HITL pattern as
    the LinkedIn poster.

    Returns the absolute path of the created draft file as a string.
    """
    vault = Path(vault_path) if vault_path else DEFAULT_VAULT
    pending_dir = vault / "Pending_Approval"
    pending_dir.mkdir(parents=True, exist_ok=True)

    now     = datetime.now(tz=timezone.utc)
    expires = now + timedelta(hours=24)
    ts      = now.strftime("%Y%m%d_%H%M%S")

    draft_file = pending_dir / f"EMAIL_DRAFT_{ts}.md"

    # Avoid filename collision in the same second
    counter = 1
    while draft_file.exists():
        draft_file = pending_dir / f"EMAIL_DRAFT_{ts}_{counter}.md"
        counter += 1

    attachment_lines = (
        "\n".join(f"- {p}" for p in attachments)
        if attachments
        else "None"
    )

    content = (
        f"---\n"
        f"action_type: send_email\n"
        f"created: {now.strftime('%Y-%m-%dT%H:%M:%S')}\n"
        f"expires: {expires.strftime('%Y-%m-%dT%H:%M:%S')}\n"
        f"status: pending\n"
        f"priority: normal\n"
        f"sent_to: \"{to}\"\n"
        f"subject: \"{subject}\"\n"
        f"---\n"
        f"\n"
        f"# APPROVAL REQUIRED: Send Email\n"
        f"\n"
        f"## Email Details\n"
        f"**To:** {to}  \n"
        f"**Subject:** {subject}\n"
        f"\n"
        f"## Email Body\n"
        f"\n"
        f"{body}\n"
        f"\n"
        f"## Attachments\n"
        f"\n"
        f"{attachment_lines}\n"
        f"\n"
        f"## To Approve\n"
        f"Move this file to: Approved/\n"
        f"\n"
        f"## To Reject\n"
        f"Move this file to: Rejected/ (add rejection reason below)\n"
        f"\n"
        f"## Rejection Reason (if rejected)\n"
        f"[Human adds reason here]\n"
        f"\n"
        f"## Auto-Reject\n"
        f"This approval expires in 24 hours and will auto-reject if not decided.\n"
    )

    draft_file.write_text(content, encoding="utf-8")
    _build_logger().info(
        "Draft created: %s | To: %s | Subject: %s", draft_file.name, to, subject[:60]
    )
    return str(draft_file)


# ── Test helper ───────────────────────────────────────────────────────────────

def test_send_email() -> dict:
    """
    Send a fixed test email (non-interactive).
    Reads the recipient from the GMAIL_TEST_RECIPIENT env var if set,
    otherwise sends to the authenticated account itself (a safe self-test).

    Run:  python mcp_servers/email_server.py --test
    """
    import os

    recipient = os.getenv("GMAIL_TEST_RECIPIENT", "me")
    result = send_email(
        to=recipient,
        subject="Test Email from AI Employee",
        body="This is a test email sent via Gmail API by the AI Employee email_server.",
    )
    print(f"Result: {result}")
    return result


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Employee Email MCP Server — send or draft emails via Gmail API"
    )
    parser.add_argument("--to",      type=str, default="",  help="Recipient email(s), comma-separated")
    parser.add_argument("--subject", type=str, default="",  help="Email subject")
    parser.add_argument("--body",    type=str, default="",  help="Email body (plain text or HTML)")
    parser.add_argument(
        "--attachments",
        type=str, nargs="*", default=None,
        help="One or more file paths to attach",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Create a Pending_Approval draft instead of sending immediately",
    )
    parser.add_argument(
        "--vault",
        type=str,
        default=str(DEFAULT_VAULT),
        help="Path to AI_Employee_Vault",
    )
    parser.add_argument(
        "--credentials",
        type=str,
        default=str(DEFAULT_CREDENTIALS_DIR),
        help="Path to .credentials/ directory",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a fixed test email (non-interactive)",
    )
    args = parser.parse_args()

    if args.test:
        test_send_email()

    elif args.draft:
        if not args.to or not args.subject or not args.body:
            parser.error("--draft requires --to, --subject, and --body")
        path = draft_email(
            to=args.to,
            subject=args.subject,
            body=args.body,
            attachments=args.attachments,
            vault_path=args.vault,
        )
        print(f"Draft created: {path}")

    elif args.to and args.subject and args.body:
        result = send_email(
            to=args.to,
            subject=args.subject,
            body=args.body,
            attachments=args.attachments,
            vault_path=args.vault,
            credentials_dir=args.credentials,
        )
        for key, value in result.items():
            print(f"  {key:<12}: {value}")

    else:
        parser.print_help()
