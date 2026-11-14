import sys
import argparse
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from freetrialfinder.config import settings
from freetrialfinder.models import DealItem, ConfidenceLevel, DealCategory, Route
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

def build_verifier(required: bool = False):
    """Return a DealVerifier when the agent is enabled and a key is set, else None."""
    api_key = settings.agent_api_key or settings.openrouter_api_key
    if not (api_key and (settings.enable_agent or required)):
        if required:
            Console().print("[red]Set AGENT_API_KEY (or OPENROUTER_API_KEY) in .env to use the agent.[/]")
        return None
    from freetrialfinder.agent import DealVerifier, JsonlTracer
    from freetrialfinder.agent.llm import OpenAICompatibleClient

    # An OpenRouter-only setup keeps working now that the default endpoint is Groq.
    base_url = settings.agent_base_url if settings.agent_api_key else "https://openrouter.ai/api/v1"
    llm = OpenAICompatibleClient(api_key=api_key, model=settings.agent_model, base_url=base_url)
    return DealVerifier(llm=llm, tracer=JsonlTracer(settings.agent_trace_file), profile=settings.load_profile())

def handle_poll(args) -> int:
    from collections import Counter

    console = Console()
    verifier = build_verifier()
    console.print(f"AI triage: [cyan]{'on (' + settings.agent_model + ')' if verifier else 'off (heuristic routing)'}[/]")
    engine = FinderEngine(
        notifiers=build_notifiers(include_console=True),
        state_file=args.state_file,
        min_score=args.min_score,
        verifier=verifier,
        agent_max_per_run=settings.agent_max_per_run,
    )
    routed = engine.run_cycle()
    counts = Counter(d.route.value for d in routed)
    console.print(f"[bold green]Poll complete.[/] Routed {len(routed)} new deals: "
                  f"now={counts['now']} digest={counts['digest']} drop={counts['drop']}")
    return 0

def handle_baseline(args) -> int:
    """Mark everything the sources list right now as seen, without sending or calling the AI.
    Run once after changing scoring or parsing so old items are not treated as new."""
    engine = FinderEngine(notifiers=[], state_file=args.state_file, min_score=args.min_score)
    if args.only:
        engine.sources = [src for src in engine.sources if getattr(src, "name", "") in args.only]
    new = engine.state_manager.filter_unseen(engine.evaluate_deals(engine.poll_all_sources()))
    for deal in new:
        deal.route = Route.DROP
        deal.reasons.append("baseline")
        engine.state_manager.record_deal(deal)
    Console().print(f"Baseline: marked [cyan]{len(new)}[/] current deals as seen.")
    return 0

def handle_digest(args) -> int:
    from datetime import timedelta

    engine = FinderEngine(sources=[], notifiers=build_notifiers(include_console=True), state_file=args.state_file)
    if args.if_due and not engine.digest_due(timedelta(hours=settings.digest_min_gap_hours)):
        Console().print("Digest: not due yet.")
        return 0
    sent = engine.send_digest(max_items=settings.digest_max_items)
    Console().print(f"[bold green]Digest:[/] {sent} deals sent." if sent else "Digest: nothing pending (or delivery failed).")
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
        url="https://www.together.ai/",
        source="test_cli",
        provider="Together AI",
        category=DealCategory.API_CREDITS,
        confidence=ConfidenceLevel.DIRECT_IDE,
        score=95,
        reasons=["mentions_api", "mentions_credits", "test_alert"],
        promo_code="DEV25",
        estimated_value="$25",
        summary="This is a test notification verifying that your FreeTrialFinder alerts are working!",
        route=Route.NOW,
        verified=True,
        headline="TEST · Together AI: $25 in free API credits",
        why="Covers a few weeks of Llama and DeepSeek calls from Cline or Aider at no cost.",
        action="Sign up, open Billing and redeem the code. Then set `OPENAI_BASE_URL=https://api.together.xyz/v1` in your coding agent.",
        expires="30 Nov 2026",
    )

    for n in notifiers:
        success = n.send_digest([sample_deal]) if args.digest else n.send(sample_deal)
        n_name = n.__class__.__name__
        if success:
            console.print(f"[bold green][+] Successfully sent test alert via {n_name}![/]")
        else:
            console.print(f"[bold red][x] Failed to send test alert via {n_name}. Please verify credentials.[/]")
    return 0

def handle_eval(args) -> int:
    import json
    from freetrialfinder.agent.evaluate import load_labelled, run_eval

    verifier = build_verifier(required=True)
    if verifier is None:
        return 1
    console = Console()
    rows = load_labelled(args.labels)
    console.print(f"Evaluating agent on [cyan]{len(rows)}[/] labelled deals with model [magenta]{settings.agent_model}[/]...")
    report = run_eval(verifier, rows)

    table = Table(title="Per-deal results", show_lines=False)
    for col in ("Label", "Agent", "Tools", "Flags", "Title"):
        table.add_column(col)
    for r in report["results"]:
        ok = r["decision"] == r["label"]
        style = "green" if ok else ("yellow" if r["decision"] == "unsure" else "red")
        table.add_row(r["label"], f"[{style}]{r['decision']}[/]", str(r["tool_calls"]), ",".join(r["flags"]) or "-", r["title"][:60])
    console.print(table)
    console.print_json(json.dumps(report["metrics"]))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        console.print(f"Saved report to [cyan]{args.out}[/]")
    return 0

def handle_traces(args) -> int:
    import json
    from collections import Counter

    console = Console()
    try:
        with open(settings.agent_trace_file, encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        console.print("[yellow]No traces yet.[/]")
        return 0
    verdicts = [e for e in events if e["kind"] == "verdict"]
    guards = Counter(e["rule"] for e in events if e["kind"] == "guard")
    flags = Counter(f for v in verdicts for f in v.get("flags", []))
    console.print(f"Runs: [cyan]{len(verdicts)}[/]  Decisions: {dict(Counter(v['decision'] for v in verdicts))}")
    console.print(f"Guard trips: {dict(guards) or '-'}  Flags: {dict(flags) or '-'}")
    for v in verdicts[-args.last:]:
        console.print(f"[dim]{v['ts']} {v['run_id']}[/] [bold]{v['decision']}[/] tools={v['tool_calls']} :: {v['reason'][:120]}")
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
    test_parser.add_argument("--digest", action="store_true", help="Preview the digest format instead of a single alert")
    test_parser.set_defaults(func=handle_test_notify)

    digest_parser = subparsers.add_parser("digest", parents=[parent_parser], help="Send the daily digest of pending deals")
    digest_parser.add_argument("--if-due", action="store_true", help="Only send if the last digest is older than DIGEST_MIN_GAP_HOURS")
    digest_parser.set_defaults(func=handle_digest)

    baseline_parser = subparsers.add_parser("baseline", parents=[parent_parser], help="Mark all current deals as seen without alerting")
    baseline_parser.add_argument("--only", nargs="*", help="Limit to these source names (e.g. github_curated)")
    baseline_parser.set_defaults(func=handle_baseline)

    eval_parser = subparsers.add_parser("eval", parents=[parent_parser], help="Score the verification agent against hand-labelled deals")
    eval_parser.add_argument("--labels", default="evals/labelled_deals.jsonl", help="Path to labelled JSONL file")
    eval_parser.add_argument("--out", default="evals/last_report.json", help="Where to save the full report")
    eval_parser.set_defaults(func=handle_eval)

    traces_parser = subparsers.add_parser("traces", parents=[parent_parser], help="Summarise recorded agent traces")
    traces_parser.add_argument("--last", type=int, default=10, help="How many recent verdicts to show")
    traces_parser.set_defaults(func=handle_traces)

    parsed = parser.parse_args(args)
    if not parsed.command:
        parser.print_help()
        return 0

    return parsed.func(parsed)

if __name__ == "__main__":
    sys.exit(main())
