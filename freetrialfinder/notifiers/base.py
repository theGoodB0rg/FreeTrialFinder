from abc import ABC, abstractmethod
from typing import List
from freetrialfinder.models import DealItem


class BaseNotifier(ABC):
    """Abstract base class for deal alert dispatchers."""

    # False for local-only output (the console), which does not count as delivery.
    external: bool = True

    @abstractmethod
    def send(self, deal: DealItem) -> bool:
        """Send one alert for a deal that needs attention now."""

    @abstractmethod
    def send_digest(self, deals: List[DealItem], more: int = 0) -> bool:
        """Send one message summarising several deals; `more` were left out for length."""
