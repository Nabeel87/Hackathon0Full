import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from watchers.base_watcher import BaseWatcher
from helpers.dashboard_updater import update_activity, update_component_status, update_stats

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

KEYWORDS = ["urgent", "asap", "invoice", "payment"]

DEFAULT_CREDENTIALS_DIR = (
    Path.home()
    / "Desktop/Hackathon/Hackathon0/ai-employee-project/.credentials"
)


# ── GmailWatcher ──────────────────────────────────────────────────────────────

class GmailWatcher(BaseWatcher):
    """Polls Gmail for unread priority emails and creates vault task cards."""

    def __init__(
        self,
        vault_path: str | Path,
        credentials_dir: str | Path | None = None,
        check_interval: int = 300,
        max_results: int = 20,
    ):
        super().__init__(vault_path, check_interval)
        creds_dir = Path(credentials_dir) if credentials_dir else DEFAULT_CREDENTIALS_DIR
        self.credentials_file = creds_dir / "credentials.json"
        self.token_file = creds_dir / "token.json"
        self.max_results = max_results
        self._service = None
        self._seen_ids: set[str] = set()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_service(self):
        """Return an authenticated Gmail API service, refreshing token as needed."""
        creds = None

        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_file), SCOPES
                )
            except Exception as e:
                self.logger.warning(f"Could not load token.json: {e} — re-authorizing.")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    self.logger.info("Refreshing access token...")
                    creds.refresh(Request())
                except TransportError as e:
                    self.logger.error(f"Token refresh failed (network error): {e}")
                    raise
                except Exception as e:
                    self.logger.warning(f"Token refresh failed: {e} — re-authorizing.")
                    creds = None

            if not creds or not creds.valid:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {self.credentials_file}\n"
                        "Download it from Google Cloud Console → "
                        "APIs & Services → Credentials → OAuth 2.0 Client IDs."
                    )
                self.logger.info("Opening browser for first-time authorization...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_file.write_text(creds.to_json(), encoding="utf-8")
            self.logger.info(f"Token saved to {self.token_file}")

        return build("gmail", "v1", credentials=creds)

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list[dict]:
        """Query Gmail for unread keyword-matching emails not yet logged."""
        if self._service is None:
            self._service = self._get_service()

        query = _build_query()
        self.logger.info(f"Query: {query}")

        try:
            result = (
                self._service.users()
                .messages()
                .list(userId="me", q=query, maxResults=self.max_results)
                .execute()
            )
        except HttpError as e:
            self.logger.error(f"Gmail API list error: {e}")
            return []

        messages = result.get("messages", [])
        if not messages:
            return []

        items = []
        for msg in messages:
            msg_id = msg["id"]

            if msg_id in self._seen_ids:
                continue
            if _already_logged(msg_id, self.vault_path):
                self._seen_ids.add(msg_id)
                continue

            try:
                full = (
                    self._service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject"],
                    )
                    .execute()
                )
            except HttpError as e:
                self.logger.error(f"Could not fetch message {msg_id}: {e}")
                continue

            headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
            items.append({
                "id": full["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "sender": headers.get("From", "unknown"),
                "snippet": full.get("snippet", "")[:200],
                "internal_date_ms": full["internalDate"],
            })

        return items

    def post_cycle(self, created_count: int) -> None:
        """Update dashboard after new emails are detected."""
        try:
            from helpers.dashboard_updater import refresh_vault_counts
            update_activity(self.vault_path, f"Gmail Monitor: {created_count} new email(s) detected")
            update_component_status(self.vault_path, "Gmail Monitor", "online")
            update_stats(self.vault_path, "emails_checked", created_count, operation="increment")
            refresh_vault_counts(self.vault_path)
        except Exception as e:
            self.logger.warning(f"Dashboard update failed: {e}")

    def create_action_file(self, item: dict) -> Path:
        """Write an EMAIL_*.md card to vault Inbox/ and return its path."""
        vault_inbox = self.vault_path / "Inbox"
        vault_inbox.mkdir(parents=True, exist_ok=True)

        received_iso, ts_slug = _parse_date(item["internal_date_ms"])
        priority = _infer_priority(item["subject"], item["snippet"])
        actions = _suggested_actions(item["subject"], item["snippet"])

        # Full message ID in filename for reliable deduplication
        card_name = f"EMAIL_{ts_slug}_{item['id']}.md"
        card_path = vault_inbox / card_name

        def yml(v: str) -> str:
            return v.replace('"', '\\"')

        card_path.write_text(
            f"""---
type: email
from: "{yml(item['sender'])}"
subject: "{yml(item['subject'])}"
received: "{received_iso}"
priority: {priority}
status: pending
message_id: "{item['id']}"
---

# Email: {item['subject']}

**From:** {item['sender']}
**Received:** {received_iso}
**Priority:** {priority}

---

## Snippet

> {item['snippet']}

---

## Suggested Actions

{actions}

---

## Notes

_Add context here as you process this email._
""",
            encoding="utf-8",
        )

        self._seen_ids.add(item["id"])
        return card_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_query() -> str:
    """Build Gmail search query: unread, inbox OR important, keyword match."""
    keyword_clause = " OR ".join(f'"{kw}"' for kw in KEYWORDS)
    return f"is:unread (label:inbox OR label:important) ({keyword_clause})"


def _already_logged(message_id: str, vault_path: Path) -> bool:
    """Return True if a vault card for this exact message ID exists in any vault folder."""
    for folder in ("Inbox", "Needs_Action", "Done"):
        d = vault_path / folder
        if d.exists() and any(message_id in f.name for f in d.iterdir() if f.suffix == ".md"):
            return True
    return False
    return any(message_id in f.name for f in inbox.iterdir() if f.suffix == ".md")


def _parse_date(internal_date_ms: str) -> tuple[str, str]:
    ts = int(internal_date_ms) / 1000
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC"), dt.strftime("%Y%m%d_%H%M%S")


def _infer_priority(subject: str, snippet: str) -> str:
    combined = (subject + " " + snippet).lower()
    if any(kw in combined for kw in ["urgent", "asap"]):
        return "high"
    return "normal"


def _suggested_actions(subject: str, snippet: str) -> str:
    combined = (subject + " " + snippet).lower()
    if "invoice" in combined or "payment" in combined:
        return (
            "- [ ] Verify invoice amount and sender legitimacy\n"
            "- [ ] Check if payment is due or already processed\n"
            "- [ ] Forward to accounts or log in expense tracker\n"
            "- [ ] Reply to confirm receipt if required"
        )
    if "urgent" in combined or "asap" in combined:
        return (
            "- [ ] Read full email immediately\n"
            "- [ ] Determine who needs to be notified\n"
            "- [ ] Draft response or escalate within 1 hour\n"
            "- [ ] Log outcome in Notes section below"
        )
    return (
        "- [ ] Read full email\n"
        "- [ ] Determine if action or reply is needed\n"
        "- [ ] Archive or file when resolved"
    )


def _safe_slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip()
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug[:max_len]


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    vault = Path.home() / "Desktop/Hackathon/Hackathon0/AI_Employee_Vault"
    interval = 300

    if len(sys.argv) > 1:
        vault = Path(sys.argv[1])
    if len(sys.argv) > 2:
        interval = int(sys.argv[2])

    watcher = GmailWatcher(vault_path=vault, check_interval=interval)
    watcher.run()
