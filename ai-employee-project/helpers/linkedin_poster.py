"""
helpers/linkedin_poster.py

Automates LinkedIn post creation using a saved Playwright browser session.

Usage
-----
From Python:
    from helpers.linkedin_poster import post_to_linkedin
    result = post_to_linkedin("Hello LinkedIn!", vault_path=vault)

CLI / manual test:
    python helpers/linkedin_poster.py
    python helpers/linkedin_poster.py --content "Test post" --vault /path/to/vault
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SESSION_DIR = (
    _PROJECT_ROOT / ".credentials" / "linkedin_session"
)

DEFAULT_VAULT = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)

LINKEDIN_BASE   = "https://www.linkedin.com"
FEED_URL        = f"{LINKEDIN_BASE}/feed/"
NAV_TIMEOUT     = 30_000   # ms
ACTION_TIMEOUT  = 15_000   # ms
MAX_RETRIES     = 3
RETRY_DELAY     = 5        # seconds between retries
RATE_LIMIT_WAIT = 300      # seconds to back off on rate-limit


# ── Logger ────────────────────────────────────────────────────────────────────

def _get_logger(vault_path: Path | None) -> logging.Logger:
    logger = logging.getLogger("linkedin_poster")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "[%(asctime)s] [linkedin_poster] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File handler — logs/linkedin_posts.log inside vault
    if vault_path:
        log_dir = vault_path / "Logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "linkedin_posts.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


# ── Session helpers ───────────────────────────────────────────────────────────

def _cookies_file(session_dir: Path) -> Path:
    return session_dir / "cookies.json"


def _session_exists(session_dir: Path) -> bool:
    cf = _cookies_file(session_dir)
    return cf.exists() and cf.stat().st_size > 10


def _save_cookies(context, session_dir: Path, logger: logging.Logger) -> None:
    cookies = context.cookies()
    _cookies_file(session_dir).write_text(
        json.dumps(cookies, indent=2), encoding="utf-8"
    )
    logger.info(f"Session saved ({len(cookies)} cookies)")


def _load_cookies(context, session_dir: Path, logger: logging.Logger) -> None:
    cookies = json.loads(_cookies_file(session_dir).read_text(encoding="utf-8"))
    context.add_cookies(cookies)
    logger.info(f"Session restored ({len(cookies)} cookies)")


# ── Browser factory ───────────────────────────────────────────────────────────

def _launch_browser(headless: bool = True):
    """Return (playwright, browser, context, page) with stealth applied."""
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import stealth_sync
    except ImportError as exc:
        raise RuntimeError(
            "Playwright not installed. Run:\n"
            "  uv pip install playwright playwright-stealth\n"
            "  playwright install chromium"
        ) from exc

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()
    stealth_sync(page)
    return pw, browser, context, page


def _is_logged_in(page) -> bool:
    return page.url.startswith(LINKEDIN_BASE) and "login" not in page.url


def _check_rate_limit(page) -> bool:
    return "checkpoint" in page.url or "captcha" in page.url.lower()


# ── Core posting logic ────────────────────────────────────────────────────────

def _do_post(page, content: str, image_path: Path | None, logger: logging.Logger) -> str:
    """
    Perform the actual LinkedIn post interaction.
    Returns the post URL (best-effort; falls back to feed URL).
    Raises on failure.
    """
    logger.info("Navigating to LinkedIn feed")
    page.goto(FEED_URL, timeout=NAV_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    # ── Open post composer ────────────────────────────────────────────────────
    start_btn = page.wait_for_selector(
        "button.share-box-feed-entry__trigger, "
        "[data-control-name='share.sharebox_open'], "
        "button:has-text('Start a post')",
        timeout=ACTION_TIMEOUT,
    )
    start_btn.click()
    logger.info("Post composer opened")

    # ── Type content ──────────────────────────────────────────────────────────
    editor = page.wait_for_selector(
        "div.ql-editor, div[data-placeholder='What do you want to talk about?'], "
        "div[contenteditable='true']",
        timeout=ACTION_TIMEOUT,
    )
    editor.click()
    editor.type(content, delay=30)   # slight delay mimics human typing
    logger.info(f"Content entered ({len(content)} chars)")

    # ── Upload image (optional) ───────────────────────────────────────────────
    if image_path:
        if not image_path.exists():
            logger.warning(f"Image not found, skipping: {image_path}")
        else:
            # Click the media/image button inside the composer
            media_btn = page.query_selector(
                "button[aria-label*='photo'], button[aria-label*='image'], "
                "button[data-control-name='add_photo']"
            )
            if media_btn:
                media_btn.click()
                file_input = page.wait_for_selector(
                    "input[type='file']", timeout=ACTION_TIMEOUT
                )
                file_input.set_input_files(str(image_path))
                logger.info(f"Image attached: {image_path.name}")
                # Wait for upload preview
                page.wait_for_timeout(3000)
            else:
                logger.warning("Image upload button not found — skipping image")

    # ── Submit ────────────────────────────────────────────────────────────────
    post_btn = page.wait_for_selector(
        "button.share-actions__primary-action, "
        "button[data-control-name='share.post'], "
        "button:has-text('Post'):not([disabled])",
        timeout=ACTION_TIMEOUT,
    )
    post_btn.click()
    logger.info("Post button clicked — waiting for publish confirmation")

    # Wait for composer to close (signals successful post)
    page.wait_for_selector(
        "div.ql-editor, div[data-placeholder]",
        state="detached",
        timeout=ACTION_TIMEOUT,
    )

    # ── Extract post URL (best-effort) ────────────────────────────────────────
    post_url = _extract_post_url(page, logger)
    return post_url


def _extract_post_url(page, logger: logging.Logger) -> str:
    """Try to find the URL of the just-published post in the feed."""
    try:
        # After posting LinkedIn usually shows the post at the top of feed
        page.wait_for_load_state("networkidle", timeout=10_000)
        first_post = page.query_selector(
            "div.feed-shared-update-v2 a[href*='/feed/update/'], "
            "article a[href*='/feed/update/']"
        )
        if first_post:
            href = first_post.get_attribute("href") or ""
            if href.startswith("http"):
                return href
            if href:
                return LINKEDIN_BASE + href
    except Exception as e:
        logger.debug(f"Could not extract post URL: {e}")
    return FEED_URL


# ── Public API ────────────────────────────────────────────────────────────────

def post_to_linkedin(
    content: str,
    image_path: str | Path | None = None,
    vault_path: str | Path | None = None,
    session_dir: str | Path | None = None,
) -> dict:
    """
    Post content to LinkedIn using a saved browser session.

    Parameters
    ----------
    content      : Text of the post.
    image_path   : Optional path to an image file to attach.
    vault_path   : Path to AI_Employee_Vault (used for log file).
    session_dir  : Override for the .credentials/linkedin_session/ dir.

    Returns
    -------
    dict with keys:
        success      (bool)
        post_url     (str)
        timestamp    (str, ISO UTC)
        error        (str | None)
        retry_after  (int | None)  — seconds, set on rate-limit
    """
    vault  = Path(vault_path)  if vault_path  else DEFAULT_VAULT
    s_dir  = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
    img    = Path(image_path)  if image_path  else None
    logger = _get_logger(vault)

    content_preview = content[:80].replace("\n", " ")
    now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    logger.info(f"Post attempt | preview: '{content_preview}...' | image: {img}")

    # ── Session check ─────────────────────────────────────────────────────────
    if not _session_exists(s_dir):
        msg = "No saved LinkedIn session. Run linkedin_watcher.py first to log in."
        logger.error(msg)
        return {"success": False, "post_url": None, "timestamp": now_iso,
                "error": msg, "retry_after": None}

    # ── Retry loop ────────────────────────────────────────────────────────────
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Attempt {attempt}/{MAX_RETRIES}")
        pw, browser, context, page = _launch_browser(headless=True)
        try:
            _load_cookies(context, s_dir, logger)
            page.goto(LINKEDIN_BASE, timeout=NAV_TIMEOUT)

            # Session expired
            if not _is_logged_in(page):
                msg = "LinkedIn session expired. Delete cookies and re-run watcher to log in."
                logger.error(msg)
                _cookies_file(s_dir).unlink(missing_ok=True)
                return {"success": False, "post_url": None, "timestamp": now_iso,
                        "error": msg, "retry_after": None}

            # Rate limit / checkpoint
            if _check_rate_limit(page):
                logger.warning(f"Rate limit detected. Retry after {RATE_LIMIT_WAIT}s.")
                return {"success": False, "post_url": None, "timestamp": now_iso,
                        "error": "Rate limited by LinkedIn.",
                        "retry_after": RATE_LIMIT_WAIT}

            post_url = _do_post(page, content, img, logger)

            # Refresh cookies after successful post
            _save_cookies(context, s_dir, logger)

            logger.info(f"SUCCESS | url: {post_url} | timestamp: {now_iso}")
            return {
                "success":     True,
                "post_url":    post_url,
                "timestamp":   now_iso,
                "error":       None,
                "retry_after": None,
            }

        except Exception as exc:
            last_error = str(exc)
            logger.warning(f"Attempt {attempt} failed: {exc}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY}s…")
                time.sleep(RETRY_DELAY)
        finally:
            try:
                browser.close()
                pw.stop()
            except Exception:
                pass

    logger.error(f"All {MAX_RETRIES} attempts failed. Last error: {last_error}")
    return {
        "success":     False,
        "post_url":    None,
        "timestamp":   now_iso,
        "error":       last_error,
        "retry_after": None,
    }


# ── Manual test ───────────────────────────────────────────────────────────────

def test_linkedin_post(vault_path: str | Path | None = None) -> None:
    """
    Interactive manual test.  Prints result to stdout.
    Run:  python helpers/linkedin_poster.py
    """
    print("\n=== LinkedIn Poster — Manual Test ===\n")

    content = input("Post content (leave blank for default test text):\n> ").strip()
    if not content:
        content = (
            "🤖 AI Employee test post — posted automatically via Playwright.\n"
            "Ignore this post. #AIEmployee #Hackathon"
        )

    image_input = input("\nImage path (leave blank to skip):\n> ").strip()
    image_path  = image_input if image_input else None

    print("\nPosting…\n")
    result = post_to_linkedin(
        content=content,
        image_path=image_path,
        vault_path=vault_path,
    )

    print("\n=== Result ===")
    for key, value in result.items():
        print(f"  {key:<15}: {value}")
    print()


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post to LinkedIn via Playwright")
    parser.add_argument("--content",  type=str, default="", help="Post text")
    parser.add_argument("--image",    type=str, default="", help="Optional image path")
    parser.add_argument(
        "--vault",
        type=str,
        default=str(DEFAULT_VAULT),
        help="Path to AI_Employee_Vault",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run interactive manual test instead",
    )
    args = parser.parse_args()

    if args.test or not args.content:
        test_linkedin_post(vault_path=args.vault)
    else:
        result = post_to_linkedin(
            content=args.content,
            image_path=args.image or None,
            vault_path=args.vault,
        )
        for key, value in result.items():
            print(f"{key}: {value}")
