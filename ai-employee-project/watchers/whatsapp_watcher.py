import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from watchers.base_watcher import BaseWatcher


class SessionExpiredError(Exception):
    """Raised when the saved WhatsApp browser session is no longer valid."""


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

# CSS selectors — WhatsApp Web
# Multiple fallbacks per element because WhatsApp updates break class names
SEL_LOGGED_IN = (
    'div[data-testid="chat-list"], '
    '#pane-side, '
    'div[aria-label="Chat list"], '
    'div[data-testid="default-user"]'
)
SEL_CHAT_LIST_BOX = (
    '#pane-side, '
    'div[aria-label="Chat list"], '
    'div[data-testid="chat-list"]'
)
SEL_CHAT_LIST = (
    'div[data-testid="cell-frame-container"], '
    'div[data-testid="list-item"]'
    # Note: div[role="listitem"] intentionally removed — too broad, matches
    # non-chat elements (archive headers, status rows) and wastes iterations.
)
# Unread badge — multiple selectors for resilience across WhatsApp updates
SEL_UNREAD_BADGE = (
    'span[data-testid="icon-unread-count"], '
    'span[data-icon="unread-count"], '
    'span[aria-label*="unread"], '
    'div[data-testid="unread-count"], '
    'span._3m_Xw'
)
SEL_CONTACT_NAME = (
    'span[data-testid="cell-frame-title"], '
    'span[title], '
    'div[data-testid="cell-frame-title"] span'
)
SEL_MESSAGE_TEXT = (
    # last-msg-text FIRST — returns the actual preview message text.
    # last-msg-status is intentionally excluded here: it holds the delivery
    # receipt (✓✓ / "Read") and never contains message content.
    '[data-testid="last-msg-text"], '
    'div[data-testid="last-msg-text"] span, '
    'span.selectable-text, '
    'span._11JPr'
)
SEL_TIMESTAMP = (
    'div[data-testid="cell-frame-timestamp"] span, '
    'span[data-testid="cell-frame-timestamp"]'
)


# ── WhatsAppWatcher ───────────────────────────────────────────────────────────

class WhatsAppWatcher(BaseWatcher):
    """Watch WhatsApp Web for important messages and create vault task cards."""

    def __init__(self, vault_path: str | Path, check_interval: int = 60):
        super().__init__(vault_path, check_interval)
        self.session_path  = _PROJECT_ROOT / ".credentials" / "whatsapp_session"
        self.session_path.mkdir(parents=True, exist_ok=True)
        # Marker file — signals that login completed successfully
        self._context_file = self.session_path / "context.json"
        # Full browser profile directory — WhatsApp device ID lives here
        self._profile_dir  = self.session_path / "chrome_profile"
        self.keywords = BUSINESS_KEYWORDS
        self.high_priority_keywords = HIGH_PRIORITY_KEYWORDS
        self.business_keywords = BUSINESS_KEYWORDS
        self._seen_ids: set[str] = set()

        # ── Browser — kept alive across check cycles ─────────────────────────
        self._pw       = None   # sync_playwright instance
        self.context   = None   # persistent Chromium context
        self.page      = None   # single WhatsApp tab, reused every cycle

        # ── Per-chat state (hybrid detection + persistent seen-IDs) ──────────
        self._state_file      = self.session_path / "chat_state.json"
        self._chat_state      = self._load_chat_state()
        self._state_was_empty = not bool(self._chat_state.get("chats"))

        # Pre-load previously saved msg_ids so duplicates are blocked even
        # after a watcher restart (without having to scan vault files).
        self._seen_ids.update(self._chat_state.get("seen_msg_ids", []))

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list[dict]:
        """Open WhatsApp Web, scan for unread keyword-matching messages."""
        self._ensure_session()

        try:
            messages = self._check_unread_messages()
        except SessionExpiredError:
            # Session expired — close browser, delete stale session, re-login
            self.logger.warning("Session expired — closing browser and launching QR re-login...")
            self.close()
            self._clear_session()
            self._login_and_save_session()
            # Retry once with the fresh session
            try:
                messages = self._check_unread_messages()
            except Exception as e:
                self.logger.error(f"Failed after re-login: {e}")
                return []
        except PlaywrightTimeout as e:
            self.logger.warning(f"Playwright timeout during check: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error during WhatsApp check: {e}")
            return []

        # ── Diagnostic: log every raw unread message ─────────────────────────
        self.logger.info(f"Raw unread chats detected: {len(messages)}")
        for m in messages:
            self.logger.info(
                f"  Unread | from: {m.get('contact','?')!r:25} | "
                f"preview: {m.get('text','')[:60]!r}"
            )

        # ── Split multi-message text and process each bubble individually ────────
        # _read_conversation_messages joins all visible bubbles with " | ".
        # When a new message arrives, the conversation pane shows the old
        # (already-saved) bubble AND the new one — producing a combined string
        # like "Fix meeting with CEO | Let's meet tomorrow".  That combined
        # string has a different SHA-1 from the first message alone, so the
        # dedup check passes and a duplicate card is written.
        # Fix: split on " | ", give each segment its own msg_id, and skip any
        # segment that is already in the vault.
        expanded: list[dict] = []
        for msg in messages:
            raw_text = msg.get("text", "")
            segments = [s.strip() for s in raw_text.split(" | ") if s.strip()]
            if not segments:
                segments = [raw_text]
            for seg in segments:
                expanded.append({**msg, "text": seg})

        # ── Filter to keyword matches and deduplicate ─────────────────────────
        results = []
        skipped_kw   = 0
        skipped_seen = 0

        for msg in expanded:
            msg_id   = _make_msg_id(msg)
            contact  = msg.get("contact", "?")
            text     = msg.get("text", "")

            if msg_id in self._seen_ids:
                skipped_seen += 1
                continue
            if _already_logged(msg_id, self.vault_path, text=text):
                self._seen_ids.add(msg_id)
                skipped_seen += 1
                continue

            # Unread chats: WhatsApp flagged them as new — bypass keyword filter.
            # The preview text for community/group chats is often a sub-group
            # name (e.g. "Pana-101-P005 Discussion Group") rather than the
            # actual message, so keyword matching would always fail for those.
            if msg.get("is_unread"):
                self.logger.info(
                    f"  UNREAD (bypass filter) | from: {contact!r} | text: {text[:80]!r}"
                )
                self._seen_ids.add(msg_id)
                results.append(msg)
                continue

            # For hybrid "recently changed" messages apply keyword filter.
            combined = (contact + " " + text).lower()
            matched_kw = [kw for kw in self.keywords if kw in combined]

            self.logger.info(
                f"  CHECKING | from: {contact!r} | text: {text[:80]!r}"
            )

            if not matched_kw:
                skipped_kw += 1
                self.logger.warning(
                    f"  NO MATCH | none of {self.keywords} found in text above."
                )
                continue

            self.logger.info(
                f"  MATCHED keywords {matched_kw} | from: {contact!r}"
            )
            self._seen_ids.add(msg_id)
            results.append(msg)

        if len(results) > MAX_MESSAGES_PER_CHECK:
            self.logger.warning(
                f"{len(results)} matching messages — processing first "
                f"{MAX_MESSAGES_PER_CHECK}, skipping the rest."
            )
            results = results[:MAX_MESSAGES_PER_CHECK]

        unread_bypass = sum(1 for m in results if m.get("is_unread"))
        self.logger.info(
            f"Summary: {len(messages)} raw | {len(expanded)} segments | "
            f"{len(results)} captured "
            f"({unread_bypass} unread-bypass, {len(results)-unread_bypass} keyword-match) | "
            f"{skipped_kw} skipped (no keywords) | "
            f"{skipped_seen} skipped (already logged)"
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

        # Mark as seen in memory and persist to disk so duplicates are
        # blocked even after a watcher restart.
        self._seen_ids.add(msg_id)
        seen = self._chat_state.setdefault("seen_msg_ids", [])
        if msg_id not in seen:
            seen.append(msg_id)
            # Trim to last 500 to prevent unbounded growth
            self._chat_state["seen_msg_ids"] = seen[-500:]
            self._save_chat_state()

        return card_path

    def run(self) -> None:
        """Start continuous polling — sets dashboard ONLINE on start, READY on stop."""
        self._update_dashboard_status("online", "OK")
        try:
            super().run()
        finally:
            self._update_dashboard_status("ready", "On-demand")
            self.close()   # tear down browser cleanly on Ctrl+C or error

    def _update_dashboard_status(self, status: str, notes: str) -> None:
        """Update the WhatsApp Monitor row in the System Status table."""
        try:
            from helpers.dashboard_updater import update_component_status
            update_component_status(self.vault_path, "WhatsApp Monitor", status, notes)
        except Exception as e:
            self.logger.warning(f"Dashboard status update failed: {e}")

    def post_cycle(self, created_count: int) -> None:
        """Update dashboard after new messages are detected."""
        try:
            from helpers.dashboard_updater import (
                update_activity, update_component_status,
                update_stats, refresh_vault_counts,
            )
            update_activity(self.vault_path, f"WhatsApp Monitor: {created_count} new message(s) detected")
            update_component_status(self.vault_path, "WhatsApp Monitor", "online", "OK")
            update_stats(self.vault_path, "whatsapp_checked", created_count, operation="increment")
            refresh_vault_counts(self.vault_path)
        except Exception as e:
            self.logger.warning(f"Dashboard update failed: {e}")

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    def _init_browser(self) -> None:
        """Start Playwright and open a persistent-context browser window.

        Uses the same chrome_profile as before so WhatsApp recognises the
        device.  The browser stays open for the lifetime of the watcher
        process — it is closed only in close() / run() finally.

        BUG 2 FIX: uses context.pages[0] (the restored WhatsApp tab) instead
        of context.new_page() (a blank new tab that races against the timeout).
        """
        self.logger.info("Initialising browser (will stay open across checks)...")
        self._pw = sync_playwright().start()
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        # Use the restored WhatsApp tab when available; else open a new one.
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.logger.info(
            f"Browser ready — using page: {self.page.url!r} "
            f"(total open pages: {len(self.context.pages)})"
        )

    def _ensure_browser(self) -> None:
        """Guarantee browser + page are alive; reinitialise after a crash."""
        if self.context is None or self.page is None:
            self._init_browser()

    def close(self) -> None:
        """Tear down browser cleanly — called from run() finally."""
        try:
            if self.context:
                # Save storage-state backup before closing
                try:
                    self.context.storage_state(path=str(self._context_file))
                except Exception:
                    pass
                self.context.close()
        except Exception as e:
            self.logger.debug(f"context.close error: {e}")
        try:
            if self._pw:
                self._pw.stop()
        except Exception as e:
            self.logger.debug(f"playwright.stop error: {e}")
        self.context = None
        self.page    = None
        self._pw     = None

    # ── Per-chat state (hybrid detection) ─────────────────────────────────────

    def _load_chat_state(self) -> dict:
        """Load per-chat last-seen message keys from disk."""
        default: dict = {"updated_at": None, "chats": {}}
        if not self._state_file.exists():
            return default
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("chats"), dict):
                return data
        except Exception as e:
            self.logger.warning(f"Could not read chat_state.json: {e}")
        return default

    def _save_chat_state(self) -> None:
        self._chat_state["updated_at"] = datetime.now().isoformat()
        self._state_file.write_text(
            json.dumps(self._chat_state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _stable_msg_key(chat_name: str, preview: str) -> str:
        """SHA-1 fingerprint of contact+preview — stable across runs."""
        raw = f"{chat_name}|{preview}".encode("utf-8", errors="ignore")
        return hashlib.sha1(raw).hexdigest()[:16]

    def _update_chat_state(self, chat_rows: list[dict]) -> None:
        chats = self._chat_state.setdefault("chats", {})
        now   = datetime.now().isoformat()
        for row in chat_rows:
            chats[row["chat_key"]] = {
                "chat_name":        row["chat_name"],
                "last_message_key": row["message_key"],
                "last_preview":     row["preview"][:300],
                "last_seen":        now,
            }

    # ── Chat row extraction ────────────────────────────────────────────────────

    def _collect_chat_rows(self) -> list[dict]:
        """Return structured info for every visible chat row (up to 40).

        WhatsApp sometimes renders each item twice in the DOM (e.g. one
        element for the row container and one for the inner frame).
        Deduplication by chat_name keeps only the first occurrence so the
        caller sees clean, unique rows.
        """
        rows = self.page.query_selector_all('[data-testid="cell-frame-container"]')
        if not rows:
            rows = self.page.query_selector_all('#pane-side [role="gridcell"]')
        if not rows:
            rows = self.page.query_selector_all('[data-testid="list-item"]')

        self.logger.info(f"[collect_chat_rows] raw DOM rows found: {len(rows)}")
        result: list[dict] = []
        seen_names: set[str] = set()
        for idx, chat in enumerate(rows[:80]):   # scan more raw rows to hit 40 unique
            try:
                info = self._extract_chat_info(chat, idx)
                if info and info["chat_name"] not in seen_names:
                    seen_names.add(info["chat_name"])
                    result.append(info)
                    if len(result) >= 40:
                        break
            except Exception as e:
                self.logger.debug(f"Row {idx} parse error: {e}")
        return result

    def _extract_chat_info(self, chat, rank: int) -> dict | None:
        """Extract normalised info from one chat row element."""
        # Unread badge
        unread_badge = (
            chat.query_selector('[data-testid="icon-unread-count"]') or
            chat.query_selector('[aria-label*="unread"]') or
            chat.query_selector('span[aria-label*=" unread"]')
        )

        # Contact name
        name_el = (
            chat.query_selector('[data-testid="cell-frame-title"]') or
            chat.query_selector('span[title]')
        )
        chat_name = name_el.inner_text().strip() if name_el else "Unknown"
        if not chat_name or chat_name == "Unknown":
            return None

        # Message preview
        # SELECTOR ORDER MATTERS:
        #   last-msg-text  → the actual message text shown in the chat list
        #   last-msg-status → the delivery receipt element (✓✓ ticks / "Read")
        # Previously last-msg-status was checked first — it always exists and
        # its inner_text() returns "Read"/"Delivered"/empty, never the message.
        # That made every preview empty → keywords never matched.
        preview_el = (
            chat.query_selector('[data-testid="last-msg-text"]') or
            chat.query_selector('span.selectable-text')
        )
        if preview_el:
            preview = preview_el.inner_text().strip()
            self.logger.debug(f"[preview via selector] {chat_name!r}: {preview[:80]!r}")
        else:
            # Fallback: take all visible text, strip the contact name, timestamps,
            # and pure-digit badge counts. The old filter `":" not in ln[:8]`
            # was removed — it silently dropped group-chat lines like
            # "John: asap call me" because the colon falls within 8 chars.
            row_text  = (chat.inner_text() or "").strip()
            row_lines = [ln.strip() for ln in row_text.split("\n") if ln.strip()]
            filtered  = [
                ln for ln in row_lines
                if ln != chat_name
                and not ln.isdigit()
                and not re.match(r'^\d{1,2}:\d{2}', ln)   # skip timestamps only
            ]
            preview = filtered[0] if filtered else row_text[:200]
            self.logger.debug(f"[preview via fallback] {chat_name!r}: {preview[:80]!r}")

        if not preview:
            return None

        preview   = self._clean_message_text(preview)
        msg_key   = self._stable_msg_key(chat_name, preview)
        chat_key  = chat_name.lower()
        state_entry = self._chat_state.get("chats", {}).get(chat_key, {})
        is_new    = state_entry.get("last_message_key") != msg_key

        return {
            "chat_key":       chat_key,
            "chat_name":      chat_name,
            "preview":        preview,
            "message_key":    msg_key,
            "is_unread":      bool(unread_badge),
            "is_new":         bool(is_new),
            "rank":           rank,
            "_el":            chat,   # Playwright ElementHandle — used by _open_chat_and_read
        }

    def _select_messages(self, chat_rows: list[dict]) -> list[dict]:
        """Hybrid strategy: always include unread + recently changed chats."""
        selected: list[dict] = []
        seen_keys: set[str]  = set()

        def add(row: dict) -> None:
            if row["message_key"] in seen_keys:
                return
            msg_id = f"{row['chat_name']}_{row['message_key']}"
            if msg_id in self._seen_ids:
                return
            selected.append({
                "contact":     row["chat_name"],
                "text":        row["preview"],
                "timestamp_raw": "",
                "received_dt": datetime.now(),
                "phone":       "",
                "msg_id":      msg_id,
                "is_unread":   row["is_unread"],
            })
            seen_keys.add(row["message_key"])
            # NOTE: _seen_ids is NOT updated here.
            # It is updated in check_for_updates only after the message passes
            # the keyword filter. Adding it here caused messages to be
            # permanently suppressed on the next cycle if they failed the filter.

        # Always capture unread chats
        for row in chat_rows:
            if row["is_unread"]:
                add(row)

        # Cold-start guard: seed state without flooding vault on first run.
        # _state_was_empty is flipped to False here so subsequent cycles within
        # the same session also use the hybrid path — previously it stayed True
        # for the entire session because it was only set at __init__.
        if self._state_was_empty:
            self._state_was_empty = False   # flip so next cycle uses hybrid path
            return selected

        # Also capture recently changed chats (top 12) even without badge
        for row in chat_rows[:12]:
            if not row["is_unread"] and row["is_new"]:
                add(row)

        return selected

    # ── Downloading-state guard (BUG 4 fix) ───────────────────────────────────

    def _is_downloading_state(self) -> bool:
        """Return True if WhatsApp is still syncing ('messages downloading').

        Checks only explicit sync-screen phrases. The previous version had two
        bugs:
          1. Operator precedence: `A or B and C` evaluated as `A or (B and C)`,
             making the third condition fire independently of the first two.
          2. Wrong HTML search: used `"#pane-side"` (CSS selector syntax) which
             is never present in raw HTML — HTML uses `id="pane-side"`.
        """
        try:
            body = self.page.locator("body").inner_text(timeout=3_000).lower()
            return (
                "messages are downloading" in body
                or "don't close this window" in body
            )
        except Exception:
            return False

    def _wait_for_chat_list_ready(self, timeout_ms: int = 45_000) -> bool:
        """Poll until the chat list pane is visible; skip during sync state."""
        selectors = [
            "#pane-side",
            '[data-testid="chat-list"]',
            '[data-testid="cell-frame-container"]',
        ]
        deadline = datetime.now().timestamp() * 1000 + timeout_ms
        while datetime.now().timestamp() * 1000 < deadline:
            if self._is_downloading_state():
                self.logger.info("WhatsApp still syncing — waiting 3 s...")
                self.page.wait_for_timeout(3_000)
                continue
            for sel in selectors:
                try:
                    if self.page.query_selector(sel):
                        return True
                except Exception:
                    pass
            self.page.wait_for_timeout(1_000)
        return False

    # ── Session management ────────────────────────────────────────────────────

    def _ensure_session(self) -> None:
        """Ensure a WhatsApp session exists — auto-launches QR scan if not.

        A valid session is indicated by EITHER:
          - chrome_profile/ folder exists and is non-empty  (primary)
          - context.json exists and contains a 'cookies' key (secondary)
        Both are created together during _login_and_save_session; either one
        alone is enough to attempt a connection.
        """
        # ── Check 1: chrome_profile folder (primary auth store) ──────────────
        profile_valid = (
            self._profile_dir.exists()
            and any(self._profile_dir.iterdir())
        )
        if profile_valid:
            self.logger.info(
                f"Found chrome_profile — using persistent session "
                f"({self._profile_dir})."
            )
            return

        # ── Check 2: storage_state snapshot (secondary) ──────────────────────
        if self._context_file.exists():
            try:
                import json
                data = json.loads(self._context_file.read_text(encoding="utf-8"))
                if "cookies" in data:
                    cookie_count = len(data.get("cookies", []))
                    self.logger.info(
                        f"chrome_profile absent but storage_state found "
                        f"({cookie_count} cookies) — will launch with snapshot."
                    )
                    return
                else:
                    self.logger.warning(
                        "context.json has no 'cookies' (old marker format) — "
                        "deleting and re-running QR login."
                    )
                    self._context_file.unlink()
            except Exception as e:
                self.logger.warning(
                    f"Could not read context.json ({e}) — deleting and re-logging in."
                )
                try:
                    self._context_file.unlink()
                except Exception:
                    pass

        # ── No valid session — launch QR login ────────────────────────────────
        print("\n" + "=" * 50)
        print("WhatsApp Watcher - No Session Found")
        print("=" * 50)
        print("Opening browser for WhatsApp QR login...")
        print(f"Fallback URL (if browser fails): {WHATSAPP_URL}")
        print("=" * 50 + "\n")
        self.logger.info("No saved session found — launching browser for QR login.")

        self._login_and_save_session()

    def _clear_session(self) -> None:
        """Delete the marker file and entire browser profile for a fresh QR login."""
        import shutil
        if self._context_file.exists():
            self._context_file.unlink()
        if self._profile_dir.exists():
            shutil.rmtree(self._profile_dir, ignore_errors=True)
        self.logger.info("Session cleared — will re-login on next check.")

    def _login_and_save_session(self) -> None:
        """
        Open a visible browser using the persistent Chrome profile directory,
        wait for the user to scan the QR code, then:

          1. Wait 8 s for WhatsApp to finish writing identity tokens to the
             profile (cookies, IndexedDB, device key).
          2. Save a Playwright storage_state snapshot as a backup.
          3. Wait another 5 s so the profile flush is complete before closing.

        The chrome_profile folder is the primary auth store — WhatsApp writes
        its full device identity there (including keys that cookies alone cannot
        reconstruct).  storage_state is a secondary snapshot used as a quick
        restore if the profile is missing.
        """
        self.logger.info(f"Profile dir : {self._profile_dir}")
        self._profile_dir.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as pw:
                self.logger.info("Launching browser for QR login...")
                try:
                    context = pw.chromium.launch_persistent_context(
                        user_data_dir=str(self._profile_dir),
                        headless=False,
                        args=["--start-maximized",
                              "--disable-blink-features=AutomationControlled"],
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    )
                except Exception as e:
                    self.logger.error(f"Failed to launch browser: {e}")
                    print(f"\nBrowser failed to open. Open manually: {WHATSAPP_URL}")
                    print("Scan the QR code, then re-run the watcher.")
                    raise

                # Use restored tab if available, else open a fresh one
                page = context.pages[0] if context.pages else context.new_page()

                print("\nOpening WhatsApp Web...")
                print(f"URL: {WHATSAPP_URL}")

                try:
                    page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30_000)
                except Exception as e:
                    self.logger.error(f"Failed to load WhatsApp Web: {e}")
                    context.close()
                    raise

                print("\nWaiting for QR code scan...")
                print("On your phone:")
                print("  1. Open WhatsApp")
                print("  2. Menu -> Linked Devices")
                print("  3. Link a Device")
                print("  4. Scan the QR code shown in the browser")

                try:
                    page.wait_for_selector(
                        'canvas[aria-label*="Scan"], canvas, '
                        'div[data-testid="qrcode"], ' + SEL_LOGGED_IN,
                        timeout=30_000,
                    )
                    if page.query_selector(SEL_LOGGED_IN):
                        print("\nAlready logged in!")
                    else:
                        print("\nWaiting for scan (up to 5 minutes)...")
                        page.wait_for_selector(SEL_LOGGED_IN, timeout=300_000)
                        print("\nLogin successful!")

                except PlaywrightTimeout as e:
                    self.logger.error(f"Login timeout: {e}")
                    print("\nLogin timed out. Please try again.")
                    context.close()
                    return

                # ── Settle delay 1: let WhatsApp finish writing identity tokens ─
                # WhatsApp writes device keys and session cookies to IndexedDB
                # after the chat list appears.  Closing immediately loses them.
                print("\nWaiting for session to fully initialise (8 s)...")
                self.logger.info("Post-login settle: waiting 8 s for cookie flush...")
                page.wait_for_timeout(8_000)

                # ── Save storage_state snapshot (backup) ──────────────────────
                self._context_file.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(self._context_file))
                import json as _json
                cookie_count = len(
                    _json.loads(self._context_file.read_text(encoding="utf-8"))
                    .get("cookies", [])
                )
                self.logger.info(
                    f"Storage state saved: {self._context_file} "
                    f"({cookie_count} cookies)"
                )
                print(f"Storage state saved ({cookie_count} cookies).")

                # ── Settle delay 2: let the profile flush complete ─────────────
                # Chrome writes its profile to disk asynchronously; give it 5 s
                # before we call context.close() so nothing is truncated.
                self.logger.info("Post-save drain: waiting 5 s before closing...")
                page.wait_for_timeout(5_000)

                context.close()
                self.logger.info(
                    f"Session saved — profile: {self._profile_dir}  "
                    f"storage_state: {self._context_file}"
                )
                print(f"\nSession saved to: {self._context_file}")

        except PlaywrightTimeout:
            raise
        except Exception as e:
            self.logger.error(f"Session setup failed: {e}")
            raise

    # ── Message scanning ──────────────────────────────────────────────────────

    def _check_unread_messages(self) -> list[dict]:
        """
        Scan WhatsApp Web for new messages using the persistent browser.

        BUG 1 FIX: browser is NOT opened/closed here.  _ensure_browser()
        guarantees self.page is alive; the same tab is reused every cycle.

        BUG 2 FIX: _init_browser() uses context.pages[0] — the restored
        WhatsApp tab — instead of creating a blank new_page().

        BUG 3 FIX: hybrid detection — unread badge OR message key changed
        vs last scan — so new messages are caught even when badge selector fails.

        BUG 4 FIX: skips cycle when WhatsApp reports "messages downloading".
        """
        self._ensure_browser()

        try:
            # Navigate to WhatsApp only when the tab isn't already there
            if "web.whatsapp.com" not in (self.page.url or ""):
                self.logger.info("Navigating to WhatsApp Web...")
                self.page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30_000)

            # BUG 4 FIX: skip cycle during initial message sync
            if self._is_downloading_state():
                self.logger.warning("WhatsApp still syncing — skipping this cycle.")
                return []

            # Wait until chat list is genuinely ready (polls, not a fixed sleep)
            if not self._wait_for_chat_list_ready(timeout_ms=45_000):
                self.logger.warning("Chat list not ready after 45 s — skipping cycle.")
                return []

            # Verify session is still logged in
            if not self.page.query_selector("#pane-side"):
                self.logger.warning("Session expired — triggering re-login.")
                raise SessionExpiredError("WhatsApp session expired.")

            # Collect all visible chat rows (up to 40)
            chat_rows = self._collect_chat_rows()
            self.logger.info(f"Chat rows collected: {len(chat_rows)}")
            for i, row in enumerate(chat_rows[:20]):
                self.logger.info(
                    f"  [{i:02d}] unread={'YES' if row['is_unread'] else 'no ':4s} | "
                    f"new={row['is_new']} | contact={row['chat_name']!r:25} | "
                    f"preview={row['preview'][:60]!r}"
                )

            # For each unread chat, open it and read the actual messages.
            # The sidebar preview is unreliable (truncated, or replaced with a
            # sub-group name for community chats).  Clicking in gives us the
            # full text of every unread message from the conversation pane.
            for row in chat_rows:
                if row["is_unread"]:
                    actual = self._open_chat_and_read(row["chat_name"], row.get("_el"))
                    if actual:
                        self.logger.info(
                            f"  [actual msg] {row['chat_name']!r}: {actual[:120]!r}"
                        )
                        row["preview"] = actual

            # Hybrid: unread badge + state-change detection
            messages = self._select_messages(chat_rows)

            # Persist updated state for next cycle
            self._update_chat_state(chat_rows)
            self._save_chat_state()

            self.logger.info(
                f"Scan complete: {len(chat_rows)} rows | "
                f"{sum(r['is_unread'] for r in chat_rows)} unread | "
                f"{len(messages)} selected"
            )

            if not chat_rows:
                self.logger.warning("0 chat rows found — saving debug snapshot.")
                self._save_debug_snapshot(self.page)

            return messages

        except SessionExpiredError:
            raise
        except PlaywrightTimeout as e:
            self.logger.warning(f"Playwright timeout: {e}")
            # Reset page so next cycle reinitialises cleanly
            self.page = None
            return []
        except Exception as e:
            self.logger.error(f"WhatsApp scan error: {e}")
            self.page = None
            return []

    # ── Per-chat message reading ───────────────────────────────────────────────

    def _open_chat_and_read(self, chat_name: str, el=None) -> str:
        """Click a chat row in the sidebar, read the actual unread message text
        from the conversation pane, and return concatenated text.

        `el` is the Playwright ElementHandle captured during _collect_chat_rows.
        Clicking it directly is the most reliable approach — avoids all
        Unicode / DOM-reflow issues with name-based searching.

        Returns the extracted text, or empty string on failure.
        """
        try:
            if el is not None:
                # Direct click on the handle we already have
                try:
                    el.click(timeout=3_000)
                    self.logger.info(f"[open-chat] clicked via handle: {chat_name!r}")
                except Exception as e:
                    self.logger.info(f"[open-chat] handle click failed ({e}), trying JS fallback")
                    el = None   # fall through to JS fallback

            if el is None:
                # JS fallback — normalize Unicode directional markers on both sides
                self.logger.info(f"[open-chat] JS fallback for: {chat_name!r}")
                clicked = self.page.evaluate("""(chatName) => {
                    function norm(s) {
                        return s.replace(/[\u200b-\u200f\u202a-\u202e\ufeff]/g, '').trim();
                    }
                    const target = norm(chatName);
                    const rows = document.querySelectorAll('[data-testid="cell-frame-container"]');
                    for (const row of rows) {
                        const nameEl =
                            row.querySelector('[data-testid="cell-frame-title"]') ||
                            row.querySelector('span[title]');
                        if (!nameEl) continue;
                        const name = norm(nameEl.getAttribute('title') || nameEl.textContent || '');
                        if (name === target || name.includes(target) || target.includes(name)) {
                            row.click();
                            return name;
                        }
                    }
                    // Last resort: click the first row with an unread badge
                    for (const row of rows) {
                        if (row.querySelector('[data-testid="icon-unread-count"],[data-icon="unread-count"]')) {
                            row.click();
                            return 'badge-fallback';
                        }
                    }
                    return null;
                }""", chat_name)
                if not clicked:
                    self.logger.info(f"[open-chat] JS fallback also failed for {chat_name!r}")
                    return ""
                self.logger.info(f"[open-chat] JS click matched: {clicked!r}")

            # Step 1: wait for the conversation panel shell (#main) to appear
            try:
                self.page.wait_for_selector(
                    '#main [data-testid="conversation-panel-messages"], '
                    '#main [role="application"], '
                    '#main .copyable-area',
                    timeout=10_000,
                )
                self.logger.info(f"[open-chat] panel ready for {chat_name!r}")
            except PlaywrightTimeout:
                self.logger.info(f"[open-chat] panel timeout for {chat_name!r}")
                return ""

            # Step 2: wait for actual message bubbles to populate.
            # WhatsApp's virtual list takes 1-3 s after the panel appears.
            try:
                self.page.wait_for_selector(
                    '#main [data-testid="msg-container"], '
                    '#main .copyable-text',
                    timeout=8_000,
                )
                self.logger.info(f"[open-chat] msg-container found for {chat_name!r}")
            except PlaywrightTimeout:
                self.logger.info(f"[open-chat] no msg-container within 8 s for {chat_name!r} — trying anyway")
                self.page.wait_for_timeout(1_000)

            # Step 3: read messages; if empty, wait 1 s and retry once
            text = self._read_conversation_messages()
            if not text:
                self.logger.info(f"[open-chat] first read empty for {chat_name!r}, retrying in 1 s...")
                self.page.wait_for_timeout(1_500)
                text = self._read_conversation_messages()

            # Step 4: scroll to bottom so WhatsApp sends read receipts and
            # clears the unread badge.  Without this the badge persists and
            # the same chat is detected as unread on every poll cycle.
            try:
                self.page.evaluate("""() => {
                    const msgs = document.querySelector(
                        '#main [data-testid="conversation-panel-messages"]'
                    );
                    if (msgs) msgs.scrollTop = msgs.scrollHeight;
                }""")
                self.page.wait_for_timeout(600)   # let WhatsApp process the read event
            except Exception:
                pass

            self.logger.info(f"[open-chat] result for {chat_name!r}: {text[:100]!r}")
            return text

        except Exception as e:
            self.logger.debug(f"[open-chat] error for {chat_name!r}: {e}")
            return ""

    def _read_conversation_messages(self) -> str:
        """Extract text from the open conversation in #main.

        Four JS strategies, most-specific first:
          1. [data-testid="msg-container"] after the unread divider bar
          2. [data-testid="msg-container"] last 5 (no divider)
          3. .copyable-text elements (older builds)
          4. Any span.selectable-text / span[dir] in #main

        Noise filtered at every level:
          - "unread message", "end-to-end", "encrypted", "click here",
            missed-call notices, pure digits, tick marks.
        """
        try:
            texts: list[str] = self.page.evaluate(r"""() => {
                const NOISE = /unread\s*message|end.to.end|encrypt|click here|missed\s*(voice|video)|voice\s*call|video\s*call/i;

                function isRealText(t) {
                    if (!t || t.length < 3) return false;
                    if (/^\d+$/.test(t)) return false;
                    if (/^[\s\u2713\u2714\ufe0f]+$/.test(t)) return false;
                    if (NOISE.test(t)) return false;
                    return true;
                }

                function textFrom(container) {
                    for (const sel of [
                        'span.selectable-text',
                        'span[dir="ltr"]',
                        'span[dir="rtl"]',
                        'span[class*="copyable"]',
                    ]) {
                        for (const sp of container.querySelectorAll(sel)) {
                            const t = sp.textContent.trim();
                            if (isRealText(t)) return t;
                        }
                    }
                    const raw = container.textContent.trim();
                    return isRealText(raw) ? raw : null;
                }

                const main = document.querySelector('#main');
                if (!main) return [];

                // Find the unread divider bar
                let dividerEl = null;
                for (const el of main.querySelectorAll(
                    '[data-testid="unread-message-bar"],[data-testid="notification-data"],' +
                    'div[role="row"],span[role="button"]'
                )) {
                    if (/\bunread\s*message/i.test(el.textContent)) {
                        dividerEl = el;
                        break;
                    }
                }

                // Strategy 1 & 2: msg-container
                const allContainers = Array.from(
                    main.querySelectorAll('[data-testid="msg-container"]')
                );
                let candidates = [];
                if (dividerEl && allContainers.length) {
                    for (const c of allContainers) {
                        if (dividerEl.compareDocumentPosition(c) & 4) candidates.push(c);
                    }
                }
                if (candidates.length === 0) candidates = allContainers.slice(-5);

                if (candidates.length) {
                    const out = [];
                    for (const c of candidates) { const t = textFrom(c); if (t) out.push(t); }
                    if (out.length) return out;
                }

                // Strategy 3: .copyable-text
                const copyables = Array.from(main.querySelectorAll('.copyable-text'));
                if (copyables.length) {
                    const out = [];
                    for (const c of copyables.slice(-5)) { const t = textFrom(c); if (t) out.push(t); }
                    if (out.length) return out;
                }

                // Strategy 4: any selectable span
                const out = [];
                for (const sp of Array.from(main.querySelectorAll(
                    'span.selectable-text,span[dir="ltr"],span[dir="rtl"]'
                )).slice(-10)) {
                    const t = sp.textContent.trim();
                    if (isRealText(t)) out.push(t);
                }
                return out;
            }""")

            if not texts:
                self.logger.debug("[read-conv] JS returned no texts")
                return ""

            # Strip Unicode directional markers (U+202A LTR, U+202C POP, etc.)
            _dir_marks = re.compile(r'[\u200b-\u200f\u202a-\u202e\ufeff]')
            texts = [_dir_marks.sub('', t).strip() for t in texts]

            clean = [
                t for t in texts
                if t and not re.search(r'\bunread\s*message|\bend.to.end\b|\bencrypt', t, re.IGNORECASE)
            ]

            # Deduplicate consecutive identical lines (same bubble rendered multiple times)
            deduped: list[str] = []
            for t in clean:
                if not deduped or t != deduped[-1]:
                    deduped.append(t)
            clean = deduped
            if not clean:
                self.logger.debug("[read-conv] all texts filtered as noise")
                return ""

            result = " | ".join(clean)
            self.logger.info(f"[read-conv] {len(clean)} message(s): {result[:150]!r}")
            return result

        except Exception as e:
            self.logger.debug(f"[read-conv] error: {e}")
            return ""

    def _js_scan_chats(self, page) -> dict:
        """
        Run JavaScript inside the page to find all chat items and their
        unread status.  Returns a dict with keys:
          selectorUsed  — which CSS selector found items
          totalFound    — total chat items
          chats         — list of {hasBadge, badgeText, contact, text, timestamp}

        This is more reliable than Playwright CSS selectors because:
        - It scopes the search to the chat pane, avoiding false positives
        - It tries multiple selector strategies in priority order
        - It uses the same JS engine WhatsApp uses, so selector quirks are avoided
        - Everything happens in one round-trip
        """
        try:
            return page.evaluate("""() => {
                // Find the chat list pane
                const pane =
                    document.querySelector('#pane-side') ||
                    document.querySelector('[aria-label="Chat list"]') ||
                    document.querySelector('[data-testid="chat-list"]') ||
                    document.body;

                // Try selectors in priority order, scoped to pane
                const itemSelectors = [
                    '[data-testid="cell-frame-container"]',
                    '[data-testid="list-item"]',
                    '#pane-side [role="listitem"]',
                    '[role="listitem"]',
                ];
                let items = [];
                let selectorUsed = '';
                for (const sel of itemSelectors) {
                    const found = pane.querySelectorAll(sel);
                    if (found.length > 0) {
                        items = Array.from(found);
                        selectorUsed = sel;
                        break;
                    }
                }

                const chats = items.map(item => {
                    // Unread badge — try every known selector
                    const badgeEl =
                        item.querySelector('[data-testid="icon-unread-count"]') ||
                        item.querySelector('[data-icon="unread-count"]')       ||
                        item.querySelector('[aria-label*="unread"]')           ||
                        item.querySelector('[data-testid="unread-count"]')     ||
                        item.querySelector('span[aria-label]');

                    // Also detect unread via bold contact name (WhatsApp bolds
                    // the name when there are unread messages)
                    const nameEl =
                        item.querySelector('[data-testid="cell-frame-title"]') ||
                        item.querySelector('span[title]');
                    const nameBold = nameEl
                        ? window.getComputedStyle(nameEl).fontWeight >= 600
                        : false;

                    const hasBadge = !!badgeEl || nameBold;
                    const badgeText = badgeEl ? badgeEl.textContent.trim() : '';

                    // Contact name
                    const contact = nameEl
                        ? (nameEl.getAttribute('title') || nameEl.textContent.trim())
                        : '';

                    // Message preview
                    const textEl =
                        item.querySelector('[data-testid="last-msg-text"] span') ||
                        item.querySelector('[data-testid="last-msg-text"]')       ||
                        item.querySelector('span.selectable-text');
                    const text = textEl ? textEl.textContent.trim() : '';

                    // Timestamp
                    const tsEl = item.querySelector(
                        '[data-testid="cell-frame-timestamp"] span, ' +
                        '[data-testid="cell-frame-timestamp"]'
                    );
                    const timestamp = tsEl ? tsEl.textContent.trim() : '';

                    return { hasBadge, badgeText, contact, text, timestamp };
                });

                return { selectorUsed, totalFound: items.length, chats };
            }""")
        except Exception as e:
            self.logger.error(f"[JS scan] evaluate failed: {e}")
            return {"selectorUsed": None, "totalFound": 0, "chats": []}

    def _save_debug_snapshot(self, page) -> None:
        """Save a screenshot and a slice of page HTML to the session folder.

        Called when both the JS scan and CSS fallback return zero chat items —
        the files help diagnose whether WhatsApp loaded correctly.
        """
        debug_dir = self.session_path / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            shot_path = debug_dir / f"screenshot_{ts}.png"
            page.screenshot(path=str(shot_path), full_page=False)
            self.logger.warning(f"Debug screenshot saved: {shot_path}")
        except Exception as e:
            self.logger.warning(f"Could not save screenshot: {e}")
        try:
            html_path = debug_dir / f"page_{ts}.html"
            html_path.write_text(page.content(), encoding="utf-8", errors="replace")
            self.logger.warning(f"Debug HTML saved: {html_path}")
        except Exception as e:
            self.logger.warning(f"Could not save HTML: {e}")

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
        """Extract and clean the last-message preview from a chat list element.

        Strategy (in order):
          1. [data-testid="last-msg-text"] — the dedicated preview container.
             last-msg-status (delivery receipt ✓✓/"Read") is intentionally
             skipped; it never holds message content.
          2. span.selectable-text / span._11JPr — older WhatsApp builds.
          3. inner_text() fallback — strips: contact name, pure-digit badge
             counts, timestamps (HH:MM), and UI artifact strings before
             picking the first remaining line.

        Any result that is still just a notification badge (pure digits) is
        discarded and an empty string is returned so the caller can decide
        whether to skip the row.
        """
        try:
            # ── 1. Dedicated selectors (most reliable) ──────────────────────
            for sel in (
                '[data-testid="last-msg-text"]',
                'div[data-testid="last-msg-text"] span',
                'span.selectable-text',
                'span._11JPr',
            ):
                el = chat_element.query_selector(sel)
                if el:
                    raw = el.inner_text().strip()
                    if raw and not self._is_notification_badge(raw):
                        self.logger.debug(f"[msg-text via {sel!r}] {raw[:80]!r}")
                        return self._clean_message_text(raw)

            # ── 2. inner_text() fallback with aggressive filtering ──────────
            full_text = (chat_element.inner_text() or "").strip()
            if not full_text:
                return ""

            # Derive contact name for filtering (may be empty)
            try:
                name_el = chat_element.query_selector(SEL_CONTACT_NAME)
                contact_name = (
                    (name_el.get_attribute("title") or name_el.inner_text()).strip()
                    if name_el else ""
                )
            except Exception:
                contact_name = ""

            lines = [ln.strip() for ln in full_text.split("\n") if ln.strip()]
            candidates = [
                ln for ln in lines
                if ln != contact_name                       # skip contact name
                and not self._is_notification_badge(ln)    # skip "3", "12", …
                and not re.match(r'^\d{1,2}:\d{2}', ln)   # skip timestamps
                and ln.lower() not in {a.lower() for a in _UI_ARTIFACTS}
            ]
            if candidates:
                self.logger.debug(f"[msg-text via fallback] {candidates[0][:80]!r}")
                return self._clean_message_text(candidates[0])

        except Exception as e:
            self.logger.debug(f"Could not extract message text: {e}")
        return ""

    def _clean_message_text(self, raw_text: str) -> str:
        """Remove WhatsApp UI artifacts, timestamps, and noise from message text."""
        cleaned = raw_text

        # Remove known UI artifact strings — case-insensitive so "online" and
        # "Online" are both stripped (WhatsApp renders both depending on locale).
        for artifact in _UI_ARTIFACTS:
            cleaned = re.sub(re.escape(artifact), "", cleaned, flags=re.IGNORECASE)

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
    """Stable, content-based ID for deduplication.

    Built from contact slug + SHA-1 of the first 120 chars of message text.
    Using detection time (datetime.now()) caused the same unread message to
    get a different ID on every poll cycle, bypassing _already_logged and
    writing duplicate vault cards.  Content-hash is stable across cycles.
    """
    contact  = _safe_slug(msg.get("contact", "unknown"), max_len=30)
    text     = (msg.get("text") or "").strip()[:120]
    content  = f"{contact}|{text}".encode("utf-8", errors="ignore")
    sha      = hashlib.sha1(content).hexdigest()[:12]
    return f"{contact}_{sha}"


def _already_logged(msg_id: str, vault_path: Path, text: str = "") -> bool:
    """Return True if a vault card with this msg_id OR message text already exists.

    Two checks per file:
    1. message_id frontmatter field — exact hash match (fast, primary)
    2. Message text content inside '## Message Preview' section — catches cards
       saved with an old/combined ID where the same text was already written.

    This handles the transition from time-based IDs and combined-string hashes:
    e.g. "Let's meeting tomorrow morning" was saved as part of a combined card
    "Fix meeting | Let's meeting...", so its individual segment hash won't match
    the stored message_id — but the text itself IS in the file body.
    """
    target_id   = f'message_id: "{msg_id}"'
    target_text = text.strip()[:100] if text else ""

    for folder in ("Inbox", "Needs_Action", "Done"):
        d = vault_path / folder
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.suffix != ".md":
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if target_id in content:
                    return True
                if target_text and target_text in content:
                    return True
            except OSError:
                pass
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

    # "Yesterday"
    if raw.lower() == "yesterday":
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Weekday names: "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
    # WhatsApp shows these for messages 2–6 days old.
    _WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    _WEEKDAY_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    raw_lower = raw.lower()
    if raw_lower in _WEEKDAYS or raw_lower in _WEEKDAY_ABBR:
        if raw_lower in _WEEKDAY_ABBR:
            target = _WEEKDAY_ABBR.index(raw_lower)
        else:
            target = _WEEKDAYS.index(raw_lower)
        days_ago = (now.weekday() - target) % 7 or 7   # always at least 1 day back
        return (now - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Unknown format — fall back to now
    return now


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    vault_path = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
    interval   = 60   # seconds between checks

    if len(sys.argv) > 1:
        vault_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        interval = int(sys.argv[2])

    watcher = WhatsAppWatcher(vault_path=vault_path, check_interval=interval)

    print("=" * 50)
    print("  WhatsApp Watcher — running continuously")
    print(f"  Vault   : {vault_path}")
    print(f"  Interval: every {interval}s")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    watcher.run()
