from abc import ABC, abstractmethod
from freetrialfinder.models import DealItem

class BaseNotifier(ABC):
    """Abstract base class for deal alert dispatchers."""

    @abstractmethod
    def send(self, deal: DealItem) -> bool:
        """Sends a notification for a newly discovered deal."""
        pass
