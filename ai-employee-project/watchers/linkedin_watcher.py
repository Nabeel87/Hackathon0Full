"""
LinkedIn Watcher — Silver Tier
==============================
Monitors LinkedIn notifications (messages, connection requests, comments,
mentions) using Playwright with persistent session cookies.

Session is stored in .credentials/linkedin_session/ so headless login is
only needed after the first interactive setup.
"""

import re
import sys
import json
import time
import logging
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

LINKEDIN_BASE = "https://www.linkedin.com"
NOTIFICATIONS_URL = f"{LINKEDIN_BASE}/notifications/"
MESSAGING_URL = f"{LINKEDIN_BASE}/messaging/"

# Milliseconds to wait for page elements
NAV_TIMEOUT = 30_000
ELEMENT_TIMEOUT = 10_000

# Back-off on rate-limit (seconds)
RATE_LIMIT_BACKOFF = 300

# Notification types we care about
NOTIFICATION_TYPES = {"message", "connection_request", "comment", "mention"}


# ── LinkedInWatcher ───────────────────────────────────────────────────────────

class LinkedInWatcher(BaseWatcher):
    """
    Polls LinkedIn for new notifications and creates vault action cards.

    First run:  launches a visible browser for manual login, then saves cookies.
    Subsequent: launches headless, restores cookies, scrapes notifications.
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
        self._cookies_file = self.session_dir / "cookies.json"
        self._seen_ids: set[str] = set()
        self._browser = None
        self._playwright = None

    # ── Session helpers ───────────────────────────────────────────────────────

    def _session_exists(self) -> bool:
        return self._cookies_file.exists() and self._cookies_file.stat().st_size > 10

    def _save_cookies(self, context) -> None:
        cookies = context.cookies()
        self._cookies_file.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        self.logger.info(f"Session saved ({len(cookies)} cookies) → {self._cookies_file}")

    def _load_cookies(self, context) -> None:
        cookies = json.loads(self._cookies_file.read_text(encoding="utf-8"))
        context.add_cookies(cookies)
        self.logger.info(f"Session restored ({len(cookies)} cookies)")

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    def _launch_browser(self, headless: bool):
        """Launch Playwright browser and return (playwright, browser, context, page)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright not installed. Run: uv pip install playwright "
                "&& playwright install chromium"
            ) from exc

        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
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
        # Mask webdriver flag without playwright-stealth dependency
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return pw, browser, context, page

    def _interactive_login(self) -> None:
        """Open a visible browser so the user can log in manually, then save cookies."""
        self.logger.info("No saved session found. Opening browser for manual LinkedIn login.")
        self.logger.info("Log in, complete any 2FA, then press ENTER here to save session.")

        pw, browser, context, page = self._launch_browser(headless=False)
        try:
            page.goto(f"{LINKEDIN_BASE}/login", timeout=NAV_TIMEOUT)
            input("\n[LinkedIn] Log in, then press ENTER to save session and continue...\n")
            self._save_cookies(context)
        finally:
            browser.close()
            pw.stop()

    def _is_logged_in(self, page) -> bool:
        """Return True if the current page looks like an authenticated LinkedIn page."""
        return page.url.startswith(LINKEDIN_BASE) and "login" not in page.url

    # ── Scraping ──────────────────────────────────────────────────────────────

    def _scrape_notifications(self, page) -> list[dict]:
        """Navigate to notifications page and extract items."""
        try:
            page.goto(NOTIFICATIONS_URL, timeout=NAV_TIMEOUT)
            page.wait_for_selector(
                "div.nt-card-list, div.notification-item, article",
                timeout=ELEMENT_TIMEOUT,
            )
        except Exception as e:
            self.logger.warning(f"Notifications page load issue: {e}")
            return []

        items = []

        # LinkedIn notification cards — selector may vary by account layout
        cards = page.query_selector_all(
            "div.nt-card, div.notification-item, li.notification-item, article.notification"
        )
        if not cards:
            # Fallback: grab any card-like elements
            cards = page.query_selector_all("[data-urn], [data-notification-id]")

        for card in cards:
            try:
                item = self._parse_notification_card(card, page)
                if item and item["id"] not in self._seen_ids:
                    items.append(item)
            except Exception as e:
                self.logger.debug(f"Skipping card parse error: {e}")

        return items

    def _parse_notification_card(self, card, page) -> dict | None:
        """Extract metadata from a single notification card element."""
        # Unique ID from data attributes
        uid = (
            card.get_attribute("data-urn")
            or card.get_attribute("data-notification-id")
            or card.get_attribute("id")
            or ""
        )

        # Text content for classification
        text = (card.inner_text() or "").strip()
        if not text or len(text) < 5:
            return None

        notification_type = _classify_notification(text)
        if notification_type not in NOTIFICATION_TYPES:
            return None  # skip promotional / system / job-alert noise

        # Try to extract the sender name (first non-empty line is usually the name)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        sender = lines[0] if lines else "Unknown"
        preview = text[:100].replace("\n", " ")

        # Notification URL
        link_el = card.query_selector("a[href]")
        href = link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else (LINKEDIN_BASE + href if href else NOTIFICATIONS_URL)

        # Timestamp — LinkedIn uses relative times ("2h", "Just now")
        time_el = card.query_selector("time, span.time-badge, span[aria-label*='ago']")
        raw_time = time_el.inner_text().strip() if time_el else ""

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
        """Log into LinkedIn (or restore session) and scrape new notifications."""
        if not self._session_exists():
            self._interactive_login()

        pw, browser, context, page = self._launch_browser(headless=True)
        try:
            self._load_cookies(context)
            page.goto(LINKEDIN_BASE, timeout=NAV_TIMEOUT)

            # Session expired check
            if not self._is_logged_in(page):
                self.logger.warning("Session expired. Deleting cookies and requesting re-login.")
                self._cookies_file.unlink(missing_ok=True)
                browser.close()
                pw.stop()
                self._interactive_login()
                return []

            # Rate-limit detection (LinkedIn redirects or shows CAPTCHA)
            if "checkpoint" in page.url or "captcha" in page.url.lower():
                self.logger.warning(
                    f"Rate limit / checkpoint detected. Backing off {RATE_LIMIT_BACKOFF}s."
                )
                time.sleep(RATE_LIMIT_BACKOFF)
                return []

            items = self._scrape_notifications(page)

            for item in items:
                self._seen_ids.add(item["id"])

            # Refresh cookies to extend session
            self._save_cookies(context)
            return items

        except Exception as e:
            self.logger.error(f"LinkedIn scrape error: {e}")
            return []
        finally:
            try:
                browser.close()
                pw.stop()
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
        except Exception as e:
            self.logger.warning(f"Dashboard update failed: {e}")

    def create_action_file(self, item: dict) -> Path:
        """Write a LINKEDIN_*.md card to vault Inbox/ and return its path."""
        vault_inbox = self.vault_path / "Inbox"
        vault_inbox.mkdir(parents=True, exist_ok=True)

        dt: datetime = item["received"]
        ts_slug = dt.strftime("%Y%m%d_%H%M%S")
        ntype = item["notification_type"]
        card_path = vault_inbox / f"LINKEDIN_{ts_slug}_{ntype}.md"

        # Avoid collisions
        counter = 1
        while card_path.exists():
            card_path = vault_inbox / f"LINKEDIN_{ts_slug}_{ntype}_{counter}.md"
            counter += 1

        detected_iso = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        preview = item["content_preview"].replace('"', "'")
        sender = item["from"].replace('"', "'")

        card_path.write_text(
            f"""---
type: linkedin_notification
notification_type: {ntype}
from: "{sender}"
content_preview: "{preview}"
received: "{detected_iso}"
priority: {item["priority"]}
status: pending
url: "{item["url"]}"
---

# LinkedIn {ntype.replace("_", " ").title()}: {sender}

**From:** {sender}
**Type:** {ntype.replace("_", " ").title()}
**Received:** {detected_iso}
**Priority:** {item["priority"]}
**URL:** {item["url"]}

---

## Preview

> {item["content_preview"]}

---

## Suggested Actions

{_suggested_actions(ntype)}

---

## Notes

_Add context here as you process this notification._
""",
            encoding="utf-8",
        )
        return card_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _classify_notification(text: str) -> str:
    """Classify a notification card's text into one of the known types."""
    t = text.lower()
    if any(kw in t for kw in ("sent you a message", "replied to your message", "messaged you")):
        return "message"
    if any(kw in t for kw in ("wants to connect", "sent you a connection", "invitation to connect")):
        return "connection_request"
    if any(kw in t for kw in ("commented on", "commented on your", "replied to your comment")):
        return "comment"
    if any(kw in t for kw in ("mentioned you", "tagged you", "mentioned you in")):
        return "mention"
    # Job alerts and promotional — return unmatched so caller can skip
    return "other"


def _infer_priority(text: str, notification_type: str) -> str:
    t = text.lower()
    if notification_type == "message":
        if any(kw in t for kw in ("urgent", "asap", "important", "invoice", "payment")):
            return "high"
    if notification_type == "connection_request":
        return "normal"
    return "normal"


def _make_uid(sender: str, ntype: str, raw_time: str) -> str:
    """Generate a stable-ish ID when no data-urn is available."""
    slug = re.sub(r"[^\w]", "_", f"{sender}_{ntype}_{raw_time}")[:60]
    return slug


def _suggested_actions(ntype: str) -> str:
    actions = {
        "message": (
            "- [ ] Read the full message on LinkedIn\n"
            "- [ ] Decide: reply, forward, or archive\n"
            "- [ ] If action needed, create a task in Needs_Action/"
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
    }
    return actions.get(
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
