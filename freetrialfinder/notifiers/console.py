from typing import List

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from freetrialfinder.models import DealItem
from freetrialfinder.notifiers.base import BaseNotifier


class ConsoleNotifier(BaseNotifier):
    """Prints alerts to the terminal (and the Actions log). Not a delivery channel."""

    external = False

    def __init__(self):
        self.console = Console()

    def send(self, deal: DealItem) -> bool:
        color = "green" if deal.verified else "yellow"
        lines = [f"[bold]{escape(deal.why or deal.summary[:200])}[/]"]
        if deal.promo_code:
            lines.append(f"[bold magenta]Code:[/] {escape(deal.promo_code)}")
        if deal.estimated_value:
            lines.append(f"[bold green]Value:[/] {escape(deal.estimated_value)}")
        if deal.expires:
            lines.append(f"[bold]Expires:[/] {escape(deal.expires)}")
        if deal.action:
            lines.append(f"[bold cyan]How to claim:[/] {escape(deal.action)}")
        lines.append(f"[dim]{escape(deal.url)} · {escape(deal.provider)} · {deal.score}/100 · {deal.route.value if deal.route else '-'}[/]")
        self.console.print(Panel("\n".join(lines), title=f"[{color}]{escape(deal.display_title)}[/]", border_style=color))
        return True

    def send_digest(self, deals: List[DealItem], more: int = 0) -> bool:
        self.console.print(f"[bold]Daily digest[/] · {len(deals) + more} offers")
        for deal in deals:
            code = f" [magenta]{escape(deal.promo_code)}[/]" if deal.promo_code else ""
            tag = "" if deal.verified else " [dim](unverified)[/]"
            self.console.print(f"• {escape(deal.display_title)}{code}{tag}\n  [dim]{escape(deal.url)}[/]")
        if more:
            self.console.print(f"[dim]+{more} more not shown[/]")
        return True
