"""
helpers/linkedin_poster.py

Automates LinkedIn post creation using a saved Playwright browser session.
Session is loaded from .credentials/linkedin_session/context.json (storage
state saved by LinkedInWatcher — must run watcher first to log in).

Usage
-----
From Python:
    from helpers.linkedin_poster import post_to_linkedin
    result = post_to_linkedin("Hello LinkedIn!", vault_path="/path/to/vault")

CLI:
    python helpers/linkedin_poster.py --content "My post text"
    python helpers/linkedin_poster.py --test
    python helpers/linkedin_poster.py --content "My post text" --test-mode
    LINKEDIN_TEST_MODE=true python helpers/linkedin_poster.py --content "My post text"
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SESSION_DIR = _PROJECT_ROOT / ".credentials" / "linkedin_session"
SESSION_FILE_NAME   = "context.json"

DEFAULT_VAULT = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)

# Project-level log directory (not inside vault)
LOG_DIR  = _PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "linkedin_posts.log"

LINKEDIN_BASE  = "https://www.linkedin.com"
FEED_URL       = f"{LINKEDIN_BASE}/feed/"
NAV_TIMEOUT    = 30_000   # ms — overall page navigation
ACTION_TIMEOUT = 15_000   # ms — element interactions
RETRY_DELAY    = 5        # seconds before single retry


# ── Logger ────────────────────────────────────────────────────────────────────

def _build_logger() -> logging.Logger:
    """
    Return the shared linkedin_poster logger.
    Log file: logs/linkedin_posts.log  (project root, never inside vault).
    Format:   [timestamp] [SUCCESS/FAILED] Content preview (50 chars) | URL: ...
    """
    logger = logging.getLogger("linkedin_poster")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Concise format for the dedicated post log
    log_fmt = logging.Formatter(
        "[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Richer format for console
    console_fmt = logging.Formatter(
        "[%(asctime)s] [linkedin_poster] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(log_fmt)
    logger.addHandler(file_handler)

    return logger


def _log_outcome(logger: logging.Logger, success: bool, preview: str, url: str) -> None:
    """Write a structured outcome line to the log (never logs full content)."""
    status  = "SUCCESS" if success else "FAILED"
    snippet = (preview[:50] + "…") if len(preview) > 50 else preview
    logger.info("[%s] %s | URL: %s", status, snippet, url or "—")


# ── Session helpers ───────────────────────────────────────────────────────────

def _context_file(session_dir: Path) -> Path:
    return session_dir / SESSION_FILE_NAME


def _session_exists(session_dir: Path) -> bool:
    cf = _context_file(session_dir)
    return cf.exists() and cf.stat().st_size > 20


# ── Browser factory ───────────────────────────────────────────────────────────

def _launch_browser(session_dir: Path, headless: bool = True):
    """
    Launch headless Chromium with the saved storage state (context.json).
    Returns (playwright, browser, context, page).
    Raises RuntimeError if Playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Playwright not installed. Run:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from exc

    pw      = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
        ],
    )

    ctx_file = _context_file(session_dir)
    context  = browser.new_context(
        storage_state=str(ctx_file) if ctx_file.exists() else None,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page = context.new_page()
    # Mask automation fingerprint
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return pw, browser, context, page


def _is_logged_in(page) -> bool:
    url = page.url
    return (
        url.startswith(LINKEDIN_BASE)
        and "login"    not in url
        and "authwall" not in url
    )


def _is_rate_limited(page) -> bool:
    url = page.url.lower()
    return "checkpoint" in url or "captcha" in url or "challenge" in url


def _cleanup(browser, pw) -> None:
    for obj in (browser, pw):
        if obj is None:
            continue
        try:
            obj.close() if hasattr(obj, "close") else obj.stop()
        except Exception:
            pass


# ── Core posting logic ────────────────────────────────────────────────────────

def _do_post(page, content: str, image_path: Path | None, logger: logging.Logger) -> str:
    """
    Drive the LinkedIn post composer.
    Returns the post URL (best-effort; falls back to feed URL).
    Raises on any interaction failure so the caller can retry.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    # 1. Navigate to feed
    logger.info("Navigating to LinkedIn feed…")
    page.goto(FEED_URL, timeout=NAV_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    # 2. Click "Start a post"
    try:
        start_btn = page.wait_for_selector(
            'button[aria-label*="Start a post"], '
            ".share-box-feed-entry__trigger, "
            "[data-control-name='share.sharebox_open'], "
            "button:has-text('Start a post')",
            timeout=ACTION_TIMEOUT,
        )
    except PlaywrightTimeout as exc:
        raise RuntimeError("Could not find 'Start a post' button") from exc

    start_btn.click()
    logger.info("Post composer opened.")

    # 3. Enter content
    try:
        editor = page.wait_for_selector(
            "div.ql-editor, "
            "div[data-placeholder='What do you want to talk about?'], "
            "div[role='textbox'][contenteditable='true']",
            timeout=ACTION_TIMEOUT,
        )
    except PlaywrightTimeout as exc:
        raise RuntimeError("Post text area not found") from exc

    editor.click()
    editor.type(content, delay=25)  # slight delay mimics human typing
    logger.info("Content entered (%d chars).", len(content))

    # 4. Optional image upload
    if image_path:
        if not image_path.exists():
            logger.warning("Image file not found — skipping image: %s", image_path)
        else:
            media_btn = page.query_selector(
                'button[aria-label*="Add a photo"], '
                'button[aria-label*="photo"], '
                'button[aria-label*="image"], '
                "[data-control-name='add_photo']"
            )
            if media_btn:
                media_btn.click()
                try:
                    file_input = page.wait_for_selector(
                        "input[type='file']", timeout=ACTION_TIMEOUT
                    )
                    file_input.set_input_files(str(image_path))
                    logger.info("Image attached: %s", image_path.name)
                    page.wait_for_timeout(3_000)   # wait for upload preview
                except PlaywrightTimeout as exc:
                    raise RuntimeError("Image file input not found after clicking button") from exc
            else:
                logger.warning("Image upload button not found — skipping image.")

    # 5. Click Post
    try:
        post_btn = page.wait_for_selector(
            "button.share-actions__primary-action, "
            "button[data-control-name='share.post'], "
            "button[aria-label*='Post']:not([disabled]), "
            "button:has-text('Post'):not([disabled])",
            timeout=ACTION_TIMEOUT,
        )
    except PlaywrightTimeout as exc:
        raise RuntimeError("Post submit button not found") from exc

    post_btn.click()
    logger.info("Post button clicked — waiting for publish confirmation…")

    # 6. Wait for composer to close (signals successful post)
    try:
        page.wait_for_selector(
            "div.ql-editor, div[data-placeholder]",
            state="detached",
            timeout=ACTION_TIMEOUT,
        )
    except PlaywrightTimeout as exc:
        raise RuntimeError("Composer did not close after clicking Post — may have failed") from exc

    # 7. Extract post URL
    return _extract_post_url(page, logger)


def _extract_post_url(page, logger: logging.Logger) -> str:
    """
    Best-effort: find the URL of the just-published post in the feed.
    Falls back to FEED_URL so callers always get a valid string.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
        link = page.query_selector(
            "div.feed-shared-update-v2 a[href*='/feed/update/'], "
            "article a[href*='/feed/update/'], "
            "a[href*='ugcPost']"
        )
        if link:
            href = link.get_attribute("href") or ""
            if href.startswith("http"):
                return href
            if href:
                return LINKEDIN_BASE + href
    except Exception as exc:
        logger.debug("Post URL extraction failed (non-fatal): %s", exc)
    return FEED_URL


def _extract_post_id(post_url: str) -> str | None:
    """Parse the post ID out of a LinkedIn /feed/update/ URL."""
    import re
    match = re.search(r"(urn:li:[^&?/]+|ugcPost:\d+|\d{10,})", post_url)
    return match.group(1) if match else None


# ── Public API ────────────────────────────────────────────────────────────────

def post_to_linkedin(
    content: str,
    image_path: str | Path | None = None,
    vault_path: str | Path | None = None,
    session_dir: str | Path | None = None,
) -> dict:
    """
    Post content to LinkedIn using a saved browser session (context.json).

    Parameters
    ----------
    content      : Text of the post.
    image_path   : Optional path to an image file to attach.
    vault_path   : Unused (kept for API compatibility); logs always go to logs/.
    session_dir  : Override for .credentials/linkedin_session/ directory.

    Returns
    -------
    dict:
        success   (bool)
        post_url  (str | None)
        post_id   (str | None)
        timestamp (str — ISO UTC)
        error     (str | None)
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    s_dir   = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
    img     = Path(image_path)  if image_path  else None
    logger  = _build_logger()
    now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    preview = content[:80].replace("\n", " ")

    def _fail(error_msg: str) -> dict:
        _log_outcome(logger, False, preview, "—")
        return {
            "success":   False,
            "post_url":  None,
            "post_id":   None,
            "timestamp": now_iso,
            "error":     error_msg,
        }

    # ── Test mode ─────────────────────────────────────────────────────────────
    if os.getenv("LINKEDIN_TEST_MODE", "false").lower() == "true":
        logger.info("TEST MODE: Simulating LinkedIn post (not actually posting)")
        logger.info("TEST MODE: Would have posted: %s…", preview[:100])
        simulated_id  = "test_post_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        simulated_url = f"https://www.linkedin.com/posts/test-{simulated_id}"
        _log_outcome(logger, True, preview, simulated_url)
        return {
            "success":   True,
            "post_url":  simulated_url,
            "post_id":   simulated_id,
            "timestamp": now_iso,
            "test_mode": True,
            "error":     None,
        }

    # ── Session gate ──────────────────────────────────────────────────────────
    if not _session_exists(s_dir):
        return _fail("LinkedIn session not found. Run watcher first.")

    # ── Attempt 1 + single retry ──────────────────────────────────────────────
    last_error = ""
    for attempt in range(1, 3):       # 2 attempts: original + one retry
        logger.info("Post attempt %d/2 | preview: '%s…'", attempt, preview[:50])
        pw = browser = context = page = None
        try:
            pw, browser, context, page = _launch_browser(s_dir, headless=True)

            # Verify session
            page.goto(LINKEDIN_BASE, timeout=NAV_TIMEOUT)

            if not _is_logged_in(page):
                return _fail("LinkedIn session expired. Please re-login.")

            if _is_rate_limited(page):
                return _fail("Rate limited by LinkedIn. Try again later.")

            post_url = _do_post(page, content, img, logger)
            post_id  = _extract_post_id(post_url)

            # Refresh context.json so session stays alive
            context.storage_state(path=str(_context_file(s_dir)))

            _log_outcome(logger, True, preview, post_url)
            return {
                "success":   True,
                "post_url":  post_url,
                "post_id":   post_id,
                "timestamp": now_iso,
                "error":     None,
            }

        except (PlaywrightTimeout, RuntimeError, Exception) as exc:
            last_error = str(exc)
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt == 1:
                logger.info("Retrying once in %ds…", RETRY_DELAY)
                time.sleep(RETRY_DELAY)

        finally:
            _cleanup(browser, pw)

    return _fail(f"Post failed after 2 attempts. Last error: {last_error}")


# ── Test helper ───────────────────────────────────────────────────────────────

def test_linkedin_post() -> dict:
    """
    Simulate a post using LINKEDIN_TEST_MODE — no session required, nothing published.
    Run:  python helpers/linkedin_poster.py --test
    """
    os.environ["LINKEDIN_TEST_MODE"] = "true"
    test_content = "Test post from AI Employee system - testing LinkedIn integration!"
    result = post_to_linkedin(test_content)
    print(f"Result: {result}")
    return result


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post to LinkedIn via Playwright")
    parser.add_argument("--content", type=str, default="", help="Post text content")
    parser.add_argument("--image",   type=str, default="", help="Optional image path")
    parser.add_argument(
        "--session",
        type=str,
        default=str(DEFAULT_SESSION_DIR),
        help="Path to linkedin_session directory",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Simulate posting a fixed test message via LINKEDIN_TEST_MODE",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Set LINKEDIN_TEST_MODE=true for this run (use with --content)",
    )
    args = parser.parse_args()

    if args.test_mode:
        os.environ["LINKEDIN_TEST_MODE"] = "true"

    if args.test:
        test_linkedin_post()
    elif args.content:
        res = post_to_linkedin(
            content=args.content,
            image_path=args.image or None,
            session_dir=args.session,
        )
        for key, value in res.items():
            print(f"  {key:<12}: {value}")
    else:
        parser.print_help()
