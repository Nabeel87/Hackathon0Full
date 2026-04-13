import re
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from watchers.base_watcher import BaseWatcher

# ── Config ────────────────────────────────────────────────────────────────────

HIGH_PRIORITY_KEYWORDS = [
    "urgent", "asap", "emergency", "critical",
    "deadline", "important", "action required",
    "immediately", "right now", "waiting", "help",
    "client", "payment",
]

BUSINESS_KEYWORDS = [
    "urgent", "asap", "meeting", "invoice",
    "payment", "deadline", "report", "client",
    "project", "important", "action", "help",
]

# KEYWORDS kept for backward compatibility (union of both lists)
KEYWORDS = sorted(set(HIGH_PRIORITY_KEYWORDS) | set(BUSINESS_KEYWORDS))

MAX_MESSAGES_PER_CHECK = 10

WHATSAPP_URL = "https://web.whatsapp.com"

# UI artifacts to strip from message text
_UI_ARTIFACTS = [
    "Typing...", "Online", "last seen",
    "voice call", "video call",
    "Photo", "Video", "Document",
    "Sticker", "GIF", "Audio",
    "You:", "Missed voice call", "Missed video call",
]

# CSS selectors — WhatsApp Web (best-effort; may drift with app updates)
SEL_UNREAD_BADGE  = 'span[data-icon="unread-count"], ._3m_Xw span._3_7SH'
SEL_CHAT_LIST     = 'div[role="listitem"]'
SEL_CONTACT_NAME  = 'span[title], ._3ko75'
SEL_MESSAGE_TEXT  = 'span.selectable-text, ._3-8er'
SEL_TIMESTAMP     = 'div._3Bxar span, span[data-icon="msg-time"]'
SEL_CHAT_LIST_BOX = '#pane-side'
SEL_LOGGED_IN     = 'div[data-testid="chat-list"], #pane-side, div._3YS_f'


# ── WhatsAppWatcher ───────────────────────────────────────────────────────────

class WhatsAppWatcher(BaseWatcher):
    """Watch WhatsApp Web for important messages and create vault task cards."""

    def __init__(self, vault_path: str | Path, check_interval: int = 60):
        super().__init__(vault_path, check_interval)
        self.session_path = Path.home() / ".credentials" / "whatsapp_session"
        self.session_path.mkdir(parents=True, exist_ok=True)
        self._context_file = self.session_path / "context.json"
        self.keywords = BUSINESS_KEYWORDS
        self.high_priority_keywords = HIGH_PRIORITY_KEYWORDS
        self.business_keywords = BUSINESS_KEYWORDS
        self._seen_ids: set[str] = set()

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list[dict]:
        """Open WhatsApp Web, scan for unread keyword-matching messages."""
        self._ensure_session()

        try:
            messages = self._check_unread_messages()
        except PlaywrightTimeout as e:
            self.logger.warning(f"Playwright timeout during check: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error during WhatsApp check: {e}")
            return []

        # Filter to keyword matches and deduplicate
        results = []
        for msg in messages:
            msg_id = _make_msg_id(msg)
            if msg_id in self._seen_ids:
                continue
            if _already_logged(msg_id, self.vault_path):
                self._seen_ids.add(msg_id)
                continue
            combined = (msg.get("contact", "") + " " + msg.get("text", "")).lower()
            if not any(kw in combined for kw in self.keywords):
                self.logger.debug(
                    f"Skipped message from {msg.get('contact','?')} — no business keywords"
                )
                continue
            results.append(msg)

        if len(results) > MAX_MESSAGES_PER_CHECK:
            self.logger.warning(
                f"{len(results)} matching messages found — processing first "
                f"{MAX_MESSAGES_PER_CHECK}, skipping the rest."
            )
            results = results[:MAX_MESSAGES_PER_CHECK]

        self.logger.info(
            f"Checking WhatsApp... found {len(results)} unread message(s) with keywords"
        )
        return results

    def create_action_file(self, item: dict) -> Path:
        """Write a WHATSAPP_*.md card to vault, routed by priority, and return its path."""
        received_dt  = item.get("received_dt") or datetime.now()
        ts_slug      = received_dt.strftime("%Y%m%d_%H%M%S")
        received_iso = received_dt.strftime("%Y-%m-%dT%H:%M:%S")
        received_hr  = received_dt.strftime("%Y-%m-%d %H:%M:%S")

        contact  = item.get("contact", "Unknown")
        phone    = item.get("phone", "")
        text     = item.get("text", "")
        preview  = text[:100]
        priority = self.detect_priority(text)
        msg_id   = _make_msg_id(item)

        # Priority routing
        if priority == "high":
            dest_folder = self.vault_path / "Needs_Action"
        else:
            dest_folder = self.vault_path / "Inbox"
        dest_folder.mkdir(parents=True, exist_ok=True)

        contact_slug = _safe_slug(contact)
        filename  = f"WHATSAPP_{ts_slug}_{contact_slug}.md"
        card_path = dest_folder / filename

        def yml(v: str) -> str:
            return v.replace('"', '\\"')

        phone_line    = f"phone: \"{yml(phone)}\"\n" if phone else ""
        phone_display = f"**Phone:** {phone}\n" if phone else ""

        card_path.write_text(
            f"""---
type: whatsapp_message
from: "{yml(contact)}"
message_preview: "{yml(preview)}"
received: {received_iso}
priority: {priority}
status: pending
{phone_line}message_id: "{msg_id}"
---

# WhatsApp Message: {contact}

**From:** {contact}
{phone_display}**Received:** {received_hr}
**Priority:** {priority}

## Message Preview
{text[:500]}

## Suggested Actions
- [ ] Reply to message
- [ ] Call contact
- [ ] Mark as important
- [ ] Create task in Needs_Action

## Links
- Open WhatsApp Web to reply: {WHATSAPP_URL}

## Notes
_Add context here as you process this message._
""",
            encoding="utf-8",
        )

        self.logger.info(
            f"Created {filename} for message from {contact} "
            f"(priority: {priority} -> {dest_folder.name}/)"
        )
        self._seen_ids.add(msg_id)
        return card_path

    def post_cycle(self, created_count: int) -> None:
        """Update dashboard after new messages are detected."""
        try:
            from helpers.dashboard_updater import (
                update_activity, update_component_status,
                update_stats, refresh_vault_counts,
            )
            update_activity(self.vault_path, f"WhatsApp Monitor: {created_count} new message(s) detected")
            update_component_status(self.vault_path, "WhatsApp Monitor", "online")
            update_stats(self.vault_path, "whatsapp_messages_checked", created_count, operation="increment")
            refresh_vault_counts(self.vault_path)
        except Exception as e:
            self.logger.warning(f"Dashboard update failed: {e}")

    # ── Session management ────────────────────────────────────────────────────

    def _ensure_session(self) -> None:
        """Ensure WhatsApp session exists, with fallback to manual link."""
        if self._context_file.exists():
            self.logger.info("Using saved WhatsApp session.")
            return

        # First-time setup banner
        print("\n" + "=" * 50)
        print("WhatsApp Watcher - First Run Setup")
        print("=" * 50)
        print("This will open a browser for WhatsApp login.")
        print("Please scan the QR code with your phone.")
        print("\nIf browser doesn't open automatically:")
        print(f"1. Open this link manually: {WHATSAPP_URL}")
        print("2. Scan the QR code with your phone")
        print("=" * 50)
        input("\nPress ENTER to continue...")

        self._login_and_save_session()

    def _login_and_save_session(self) -> None:
        """
        Launch a headed browser, navigate to WhatsApp Web, wait for QR scan,
        then persist the browser context to disk for future headless runs.
        """
        # ── Step 1: verify Playwright + browser executable ────────────────────
        self.logger.info("Playwright installation check...")
        self.logger.info(f"Session path: {self.session_path}")
        self.logger.info("Browser: Chromium (headless=False)")

        try:
            with sync_playwright() as _pw:
                browser_path = _pw.chromium.executable_path
                self.logger.info(f"Chromium found at: {browser_path}")
        except Exception as e:
            self.logger.error(f"Playwright browser not found: {e}")
            print("\nPlaywright browsers not installed!")
            print("Run: playwright install chromium")
            raise

        # ── Step 2: headed browser login ──────────────────────────────────────
        try:
            with sync_playwright() as pw:
                self.logger.info("Launching browser...")
                try:
                    browser = pw.chromium.launch(
                        headless=False,
                        args=["--start-maximized"],
                    )
                except Exception as e:
                    self.logger.error(f"Failed to launch browser: {e}")
                    print("\nBrowser failed to open automatically!")
                    print("\nMANUAL STEPS:")
                    print("1. Open your browser")
                    print(f"2. Go to: {WHATSAPP_URL}")
                    print("3. Scan the QR code with your phone")
                    print("4. Press ENTER here after scanning")
                    input("\nPress ENTER after you've scanned the QR code...")
                    return

                context = browser.new_context(
                    viewport=None,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = context.new_page()

                print("\nOpening WhatsApp Web...")
                print(f"URL: {WHATSAPP_URL}")

                try:
                    page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30_000)
                except Exception as e:
                    self.logger.error(f"Failed to load WhatsApp Web: {e}")
                    print(f"\nError loading page: {e}")
                    print(f"\nTry manually: {WHATSAPP_URL}")
                    context.close()
                    browser.close()
                    return

                # Wait for QR code or chat list
                print("\nWaiting for QR code scan...")
                print("On your phone:")
                print("  1. Open WhatsApp")
                print("  2. Menu -> Linked Devices")
                print("  3. Link a Device")
                print("  4. Scan the QR code from the browser")

                try:
                    self.logger.info("Waiting for QR code to load...")
                    page.wait_for_selector(
                        'canvas[aria-label*="Scan"], canvas, div[data-testid="qrcode"], '
                        + SEL_LOGGED_IN,
                        timeout=30_000,
                    )

                    if page.query_selector(SEL_LOGGED_IN):
                        print("\nAlready logged in!")
                    else:
                        print("\nWaiting for scan (up to 5 minutes)...")
                        page.wait_for_selector(SEL_LOGGED_IN, timeout=300_000)
                        print("\nLogin successful!")

                except PlaywrightTimeout as e:
                    self.logger.error(f"Login timeout or failed: {e}")
                    print(f"\nLogin timeout: {e}")
                    print("\nPlease try again or check your phone")
                    context.close()
                    browser.close()
                    return

                # Save session
                self.session_path.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(self._context_file))
                self.logger.info(f"Session stored at {self._context_file}")
                print(f"\nSession saved to: {self._context_file}")

                context.close()
                browser.close()

        except (PlaywrightTimeout, RuntimeError):
            raise
        except Exception as e:
            self.logger.error(f"Session setup failed: {e}")
            print(f"\nSetup failed: {e}")
            print("\nManual alternative:")
            print(f"1. Open {WHATSAPP_URL} in your browser")
            print("2. Scan QR code")
            print("3. Session will be saved on next run")
            raise

    # ── Message scanning ──────────────────────────────────────────────────────

    def _check_unread_messages(self) -> list[dict]:
        """
        Launch headless browser with saved session and return unread message dicts.
        If session is expired, logs an error and raises RuntimeError.
        """
        messages: list[dict] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self._context_file),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30_000)

                # Verify session is still valid
                try:
                    page.wait_for_selector(SEL_LOGGED_IN, timeout=20_000)
                except PlaywrightTimeout:
                    self.logger.error(
                        "WhatsApp session appears to have expired. "
                        f"Delete {self._context_file} and re-run to log in again."
                    )
                    raise RuntimeError("WhatsApp session expired — manual re-login required.")

                # Wait for chats to load
                try:
                    page.wait_for_selector(SEL_CHAT_LIST_BOX, timeout=15_000)
                    page.wait_for_timeout(2_000)  # Let the list render fully
                except PlaywrightTimeout:
                    self.logger.warning("Chat list pane did not appear in time.")
                    return []

                # Find chats with unread badges
                chat_items = page.query_selector_all(SEL_CHAT_LIST)
                self.logger.info(f"Found {len(chat_items)} chat(s) in list")

                for chat in chat_items:
                    badge = chat.query_selector(SEL_UNREAD_BADGE)
                    if badge is None:
                        continue
                    msg_data = self._extract_message_data(chat)
                    if msg_data:
                        messages.append(msg_data)

            except (RuntimeError, PlaywrightTimeout):
                raise
            except Exception as e:
                self.logger.error(f"WhatsApp Web selector error: {e}")
            finally:
                context.close()
                browser.close()

        return messages

    def _extract_message_data(self, chat_element) -> dict | None:
        """Parse contact name, message preview, and timestamp from a chat list item."""
        try:
            contact = self._extract_sender_name(chat_element)
            text    = self._extract_message_text(chat_element)

            # Skip notification badges masquerading as messages
            if self._is_notification_badge(text):
                self.logger.debug(f"Skipped notification badge for {contact}")
                return None

            # Timestamp (WhatsApp shows relative times like "10:32 AM" or "Yesterday")
            ts_el         = chat_element.query_selector(SEL_TIMESTAMP)
            timestamp_raw = ts_el.inner_text().strip() if ts_el else ""
            received_dt   = _parse_whatsapp_time(timestamp_raw)

            return {
                "contact":       contact,
                "text":          text,
                "timestamp_raw": timestamp_raw,
                "received_dt":   received_dt,
                "phone":         "",  # WhatsApp Web doesn't expose phone in list view
            }

        except Exception as e:
            self.logger.error(f"WhatsApp Web selector error extracting message data: {e}")
            return None

    def _extract_sender_name(self, chat_element) -> str:
        """Extract clean sender name from a chat list element."""
        try:
            name_el = chat_element.query_selector(SEL_CONTACT_NAME)
            if name_el:
                name = name_el.get_attribute("title") or name_el.inner_text()
                return name.strip()
        except Exception as e:
            self.logger.debug(f"Could not extract sender name: {e}")
        return "Unknown"

    def _extract_message_text(self, chat_element) -> str:
        """Extract and clean message text from a chat list element."""
        try:
            text_el = chat_element.query_selector(SEL_MESSAGE_TEXT)
            if text_el:
                raw = text_el.inner_text().strip()
                return self._clean_message_text(raw)
        except Exception as e:
            self.logger.debug(f"Could not extract message text: {e}")
        return ""

    def _clean_message_text(self, raw_text: str) -> str:
        """Remove WhatsApp UI artifacts, timestamps, and noise from message text."""
        cleaned = raw_text

        # Remove known UI artifact strings
        for artifact in _UI_ARTIFACTS:
            cleaned = cleaned.replace(artifact, "")

        # Remove timestamps: "10:36 AM", "10:36", "2:30 PM"
        cleaned = re.sub(r'\b\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?\b', '', cleaned)

        # Remove standalone notification counts like "3", "12"
        cleaned = re.sub(r'^\s*\d+\s*$', '', cleaned, flags=re.MULTILINE)

        # Remove duplicate spaces / newlines
        cleaned = re.sub(r'\s+', ' ', cleaned)

        return cleaned.strip()

    def _is_notification_badge(self, text: str) -> bool:
        """Return True if text is just a notification badge (number or empty)."""
        stripped = text.strip()
        if not stripped:
            return True
        # Pure digit strings are badge counts
        if re.match(r'^\d+$', stripped):
            return True
        return False

    def _create_message_fingerprint(self, sender: str, message: str) -> str:
        """Create a content-based fingerprint for deduplication (sender + first 50 chars)."""
        sender_clean  = sender.strip().lower()
        message_clean = message.strip()[:50].lower()
        return f"{sender_clean}|{message_clean}"

    # ── Priority ──────────────────────────────────────────────────────────────

    def detect_priority(self, message_text: str) -> str:
        """Return 'high' if message contains a high-priority keyword, else 'normal'."""
        lower = message_text.lower()
        for kw in self.high_priority_keywords:
            if kw in lower:
                return "high"
        return "normal"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_msg_id(msg: dict) -> str:
    """Stable ID from contact + timestamp for deduplication."""
    contact = _safe_slug(msg.get("contact", "unknown"), max_len=30)
    dt      = msg.get("received_dt") or datetime.now()
    ts_slug = dt.strftime("%Y%m%d_%H%M%S")
    return f"{contact}_{ts_slug}"


def _already_logged(msg_id: str, vault_path: Path) -> bool:
    """Return True if a vault card with this msg_id already exists."""
    for folder in ("Inbox", "Needs_Action", "Done"):
        d = vault_path / folder
        if d.exists() and any(msg_id in f.name for f in d.iterdir() if f.suffix == ".md"):
            return True
    return False


def _safe_slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug[:max_len]


def _parse_whatsapp_time(raw: str) -> datetime:
    """
    Convert WhatsApp timestamp strings to datetime.
    WhatsApp shows: "10:32 AM", "Yesterday", "Mon", "12/04/2026", etc.
    Falls back to datetime.now() when the format is unrecognised.
    """
    now = datetime.now()
    raw = raw.strip()

    if not raw:
        return now

    # "HH:MM AM/PM" — today
    match = re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", raw, re.IGNORECASE)
    if match:
        hour, minute, meridiem = int(match[1]), int(match[2]), match[3].upper()
        if meridiem == "PM" and hour != 12:
            hour += 12
        if meridiem == "AM" and hour == 12:
            hour = 0
        try:
            return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            return now

    # "HH:MM" (24-hour) — today
    match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if match:
        try:
            return now.replace(hour=int(match[1]), minute=int(match[2]), second=0, microsecond=0)
        except ValueError:
            return now

    # "DD/MM/YYYY" or "MM/DD/YYYY"
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if match:
        try:
            return datetime(int(match[3]), int(match[2]), int(match[1]))
        except ValueError:
            return now

    # "Yesterday" or weekday names — rough approximation
    return now


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    vault_path = Path.home() / "Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"

    if len(sys.argv) > 1:
        vault_path = Path(sys.argv[1])

    watcher = WhatsAppWatcher(str(vault_path))

    # Run one check (triggers QR login on first run via _ensure_session, then scans)
    watcher.check_for_updates()
