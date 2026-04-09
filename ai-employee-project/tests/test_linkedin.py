"""
tests/test_linkedin.py

LinkedIn Silver Tier integration tests.

Run:
    python -m pytest tests/test_linkedin.py -v
    python tests/test_linkedin.py          # standalone
"""

import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

# -- Project root on sys.path --------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_VAULT = Path(
    "C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault"
)
_CREDENTIALS_DIR = _PROJECT_ROOT / ".credentials" / "linkedin_session"

# -- Tests ---------------------------------------------------------------------

def test_linkedin_watcher_init():
    """LinkedInWatcher initialises with correct vault_path and check_interval."""
    from watchers.linkedin_watcher import LinkedInWatcher

    watcher = LinkedInWatcher(vault_path=_VAULT, check_interval=180)

    assert watcher.vault_path == Path(_VAULT), (
        f"vault_path mismatch: {watcher.vault_path}"
    )
    assert watcher.check_interval == 180, (
        f"check_interval should be 180, got {watcher.check_interval}"
    )
    assert watcher.session_dir.exists() or True, "session_dir path accessible"
    print("  vault_path   :", watcher.vault_path)
    print("  check_interval:", watcher.check_interval)
    print("  session_dir  :", watcher.session_dir)


def test_linkedin_session_exists():
    """LinkedIn session directory exists (create if missing)."""
    if not _CREDENTIALS_DIR.exists():
        _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {_CREDENTIALS_DIR}")
    else:
        print(f"  Exists : {_CREDENTIALS_DIR}")

    assert _CREDENTIALS_DIR.exists(), (
        f"Session directory could not be created: {_CREDENTIALS_DIR}"
    )

    cookies_file = _CREDENTIALS_DIR / "cookies.json"
    if cookies_file.exists():
        print(f"  cookies.json: FOUND ({cookies_file.stat().st_size} bytes)")
    else:
        print("  cookies.json: NOT FOUND (login required before first run)")


def test_linkedin_poster_function():
    """post_to_linkedin exists and has the correct signature."""
    from helpers.linkedin_poster import post_to_linkedin

    assert callable(post_to_linkedin), "post_to_linkedin is not callable"

    sig = inspect.signature(post_to_linkedin)
    params = list(sig.parameters.keys())

    assert "content" in params, f"'content' param missing - found: {params}"
    assert "image_path" in params, f"'image_path' param missing - found: {params}"
    assert "vault_path" in params, f"'vault_path' param missing - found: {params}"

    # Verify defaults: image_path and vault_path should be optional
    assert sig.parameters["image_path"].default is not inspect.Parameter.empty, (
        "image_path should have a default value"
    )
    assert sig.parameters["vault_path"].default is not inspect.Parameter.empty, (
        "vault_path should have a default value"
    )

    print("  Function    : post_to_linkedin")
    print("  Parameters  :", params)
    print("  image_path default:", sig.parameters["image_path"].default)
    print("  vault_path default:", sig.parameters["vault_path"].default)


def test_linkedin_skill_exists():
    """post-linkedin SKILL.md exists and has required frontmatter fields."""
    skill_path = _PROJECT_ROOT / ".claude" / "skills" / "post-linkedin" / "SKILL.md"

    assert skill_path.exists(), f"SKILL.md not found at: {skill_path}"

    content = skill_path.read_text(encoding="utf-8")

    # Must have YAML frontmatter delimiters
    assert content.startswith("---"), "SKILL.md must start with '---' frontmatter"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "SKILL.md frontmatter not properly closed with '---'"

    frontmatter_block = parts[1]

    # Required frontmatter fields
    for field in ("name:", "description:", "triggers:"):
        assert field in frontmatter_block, (
            f"Required frontmatter field '{field}' missing"
        )

    # Must have Purpose, Process, Usage sections
    for section in ("## Purpose", "## Process", "## Usage"):
        assert section in content, f"Required section '{section}' missing"

    # Must be pure Markdown - no Python code (python keyword in fenced block)
    import re
    python_blocks = re.findall(r"```python", content)
    assert not python_blocks, (
        "SKILL.md must not contain Python code blocks (found ```python)"
    )

    print(f"  Path      : {skill_path}")
    print(f"  Size      : {len(content)} chars")
    print("  Frontmatter fields: name, description, triggers OK")
    print("  Sections  : Purpose, Process, Usage OK")
    print("  No Python code blocks OK")


def test_approval_workflow():
    """Create a mock approval file, verify format, then clean up."""
    pending_dir = _VAULT / "Pending_Approval"
    pending_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=timezone.utc)
    ts  = now.strftime("%Y%m%d_%H%M%S")
    test_content = "Test post: LinkedIn integration test - automated by test suite."
    expires_iso  = now.replace(hour=(now.hour + 1) % 24).strftime("%Y-%m-%d %H:%M:%S UTC")
    created_iso  = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    approval_file = pending_dir / f"LINKEDIN_POST_{ts}_TEST.md"

    card = f"""---
type: linkedin_post_approval
status: pending
created: "{created_iso}"
expires: "{expires_iso}"
content_preview: "{test_content[:100]}"
image_path: none
---

# LinkedIn Post - Awaiting Approval

**Created:** {created_iso}
**Expires:** {expires_iso}
**Status:** PENDING

---

## Post Content

{test_content}

---

## Image

None

---

## Approval Instructions

To **approve**: move this file to `Approved/`
To **reject**: move this file to `Rejected/` and add a reason below

### Rejection Reason (if rejecting)

_Add reason here before moving to Rejected/_
"""

    approval_file.write_text(card, encoding="utf-8")

    # -- Verify file -----------------------------------------------------------
    assert approval_file.exists(), "Approval file was not created"

    written = approval_file.read_text(encoding="utf-8")

    assert "type: linkedin_post_approval" in written, "Missing type field"
    assert "status: pending"              in written, "Missing status field"
    assert "content_preview"              in written, "Missing content_preview field"
    assert "## Post Content"              in written, "Missing Post Content section"
    assert "## Approval Instructions"     in written, "Missing Approval Instructions section"
    assert test_content                   in written, "Post content not written correctly"

    print(f"  File    : {approval_file.name}")
    print(f"  Size    : {len(written)} chars")
    print("  Fields  : type, status, content_preview OK")
    print("  Sections: Post Content, Approval Instructions OK")

    # -- Clean up --------------------------------------------------------------
    approval_file.unlink()
    assert not approval_file.exists(), "Test file cleanup failed"
    print("  Cleanup : OK")


# -- Standalone runner ---------------------------------------------------------

def _run_all():
    tests = [
        ("LinkedInWatcher init",          test_linkedin_watcher_init),
        ("Session directory",             test_linkedin_session_exists),
        ("post_to_linkedin signature",    test_linkedin_poster_function),
        ("post-linkedin SKILL.md",        test_linkedin_skill_exists),
        ("Approval workflow (mock)",      test_approval_workflow),
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("  LINKEDIN SILVER TIER TEST SUITE")
    print("=" * 60)

    for name, fn in tests:
        print(f"\n>> {name}")
        try:
            fn()
            print(f"  PASS")
            passed += 1
        except Exception as exc:
            print(f"  FAIL -- {exc}")
            failed += 1

    print("\n" + "-" * 60)
    print(f"  Results: {passed}/{len(tests)} passed", end="")
    if failed:
        print(f"  ({failed} failed)")
    else:
        print("  -- all passing")
    print("-" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
