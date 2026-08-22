"""Data models shared by the mobile task client and the API/GUI."""

from dataclasses import asdict, dataclass
from datetime import datetime

RESULT_STATUSES = (
    "completed",
    "already_done",
    "partial",
    "unavailable",
    "auth_required",
    "failed",
    "stopped",
)


def _status(value, fallback="failed"):
    return value if value in RESULT_STATUSES else fallback


@dataclass
class MobileTaskResult:
    """Result for one independently retryable mobile activity."""

    name: str
    status: str = "failed"
    points: int = 0
    articles: int = 0
    reason: str = ""

    def __post_init__(self):
        self.status = _status(self.status)
        self.points = max(0, int(self.points or 0))
        self.articles = max(0, int(self.articles or 0))

    @property
    def successful(self):
        return self.status in ("completed", "already_done")

    def to_dict(self):
        return asdict(self)


@dataclass
class MobileTaskSummary:
    """Serializable summary returned by ``MobileTaskRunner.run``."""

    status: str = "failed"
    check_in_status: str = "stopped"
    read_status: str = "stopped"
    check_in_points: int = 0
    read_points: int = 0
    read_articles: int = 0
    target_points: int = 30
    target_articles: int = 10
    reason: str = ""
    last_attempt_at: str = ""

    def __post_init__(self):
        self.status = _status(self.status)
        self.check_in_status = _status(self.check_in_status, "stopped")
        self.read_status = _status(self.read_status, "stopped")
        self.check_in_points = max(0, int(self.check_in_points or 0))
        self.read_points = max(0, int(self.read_points or 0))
        self.read_articles = max(0, int(self.read_articles or 0))
        self.target_points = max(0, int(self.target_points or 0))
        self.target_articles = max(0, int(self.target_articles or 0))
        if not self.last_attempt_at:
            self.last_attempt_at = datetime.now().isoformat(timespec="seconds")

    @property
    def successful(self):
        return self.status in ("completed", "already_done")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_status(cls, data):
        """Build a summary from a persisted status object defensively."""
        data = data if isinstance(data, dict) else {}
        check = data.get("check_in") if isinstance(data.get("check_in"), dict) else {}
        read = (
            data.get("read_to_earn")
            if isinstance(data.get("read_to_earn"), dict)
            else {}
        )
        return cls(
            status=data.get("result", "failed"),
            check_in_status=check.get("status", data.get("check_in_status", "stopped")),
            read_status=read.get("status", data.get("read_status", "stopped")),
            check_in_points=check.get("points", data.get("check_in_points", 0)),
            read_points=read.get("points", data.get("read_points", 0)),
            read_articles=read.get("articles", data.get("read_articles", 0)),
            target_points=read.get("target_points", data.get("target_points", 30)),
            target_articles=read.get("target_articles", data.get("target_articles", 10)),
            reason=data.get("reason", ""),
            last_attempt_at=data.get("last_attempt_at", ""),
        )
