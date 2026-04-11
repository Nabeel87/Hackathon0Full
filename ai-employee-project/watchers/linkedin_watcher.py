"""
LinkedIn Watcher — Silver Tier
==============================
Monitors LinkedIn notifications (messages, connection requests, comments,
mentions) using Playwright with a persistent browser session.

Session is stored in .credentials/linkedin_session/context.json so headless
login is only needed after the first interactive setup.

Methods (spec-required):
  __init__           — configure paths and intervals
  check_for_updates  — top-level poll: ensure session, scrape, return items
  create_action_file — write LINKEDIN_<ts>_<type>.md to vault Inbox/
  _ensure_session    — verify saved session or trigger login
  _login_and_save_session — headed manual login flow, saves context.json
  _check_messages    — scrape linkedin.com/messaging
  _check_notifications — scrape linkedin.com/notifications
  _extract_notification_data — parse a single page element into a dict
"""

import re
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from watchers.base_watcher import BaseWatcher
from helpers.dashboard_updater import update_activity, update_component_status, update_stats

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SESSION_DIR = (
    Path.home()
    / "Desktop/Hackathon/Hackathon0Full/ai-employee-project/.credentials/linkedin_session"
)

SESSION_FILE_NAME  = "context.json"
SEEN_IDS_FILE_NAME = "linkedin_seen_ids.json"

LINKEDIN_BASE      = "https://www.linkedin.com"
MESSAGING_URL      = f"{LINKEDIN_BASE}/messaging/"   # plain URL; unread filtered by element class
NOTIFICATIONS_URL  = f"{LINKEDIN_BASE}/notifications/"

# Page timeouts (ms)
NAV_TIMEOUT     = 60_000   # 60 seconds for full page navigation
ELEMENT_TIMEOUT = 30_000   # 30 seconds — LinkedIn SPA injects content well after load

# Rate-limit back-off (seconds)
RATE_LIMIT_BACKOFF = 300

# Notification types we care about (everything else is filtered as spam)
NOTIFICATION_TYPES = {"message", "connection_request", "comment", "mention"}


# ── LinkedInWatcher ───────────────────────────────────────────────────────────

class LinkedInWatcher(BaseWatcher):
    """
    Polls LinkedIn for new messages and notifications, creates vault cards.

    First run:  launches a visible browser for manual login → saves context.json
    Subsequent: launches headless, restores context.json, scrapes content.
    """

    def __init__(
        self,
        vault_path: str | Path,
        session_dir: str | Path | None = None,
        check_interval: int = 180,
    ):
        super().__init__(vault_path, check_interval)
        self.session_dir = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._context_file  = self.session_dir / SESSION_FILE_NAME
        self._seen_ids_file = self.session_dir / SEEN_IDS_FILE_NAME
        self._seen_ids: set[str] = self._load_seen_ids()

    # ── Seen-ID persistence ───────────────────────────────────────────────────

    def _load_seen_ids(self) -> set[str]:
        """Load previously seen notification IDs from disk."""
        if self._seen_ids_file.exists():
            try:
                return set(json.loads(self._seen_ids_file.read_text(encoding="utf-8")))
            except Exception as e:
                self.logger.warning("Could not load seen_ids file: %s", e)
        return set()

    def _save_seen_ids(self) -> None:
        """Persist current seen IDs to disk so restarts don't re-process old items."""
        try:
            self._seen_ids_file.write_text(
                json.dumps(list(self._seen_ids), indent=2), encoding="utf-8"
            )
        except Exception as e:
            self.logger.warning("Could not save seen_ids file: %s", e)

    # ── Session management ────────────────────────────────────────────────────

    def _ensure_session(self) -> bool:
        """
        Check whether a valid saved session exists.
        If not, trigger the manual login flow to create one.
        Returns True if a session is ready, raises on unrecoverable failure.
        """
        if self._context_file.exists() and self._context_file.stat().st_size > 20:
            self.logger.info("Using saved session → %s", self._context_file)
            return True

        self.logger.info("No saved session found — starting interactive login.")
        self._login_and_save_session()
        return True

    def _login_and_save_session(self) -> None:
        """
        Open a visible browser so the user can log in manually (including 2FA),
        then save the browser storage state to context.json.
        """
        self.logger.info("Opening browser in headed mode for LinkedIn login.")
        self.logger.info(
            "Complete login and any 2FA in the browser window, then press ENTER here."
        )

        pw, browser, context, page = self._launch_browser(headless=False)
        try:
            page.goto(f"{LINKEDIN_BASE}/login", timeout=NAV_TIMEOUT)
            input(
                "\n[LinkedIn] Log in to LinkedIn (complete 2FA if prompted), "
                "then press ENTER to save session...\n"
            )
            # Save full storage state (cookies + localStorage)
            context.storage_state(path=str(self._context_file))
            self.logger.info("Session saved → %s", self._context_file)
        finally:
            browser.close()
            pw.stop()

    # ── Browser helpers ───────────────────────────────────────────────────────

    def _launch_browser(self, headless: bool):
        """Launch Playwright Chromium and return (playwright, browser, context, page)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright not installed.\n"
                "Run: pip install playwright && playwright install chromium"
            ) from exc

        pw = sync_playwright().start()
        launch_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
        ]

        if self._context_file.exists() and not headless is False:
            # Restore persistent storage state when file exists
            browser = pw.chromium.launch(headless=headless, args=launch_args)
            context = browser.new_context(
                storage_state=str(self._context_file),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
        else:
            browser = pw.chromium.launch(headless=headless, args=launch_args)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )

        page = context.new_page()
        # Mask webdriver flag
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return pw, browser, context, page

    def _is_logged_in(self, page) -> bool:
        """True when the current page looks like an authenticated LinkedIn page."""
        url = page.url
        return url.startswith(LINKEDIN_BASE) and "login" not in url and "authwall" not in url

    def _detect_rate_limit(self, page) -> bool:
        """True when LinkedIn is rate-limiting or showing a checkpoint."""
        url = page.url.lower()
        return "checkpoint" in url or "captcha" in url or "challenge" in url

    def _save_session(self, context) -> None:
        """Refresh context.json so the session stays alive between polls."""
        context.storage_state(path=str(self._context_file))

    # ── Message scraping ──────────────────────────────────────────────────────

    def _check_messages(self, page) -> list[dict]:
        """
        Navigate to linkedin.com/messaging/ and extract unread threads.

        Navigation strategy:
          1. goto with wait_until="commit" — fires on first byte, never times out on SPA
          2. Explicit domcontentloaded + networkidle waits in try/except (non-fatal)
          3. wait_for_selector is best-effort — timeout logs a warning, does NOT abort
          4. Unread threads identified by element-class check, not URL filter
        """
        # ── Navigate ──────────────────────────────────────────────────────────
        try:
            page.goto(MESSAGING_URL, wait_until="commit", timeout=NAV_TIMEOUT)
        except Exception as exc:
            self.logger.warning("Messaging navigation failed: %s", exc)
            return []

        # Non-fatal progressive load waits
        for state, ms in (("domcontentloaded", 20_000), ("networkidle", 15_000)):
            try:
                page.wait_for_load_state(state, timeout=ms)
            except Exception:
                pass

        # ── Wait for conversation list (best-effort) ──────────────────────────
        try:
            page.wait_for_selector(
                "ul.msg-conversations-container__conversations-list, "
                "li[class*='conversations-list-item'], "
                "div[class*='msg-conversation'], "
                ".scaffold-layout__list",
                timeout=ELEMENT_TIMEOUT,
            )
        except Exception:
            self.logger.warning(
                "Messaging: selector wait timed out — scraping anyway "
                "(title=%s url=%s)", page.title(), page.url
            )

        page.wait_for_timeout(2000)  # final JS-render settle

        # ── Scrape conversation rows ──────────────────────────────────────────
        threads = (
            page.query_selector_all("li.msg-conversations-container__conversations-list-item")
            or page.query_selector_all("li[class*='conversations-list-item']")
            or page.query_selector_all("div[class*='msg-conversation-card']")
            or page.query_selector_all(".msg-conversation-listitem")
        )
        self.logger.info(
            "Messaging: %d thread row(s) found (title=%s)", len(threads), page.title()
        )

        items = []
        for thread in threads:
            try:
                # Only process threads with an unread indicator
                is_unread = bool(
                    thread.query_selector(
                        ".msg-conversation-card__unread-count, "
                        "[class*='unread-count'], "
                        "[class*='--unread'], "
                        ".notification-badge"
                    )
                )
                if not is_unread:
                    continue

                data = self._extract_notification_data(thread, page, default_type="message")
                if data and data["id"] not in self._seen_ids:
                    items.append(data)
            except Exception as exc:
                self.logger.debug("Skipping thread parse error: %s", exc)

        return items

    # ── Notification scraping ─────────────────────────────────────────────────

    def _check_notifications(self, page) -> list[dict]:
        """
        Navigate to linkedin.com/notifications and extract relevant items.
        Filters out promotional, job-alert, and system noise.
        wait_for_selector is best-effort only — timeout does NOT abort scraping.
        """
        try:
            page.goto(NOTIFICATIONS_URL, wait_until="commit", timeout=NAV_TIMEOUT)
        except Exception as exc:
            self.logger.warning("Notifications navigation failed: %s", exc)
            return []

        for state, ms in (("domcontentloaded", 20_000), ("networkidle", 15_000)):
            try:
                page.wait_for_load_state(state, timeout=ms)
            except Exception:
                pass

        try:
            page.wait_for_selector(
                "div.nt-card-list, "
                "div.notification-item, "
                "li.notification-item, "
                "article",
                timeout=ELEMENT_TIMEOUT,
            )
        except Exception:
            self.logger.warning(
                "Notifications: selector wait timed out — scraping anyway "
                "(title=%s url=%s)", page.title(), page.url
            )

        page.wait_for_timeout(2000)

        items = []

        cards = page.query_selector_all(
            "div.nt-card, "
            "div.notification-item, "
            "li.notification-item, "
            "article.notification, "
            "[data-urn], "
            "[data-notification-id]"
        )

        for card in cards:
            try:
                data = self._extract_notification_data(card, page, default_type=None)
                if data and data["id"] not in self._seen_ids:
                    items.append(data)
            except Exception as exc:
                self.logger.debug("Skipping notification parse error: %s", exc)

        return items

    # ── Element parsing ───────────────────────────────────────────────────────

    def _extract_notification_data(self, element, page, default_type: str | None) -> dict | None:
        """
        Parse a single page element (card / thread li) into a notification dict.

        Args:
            element:      Playwright ElementHandle
            page:         Current Playwright Page (unused here, kept for extensibility)
            default_type: Force notification_type to this value if classification
                          fails (e.g. 'message' for messaging threads).

        Returns dict with keys:
            id, notification_type, from, content_preview, received,
            raw_time, url, priority
        or None if the element should be skipped.
        """
        # ── Unique ID ─────────────────────────────────────────────────────────
        uid = (
            element.get_attribute("data-urn")
            or element.get_attribute("data-entity-urn")       # current LinkedIn DOM
            or element.get_attribute("data-notification-id")
            or element.get_attribute("data-conversation-id")
            or element.get_attribute("id")
            or ""
        )

        # ── Text content ──────────────────────────────────────────────────────
        text = (element.inner_text() or "").strip()
        if not text or len(text) < 5:
            return None

        # ── Classify ──────────────────────────────────────────────────────────
        notification_type = _classify_notification(text)
        if notification_type == "other":
            if default_type and default_type in NOTIFICATION_TYPES:
                notification_type = default_type
            else:
                return None  # skip promotional / system / job-alert noise

        # ── Sender name ───────────────────────────────────────────────────────
        # Try dedicated name element first, fall back to first text line
        name_el = element.query_selector(
            ".msg-conversation-listitem__participant-names, "
            ".nt-card__text--truncate, "
            ".notification-item__actor-name, "
            "span.actor-name"
        )
        if name_el:
            sender = (name_el.inner_text() or "").strip().splitlines()[0]
        else:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            sender = lines[0] if lines else "Unknown"

        sender = sender[:80]  # safety cap

        # ── Content preview (first 100 chars) ────────────────────────────────
        preview = text[:100].replace("\n", " ").strip()

        # ── URL ───────────────────────────────────────────────────────────────
        link_el = element.query_selector("a[href]")
        href = link_el.get_attribute("href") if link_el else ""
        if href and href.startswith("http"):
            url = href
        elif href:
            url = LINKEDIN_BASE + href
        else:
            url = MESSAGING_URL if notification_type == "message" else NOTIFICATIONS_URL

        # ── Timestamp ─────────────────────────────────────────────────────────
        time_el = element.query_selector(
            "time, "
            "span.time-badge, "
            "span[aria-label*='ago'], "
            ".msg-conversation-listitem__time-stamp"
        )
        raw_time = time_el.inner_text().strip() if time_el else ""

        # ── Stable ID fallback ────────────────────────────────────────────────
        uid = uid or _make_uid(sender, notification_type, raw_time)

        return {
            "id": uid,
            "notification_type": notification_type,
            "from": sender,
            "content_preview": preview,
            "received": datetime.now(tz=timezone.utc),
            "raw_time": raw_time,
            "url": url,
            "priority": _infer_priority(text, notification_type),
        }

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list[dict]:
        """
        Ensure session, open headless browser, scrape messages + notifications.
        Returns list of new item dicts; empty list on any unrecoverable error.
        """
        self.logger.info("Checking LinkedIn...")

        # ── Session gate ──────────────────────────────────────────────────────
        try:
            self._ensure_session()
        except Exception as exc:
            self.logger.error("Session setup failed: %s", exc)
            return []

        pw = browser = context = page = None
        try:
            pw, browser, context, page = self._launch_browser(headless=True)

            # Verify session is still valid
            page.goto(LINKEDIN_BASE, wait_until="commit", timeout=NAV_TIMEOUT)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20_000)
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass

            if not self._is_logged_in(page):
                self.logger.error(
                    "Session expired. Delete %s and re-run to log in again.",
                    self._context_file,
                )
                return []

            if self._detect_rate_limit(page):
                self.logger.warning(
                    "Rate limit / checkpoint detected. Backing off %ds.", RATE_LIMIT_BACKOFF
                )
                return []

            # ── Scrape both sources ───────────────────────────────────────────
            messages      = self._check_messages(page)
            notifications = self._check_notifications(page)

            items = messages + notifications
            # Deduplicate (both sources may occasionally surface the same item)
            seen: set[str] = set()
            unique_items: list[dict] = []
            for item in items:
                if item["id"] not in seen and item["id"] not in self._seen_ids:
                    seen.add(item["id"])
                    unique_items.append(item)

            for item in unique_items:
                self._seen_ids.add(item["id"])

            self.logger.info(
                "Checking LinkedIn... found %d new notification(s)", len(unique_items)
            )

            # Refresh saved session so it stays alive
            self._save_session(context)
            # Persist seen IDs so restarts don't re-process old items
            self._save_seen_ids()
            return unique_items

        except Exception as exc:
            self.logger.error("LinkedIn scrape error: %s", exc)
            return []
        finally:
            for obj in (browser, pw):
                if obj:
                    try:
                        obj.close() if hasattr(obj, "close") else obj.stop()
                    except Exception:
                        pass

    def post_cycle(self, created_count: int) -> None:
        """Update dashboard after new notifications are detected."""
        try:
            from helpers.dashboard_updater import refresh_vault_counts
            update_activity(
                self.vault_path,
                f"LinkedIn Monitor: {created_count} new notification(s) detected",
            )
            update_component_status(self.vault_path, "LinkedIn Monitor Skill", "online")
            update_stats(self.vault_path, "linkedin_checked", created_count, operation="increment")
            refresh_vault_counts(self.vault_path)
        except Exception as exc:
            self.logger.warning("Dashboard update failed: %s", exc)

    def create_action_file(self, item: dict) -> Path:
        """
        Write a LINKEDIN_<timestamp>_<type>.md card to vault Inbox/.
        Logs: "Created LINKEDIN_xxx.md for <type> from <sender>"
        Returns the created file path.
        """
        vault_inbox = self.vault_path / "Inbox"
        vault_inbox.mkdir(parents=True, exist_ok=True)

        dt: datetime = item["received"]
        ts_slug      = dt.strftime("%Y%m%d_%H%M%S")
        ntype        = item["notification_type"]
        sender       = item["from"]

        card_path = vault_inbox / f"LINKEDIN_{ts_slug}_{ntype}.md"

        # Avoid filename collisions in the same second
        counter = 1
        while card_path.exists():
            card_path = vault_inbox / f"LINKEDIN_{ts_slug}_{ntype}_{counter}.md"
            counter += 1

        received_iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        received_fmt = dt.strftime("%Y-%m-%d %H:%M:%S")
        preview_yml  = item["content_preview"].replace('"', "'")
        sender_yml   = sender.replace('"', "'")
        ntype_title  = ntype.replace("_", " ").title()

        card_path.write_text(
            f"""---
type: linkedin_notification
notification_type: {ntype}
from: "{sender_yml}"
content_preview: "{preview_yml}"
received: {received_iso}
priority: {item["priority"]}
status: pending
url: "{item["url"]}"
---

# LinkedIn Notification: New {ntype_title}

**From:** {sender}
**Type:** {ntype_title}
**Received:** {received_fmt}
**Priority:** {item["priority"]}

---

## {ntype_title} Preview

{item["content_preview"]}

---

## Suggested Actions

{_suggested_actions(ntype)}

---

## Notes

_Add context here as you process this notification._
""",
            encoding="utf-8",
        )

        self.logger.info(
            "Created %s for %s from %s", card_path.name, ntype, sender
        )
        return card_path


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _classify_notification(text: str) -> str:
    """Map notification card text to one of the four known types, or 'other'."""
    t = text.lower()

    if any(kw in t for kw in (
        "sent you a message", "replied to your message",
        "messaged you", "sent you a linkedin message",
    )):
        return "message"

    if any(kw in t for kw in (
        "wants to connect", "sent you a connection",
        "invitation to connect", "sent you an invitation",
    )):
        return "connection_request"

    if any(kw in t for kw in (
        "commented on", "commented on your",
        "replied to your comment", "also commented on",
    )):
        return "comment"

    if any(kw in t for kw in (
        "mentioned you", "tagged you",
        "mentioned you in", "mentioned you in a comment",
    )):
        return "mention"

    # Job alerts, promotional, "who viewed your profile", etc.
    return "other"


def _infer_priority(text: str, notification_type: str) -> str:
    """Return 'high' for urgent-keyword messages; 'normal' otherwise."""
    if notification_type == "message":
        t = text.lower()
        if any(kw in t for kw in ("urgent", "asap", "important", "invoice", "payment")):
            return "high"
    return "normal"


def _make_uid(sender: str, ntype: str, raw_time: str) -> str:
    """Stable-ish ID when no data-urn is present on the element."""
    raw = f"{sender}_{ntype}_{raw_time}"
    return re.sub(r"[^\w]", "_", raw)[:60]


def _suggested_actions(ntype: str) -> str:
    return {
        "message": (
            "- [ ] Reply to message\n"
            "- [ ] Connect with sender\n"
            "- [ ] Mark as important\n"
            "- [ ] Archive conversation"
        ),
        "connection_request": (
            "- [ ] Review sender's profile\n"
            "- [ ] Accept or ignore the connection request\n"
            "- [ ] If relevant, send a welcome message"
        ),
        "comment": (
            "- [ ] Read the comment in context\n"
            "- [ ] Reply if appropriate\n"
            "- [ ] Like or acknowledge if no reply needed"
        ),
        "mention": (
            "- [ ] Review the post/comment where you were mentioned\n"
            "- [ ] Respond or engage as appropriate\n"
            "- [ ] Share if it adds value to your network"
        ),
    }.get(
        ntype,
        "- [ ] Review the notification\n- [ ] Take appropriate action\n- [ ] Archive when resolved",
    )


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    vault = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
    session = Path(
        "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/"
        "ai-employee-project/.credentials/linkedin_session"
    )

    if len(sys.argv) > 1:
        vault = Path(sys.argv[1])
    if len(sys.argv) > 2:
        session = Path(sys.argv[2])

    watcher = LinkedInWatcher(vault_path=vault, session_dir=session)
    watcher.run()
