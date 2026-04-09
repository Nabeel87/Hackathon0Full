import time
import logging
from abc import ABC, abstractmethod
from pathlib import Path


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


class BaseWatcher(ABC):
    """Abstract base class for all watchers."""

    def __init__(self, vault_path: str | Path, check_interval: int = 60):
        self.vault_path = Path(vault_path)
        self.check_interval = check_interval
        self.logger = _setup_logger(self.__class__.__name__)
        self._running = False

    @abstractmethod
    def check_for_updates(self) -> list[dict]:
        """Check the source for new items. Returns a list of item dicts."""
        ...

    @abstractmethod
    def create_action_file(self, item: dict) -> Path:
        """Write a vault action/task file for the given item. Returns the file path."""
        ...

    def run(self) -> None:
        """Main polling loop. Runs until CTRL+C or stop() is called."""
        self.logger.info(
            f"Starting {self.__class__.__name__} "
            f"(interval={self.check_interval}s, vault={self.vault_path})"
        )
        self._running = True

        try:
            while self._running:
                try:
                    items = self.check_for_updates()
                except Exception as e:
                    self.logger.error(f"check_for_updates failed: {e}")
                    items = []

                if items:
                    self.logger.info(f"{len(items)} new item(s) found.")
                else:
                    self.logger.info("No new items.")

                created = []
                for item in items:
                    try:
                        path = self.create_action_file(item)
                        created.append(path)
                        self.logger.info(f"Action file created: {path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create action file: {e}")

                if created:
                    try:
                        self.post_cycle(len(created))
                    except Exception as e:
                        self.logger.error(f"post_cycle failed: {e}")

                # Sleep in short ticks so stop() takes effect promptly
                self._interruptible_sleep(self.check_interval)

        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received — shutting down.")
        finally:
            self._running = False
            self.logger.info(f"{self.__class__.__name__} stopped.")

    def post_cycle(self, created_count: int) -> None:
        """
        Called after each poll cycle where new items were found.
        Override in subclasses to update the dashboard or run side effects.
        """

    def stop(self) -> None:
        """Signal the run loop to exit after the current sleep tick."""
        self._running = False
        self.logger.info("Stop signal received.")

    def _interruptible_sleep(self, seconds: int) -> None:
        """Sleep in 1-second ticks so stop() and CTRL+C respond within 1 second."""
        elapsed = 0
        while self._running and elapsed < seconds:
            time.sleep(1)
            elapsed += 1
        if self._running:
            self.logger.info(f"Next check in {self.check_interval}s...")
