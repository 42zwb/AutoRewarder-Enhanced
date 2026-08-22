"""Microsoft Rewards mobile-only activity automation.

The package deliberately keeps OAuth, HTTP transport, task policy, and
per-account state separate.  A scheduled run can therefore fail closed when
the mobile app API is unavailable without affecting browser search tasks.
"""

from .models import (
    MobileTaskResult,
    MobileTaskSummary,
    RESULT_STATUSES,
)
from .runner import MobileTaskRunner
from .tasks import DailyCheckInTask, ReadToEarnTask

__all__ = [
    "MobileTaskResult",
    "MobileTaskSummary",
    "MobileTaskRunner",
    "DailyCheckInTask",
    "ReadToEarnTask",
    "RESULT_STATUSES",
]
