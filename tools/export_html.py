"""Export seen_deals.json to a self-contained offline HTML report."""
import argparse
import html
import json
from datetime import datetime
from pathlib import Path


def load_deals(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for deal_id, v in data.items():
        items.append({
            "id": deal_id,
            "title": v.get("title", deal_id),
            "url": v.get("url", "#"),
            "provider": v.get("provider", "Unknown"),
            "score": v.get("score", 0),
            "confidence": v.get("confidence", "POTENTIAL"),
            "discovered_at": v.get("discovered_at", ""),
            "first_alerted_at": v.get("first_alerted_at", ""),
        })
    # Highest score first, then most recent
    items.sort(key=lambda d: (d["score"], d["first_alerted_at"]), reverse=True)
    return items


def render(deals, generated_at: str) -> str:
    cards = []
    for d in deals:
        score = int(d["score"] or 0)
        conf = html.escape(str(d["confidence"]))
        badge = "direct" if conf == "DIRECT_IDE" else "potential"
        cards.append(f"""
        <article class="card" data-conf="{badge}" data-provider="{html.escape(str(d['provider']).lower())}" data-title="{html.escape(str(d['title']).lower())}">
          <div class="top"><span class="score">{score}/100</span><span class="badge {badge}">{conf}</span><span class="provider">{html.escape(str(d['provider']))}</span></div>
          <h3><a href="{html.escape(str(d['url']))}" target="_blank" rel="noopener">{html.escape(str(d['title']))}</a></h3>
          <div class="meta"><a href="{html.escape(str(d['url']))}" target="_blank" rel="noopener">{html.escape(str(d['url']))[:90]}</a></div>
          <div class="dates">Alerted: {html.escape(str(d['first_alerted_at']))}</div>
        </article>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FreeTrialFinder Report — {{n}} deals</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0}}
header{{position:sticky;top:0;background:#0f172a;padding:16px 20px;border-bottom:1px solid #334155}}
h1{{margin:0 0 4px;font-size:20px}}p.sub{{margin:0;color:#94a3b8;font-size:13px}}
.controls{{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}}
input,select{{padding:8px 10px;border-radius:8px;border:1px solid #334155;background:#1e293b;color:#e2e8f0}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;padding:16px 20px 40px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:14px}}
.card h3{{margin:8px 0;font-size:15px;line-height:1.35}}.card a{{color:#7dd3fc;text-decoration:none}}.card a:hover{{text-decoration:underline}}
.top{{display:flex;gap:8px;align-items:center;font-size:12px}}.score{{background:#020617;padding:3px 8px;border-radius:99px;font-weight:700}}
.badge.direct{{background:#16a34a;padding:3px 8px;border-radius:99px;font-weight:700}}.badge.potential{{background:#d97706;padding:3px 8px;border-radius:99px;font-weight:700}}
.provider{{color:#c4b5fd}}.meta{{font-size:12px;color:#94a3b8;word-break:break-all}}.dates{{font-size:11px;color:#64748b;margin-top:6px}}
</style></head><body>
<header><h1>FreeTrialFinder Report — {len(deals)} deals</h1>
<p class="sub">Generated {html.escape(generated_at)} from seen_deals.json — sorted by score, then recency. Offline, no keys needed.</p>
<div class="controls"><input id="q" placeholder="Filter: openrouter, claude, $25..." size="36"/><select id="f"><option value="">All tiers</option><option value="direct">DIRECT_IDE only</option><option value="potential">POTENTIAL only</option></select></div>
</header><main>{"".join(cards)}</main>
<script>const q=document.getElementById('q'),f=document.getElementById('f'),cards=[...document.querySelectorAll('.card')];function run(){{const t=q.value.toLowerCase(),c=f.value;cards.forEach(el=>{{const okT=!t||el.dataset.title.includes(t)||el.dataset.provider.includes(t);const okC=!c||el.dataset.conf===c;el.style.display=okT&&okC?'':'none'}})}}q.oninput=run;f.onchange=run;</script>
</body></html>""".replace("{{n}}", str(len(deals)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Export seen deals JSON to offline HTML report.")
    ap.add_argument("--in", dest="inp", default="data/seen_deals.json", help="Input JSON path.")
    ap.add_argument("--out", dest="out", default="data/report.html", help="Output HTML path.")
    ap.add_argument("--limit", type=int, default=500, help="Max deals to include (default: 500).")
    args = ap.parse_args()
    deals = load_deals(Path(args.inp))[:args.limit]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(deals, datetime.now().astimezone().isoformat(timespec="seconds")), encoding="utf-8")
    print(f"Wrote {len(deals)} deals -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
