from abc import ABC, abstractmethod
from typing import List
from freetrialfinder.models import RawDeal

class BaseSource(ABC):
    """Abstract base class for all deal scrapers and collectors."""

    name: str = "base_source"

    @abstractmethod
    def fetch(self) -> List[RawDeal]:
        """Fetches raw candidate deals from the external source."""
        pass
