from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from freetrialfinder.models import DealItem, ConfidenceLevel
from freetrialfinder.notifiers.base import BaseNotifier

class ConsoleNotifier(BaseNotifier):
    """Prints formatted deal alerts to the terminal using Rich."""

    def __init__(self):
        self.console = Console()

    def send(self, deal: DealItem) -> bool:
        tier_color = "green" if deal.confidence == ConfidenceLevel.DIRECT_IDE else "yellow"
        
        info = (
            f"[bold {tier_color}]Status:[/] {deal.confidence.value} ({deal.score}/100)\n"
            f"[bold cyan]Provider:[/] {deal.provider} | [bold cyan]Category:[/] {deal.category.value}\n"
            f"[bold cyan]URL:[/] {deal.url}\n"
        )
        if deal.promo_code:
            info += f"[bold magenta]Promo Code:[/] {deal.promo_code}\n"
        if deal.estimated_value:
            info += f"[bold green]Value:[/] {deal.estimated_value}\n"
        if deal.reasons:
            info += f"[dim]Signals: {', '.join(deal.reasons[:4])}[/]\n"
        info += f"\n[white]{deal.summary[:200]}[/]"

        self.console.print(Panel(info, title=f"[{tier_color}]{deal.title}[/]", border_style=tier_color))
        return True
