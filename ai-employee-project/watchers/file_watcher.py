import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from watchers.base_watcher import BaseWatcher
from helpers.dashboard_updater import update_activity, update_component_status, update_stats

# ── Security blacklist ────────────────────────────────────────────────────────

BLACKLIST_PATTERNS = [
    r"\.ssh",
    r"\.config",
    r"\.env",
    r"credentials",
    r"passwords?",
    r"secret",
    r"private[_\-]?key",
    r"id_rsa",
    r"\.pem",
    r"\.p12",
    r"\.pfx",
]

_BLACKLIST_RE = re.compile("|".join(BLACKLIST_PATTERNS), re.IGNORECASE)


def _is_safe(path: Path) -> bool:
    """Return False if the file should be skipped for privacy/security reasons."""
    name = path.name
    if name.startswith("."):           # hidden files
        return False
    if name.startswith("~"):           # temp/lock files
        return False
    if name.endswith(".tmp") or name.endswith(".part"):
        return False
    if _BLACKLIST_RE.search(str(path)):  # blacklisted path patterns
        return False
    return True


# ── FileWatcher ───────────────────────────────────────────────────────────────

class FileWatcher(BaseWatcher):
    """
    Scans a directory for new files and creates vault action cards.

    check_for_updates() lists the directory directly — no watchdog, no threads.
    Already-logged files are tracked in self._seen_paths so repeated calls
    within the same session don't produce duplicate cards.
    """

    def __init__(
        self,
        vault_path: str | Path,
        watch_dir: str | Path | None = None,
        check_interval: int = 60,
    ):
        super().__init__(vault_path, check_interval)
        self.watch_dir = Path(watch_dir) if watch_dir else Path("C:/Users/GEO COMPUTERS/Downloads/vaultFull")
        self._seen_paths: set[Path] = set()

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list[dict]:
        """List watch_dir, filter safe files, return new ones as metadata dicts."""
        if not self.watch_dir.exists():
            self.logger.warning(f"Watch directory not found: {self.watch_dir}")
            return []

        items = []
        for path in sorted(self.watch_dir.iterdir()):
            if not path.is_file():
                continue
            if not _is_safe(path):
                continue
            if path in self._seen_paths:
                continue
            if _already_logged(path, self.vault_path):
                self._seen_paths.add(path)
                continue

            try:
                stat = path.stat()
            except OSError as e:
                self.logger.warning(f"Could not stat {path.name}: {e}")
                continue

            self._seen_paths.add(path)
            items.append({
                "path": path,
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "detected_at": datetime.now(tz=timezone.utc),
            })

        return items

    def post_cycle(self, created_count: int) -> None:
        """Update dashboard after new files are detected."""
        try:
            from helpers.dashboard_updater import refresh_vault_counts
            update_activity(self.vault_path, f"File Monitor: {created_count} new file(s) detected")
            update_component_status(self.vault_path, "File Monitor", "online")
            update_stats(self.vault_path, "files_monitored", created_count, operation="increment")
            refresh_vault_counts(self.vault_path)
        except Exception as e:
            self.logger.warning(f"Dashboard update failed: {e}")

    def create_action_file(self, item: dict) -> Path:
        """Write a FILE_*.md card to vault Inbox/ and return its path."""
        vault_inbox = self.vault_path / "Inbox"
        vault_inbox.mkdir(parents=True, exist_ok=True)

        dt: datetime = item["detected_at"]
        ts_slug = dt.strftime("%Y%m%d_%H%M%S")
        name_slug = _safe_slug(item["name"])
        card_path = vault_inbox / f"FILE_{ts_slug}_{name_slug}.md"

        size_kb = item["size_bytes"] / 1024
        detected_iso = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        # Use forward slashes so Windows paths are safe in YAML
        file_path_safe = item["path"].as_posix()
        file_type = item["suffix"] or "unknown"
        priority = _infer_priority(item["name"], item["suffix"])
        actions = _suggested_actions(item["suffix"])

        card_path.write_text(
            f"""---
type: file
file_name: "{item['name']}"
file_path: "{file_path_safe}"
file_size: "{size_kb:.1f} KB"
file_type: "{file_type}"
detected_at: "{detected_iso}"
priority: {priority}
status: pending
---

# New File: {item['name']}

**Path:** `{item['path']}`
**Size:** {size_kb:.1f} KB
**Type:** {file_type}
**Detected:** {detected_iso}
**Priority:** {priority}

---

## Suggested Actions

{actions}

---

## Notes

_Add context here as you process this file._
""",
            encoding="utf-8",
        )
        return card_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _already_logged(path: Path, vault_path: Path) -> bool:
    """Return True if a vault card referencing this filename exists in any vault folder."""
    slug = _safe_slug(path.name)
    for folder in ("Inbox", "Needs_Action", "Done"):
        d = vault_path / folder
        if d.exists() and any(slug in f.name for f in d.iterdir() if f.suffix == ".md"):
            return True
    return False


def _safe_slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip()
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug[:max_len]


def _infer_priority(name: str, suffix: str) -> str:
    if suffix in {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip", ".exe", ".dmg"}:
        return "high"
    if re.search(r"urgent|invoice|contract|payment|asap", name, re.IGNORECASE):
        return "high"
    return "normal"


def _suggested_actions(suffix: str) -> str:
    actions = {
        ".pdf": (
            "- [ ] Open and review PDF contents\n"
            "- [ ] Check sender/source legitimacy\n"
            "- [ ] File in appropriate project folder\n"
            "- [ ] Extract key data if needed"
        ),
        ".docx": (
            "- [ ] Review document contents\n"
            "- [ ] Check for tracked changes or comments\n"
            "- [ ] Save to project folder"
        ),
        ".xlsx": (
            "- [ ] Open spreadsheet and review data\n"
            "- [ ] Validate formulas and values\n"
            "- [ ] Archive or import as needed"
        ),
        ".zip": (
            "- [ ] Scan archive before extracting\n"
            "- [ ] Extract to a sandboxed folder\n"
            "- [ ] Review contents"
        ),
        ".exe": (
            "- [ ] **Do not run without verifying source**\n"
            "- [ ] Scan with antivirus\n"
            "- [ ] Confirm legitimacy before executing"
        ),
    }
    return actions.get(suffix, (
        "- [ ] Review the file\n"
        "- [ ] Determine if action is needed\n"
        "- [ ] Archive or delete when resolved"
    ))


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    vault = Path("C:/Users/GEO COMPUTERS/Desktop/Hackathon/Hackathon0Full/AI_Employee_Vault")
    watch = Path("C:/Users/GEO COMPUTERS/Downloads/vaultFull")

    if len(sys.argv) > 1:
        watch = Path(sys.argv[1])
    if len(sys.argv) > 2:
        vault = Path(sys.argv[2])

    watcher = FileWatcher(vault_path=vault, watch_dir=watch)
    watcher.run()
