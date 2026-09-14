import sys
import argparse
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from freetrialfinder.config import settings
from freetrialfinder.models import DealItem, ConfidenceLevel, DealCategory
from freetrialfinder.engine import FinderEngine
from freetrialfinder.notifiers.telegram import TelegramNotifier
from freetrialfinder.notifiers.discord import DiscordNotifier
from freetrialfinder.notifiers.console import ConsoleNotifier

def build_notifiers(include_console: bool = True):
    notifiers = []
    if settings.enable_telegram and settings.telegram_bot_token and settings.telegram_chat_id:
        notifiers.append(TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id))
    if settings.enable_discord and settings.discord_webhook_url:
        notifiers.append(DiscordNotifier(settings.discord_webhook_url))
    if include_console and settings.enable_console:
        notifiers.append(ConsoleNotifier())
    return notifiers

def handle_poll(args) -> int:
    notifiers = build_notifiers(include_console=True)
    engine = FinderEngine(
        notifiers=notifiers,
        state_file=args.state_file,
        min_score=args.min_score,
    )
    new_deals = engine.run_cycle()
    console = Console()
    console.print(f"[bold green]Poll completed successfully![/] Found [cyan]{len(new_deals)}[/] new qualified deals.")
    return 0

def handle_inspect(args) -> int:
    engine = FinderEngine(
        notifiers=[],
        state_file=args.state_file,
        min_score=args.min_score,
    )
    deals = engine.inspect()
    console = Console()

    if not deals:
        console.print("[yellow]No qualified deals found matching the current criteria.[/]")
        return 0

    table = Table(title=f"Discovered AI Deals & Trials ({len(deals)} items)", show_lines=True)
    table.add_column("Score", style="bold cyan", width=8)
    table.add_column("Tier", style="bold", width=14)
    table.add_column("Provider", style="magenta", width=14)
    table.add_column("Category", style="blue", width=14)
    table.add_column("Promo Code", style="yellow", width=14)
    table.add_column("Title & Link", style="white")

    for deal in deals:
        tier_str = f"[green]{deal.confidence.value}[/]" if deal.confidence == ConfidenceLevel.DIRECT_IDE else f"[yellow]{deal.confidence.value}[/]"
        code_str = deal.promo_code if deal.promo_code else "-"
        table.add_row(
            f"{deal.score}/100",
            tier_str,
            deal.provider,
            deal.category.value,
            code_str,
            f"{deal.title}\n[dim]{deal.url}[/]",
        )

    console.print(table)
    return 0

def handle_test_notify(args) -> int:
    console = Console()
    notifiers = build_notifiers(include_console=False)
    if not notifiers:
        console.print("[red]No external notifiers configured![/] Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL in .env or environment.")
        return 1

    sample_deal = DealItem(
        id="test-notification-deal",
        title="Test Notification: Together AI $25 Free API Credits for Claude & Llama",
        url="https://together.ai",
        source="test_cli",
        provider="Together AI",
        category=DealCategory.API_CREDITS,
        confidence=ConfidenceLevel.DIRECT_IDE,
        score=95,
        reasons=["mentions_api", "mentions_credits", "test_alert"],
        promo_code="DEV25",
        estimated_value="$25",
        summary="This is a test notification verifying that your FreeTrialFinder alerts are working!",
    )

    for n in notifiers:
        success = n.send(sample_deal)
        n_name = n.__class__.__name__
        if success:
            console.print(f"[bold green][+] Successfully sent test alert via {n_name}![/]")
        else:
            console.print(f"[bold red][x] Failed to send test alert via {n_name}. Please verify credentials.[/]")
    return 0

def main(args: Optional[List[str]] = None) -> int:
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--state-file",
        default=settings.state_file,
        help="Path to persistent seen deals state file.",
    )
    parent_parser.add_argument(
        "--min-score",
        type=int,
        default=settings.min_score,
        help="Minimum developer usability score to alert on (default: 40).",
    )

    parser = argparse.ArgumentParser(
        prog="freetrialfinder",
        description="Modular, $0-cost AI free trial and credits monitor for IDE developers.",
        parents=[parent_parser],
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    poll_parser = subparsers.add_parser("poll", parents=[parent_parser], help="Poll all sources, score, deduplicate, and alert")
    poll_parser.set_defaults(func=handle_poll)

    inspect_parser = subparsers.add_parser("inspect", parents=[parent_parser], help="Dry-run: inspect current deals across sources without alerting")
    inspect_parser.set_defaults(func=handle_inspect)

    test_parser = subparsers.add_parser("test-notify", parents=[parent_parser], help="Send a test notification to configured Telegram/Discord channels")
    test_parser.set_defaults(func=handle_test_notify)

    parsed = parser.parse_args(args)
    if not parsed.command:
        parser.print_help()
        return 0

    return parsed.func(parsed)

if __name__ == "__main__":
    sys.exit(main())
