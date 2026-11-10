"""Local read-only HTML. No fake metrics. Live panel requires observed-live snapshot."""

from __future__ import annotations

import html
import json
from pathlib import Path


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{100.0 * float(value):.1f}%"


def _num(value, digits=2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _bar(acc: float | None) -> str:
    if acc is None:
        return ""
    width = max(0.0, min(100.0, 100.0 * acc))
    return f'<div class="bar"><span style="width:{width:.1f}%"></span></div>'


def render_html(metrics: dict | None, predictions: list[dict] | None = None) -> str:
    if not metrics:
        return """<!doctype html><html><head><meta charset="utf-8"><title>KXBTC15M V3</title>
<style>body{font-family:Georgia,serif;max-width:960px;margin:2rem auto;padding:0 1rem;background:#111;color:#eee}
.banner{border:1px solid #555;padding:1rem}</style></head><body>
<div class="banner"><strong>not trained</strong> / no evaluation yet. No accuracy is shown.</div>
<p>Phase 1 is offline historical replay. This is not a live stream.</p>
</body></html>
"""
    hold = metrics.get("holdout") or {}
    a = hold.get("A_logistic") or {}
    aspiration = metrics.get("aspiration") or {"low": 0.8, "high": 0.9}
    live_rows = [r for r in (predictions or []) if r.get("availability") == "observed_live" and not r.get("skip_reason")]
    if live_rows:
        latest = live_rows[-1]
        live_panel = f"""
        <div class="panel live">
          <h2>Current market (observed live)</h2>
          <p>Start S<sub>t</sub> {_num(latest.get('S_t'))} · Predicted end {_num(latest.get('forecast_end'))} · Predicted {html.escape(str(latest.get('pred_yes')))}</p>
        </div>"""
    else:
        live_panel = """
        <div class="panel live">
          <h2>Current market (observed live)</h2>
          <p><strong>unavailable</strong> — no observed-live snapshot with observation_at ≤ t*. Replay numbers below are not live.</p>
        </div>"""

    latest_replay = None
    for r in reversed(predictions or []):
        if r.get("availability") == "historical_replay" and r.get("pred_yes") in {"yes", "no"}:
            latest_replay = r
            break
    replay_card = ""
    if latest_replay:
        replay_card = f"""
        <div class="panel replay">
          <h2>Latest scored window (historical replay — not live)</h2>
          <p>{html.escape(str(latest_replay.get('ticker')))}</p>
          <p>Start S<sub>t</sub> <strong>{_num(latest_replay.get('S_t'))}</strong>
             · Predicted end <strong>{_num(latest_replay.get('forecast_end'))}</strong>
             · Predicted <strong>{html.escape(str(latest_replay.get('pred_yes')).upper())}</strong>
             · Actual {html.escape(str(latest_replay.get('result') or '—').upper())}</p>
        </div>"""

    rows_html = []
    for key, title in (
        ("A_logistic", "A logistic (headline)"),
        ("A_ret", "A-ret Ridge side"),
        ("B_knn", "B purged kNN k=25"),
        ("C_majority", "C majority"),
        ("C_last10", "C last-10"),
        ("C_nochange", "C no-change"),
        ("C_lastprice", "C last-price"),
    ):
        m = hold.get(key) or {}
        rows_html.append(
            f"<tr><td>{html.escape(title)}</td><td>{_pct(m.get('accuracy'))}</td>"
            f"<td>{_pct(m.get('wilson_lo'))}–{_pct(m.get('wilson_hi'))}</td>"
            f"<td>{_pct(m.get('coverage'))}</td><td>{_num(m.get('mae'), 2)}</td>"
            f"<td>{m.get('n_scored')}</td></tr>"
        )

    table_rows = []
    for r in (predictions or []):
        if r.get("split") != "holdout":
            continue
        ok = "yes" if r.get("pred_yes") == r.get("result") else "no"
        if r.get("skip_reason"):
            ok = "skip"
        err = ""
        if r.get("forecast_end") is not None and r.get("expiration_value") is not None:
            err = _num(abs(float(r["forecast_end"]) - float(r["expiration_value"])))
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(str(r.get('ticker')))}</td>"
            f"<td>{html.escape(str(r.get('prediction_asof')))}</td>"
            f"<td>{html.escape(str(r.get('pred_yes')))}</td>"
            f"<td>{html.escape(str(r.get('result')))}</td>"
            f"<td>{ok}</td><td>{err}</td>"
            f"<td>{html.escape(str(r.get('availability')))}</td>"
            "</tr>"
        )
        if len(table_rows) >= 200:
            break

    acc = a.get("accuracy")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>KXBTC15M V3 replay</title>
<style>
body{{font-family:ui-sans-serif,system-ui,sans-serif;margin:0;background:#0f1419;color:#e8eef4}}
main{{max-width:1100px;margin:0 auto;padding:1.5rem}}
.banner{{background:#1c2833;border-left:4px solid #c9a227;padding:1rem 1.2rem;margin-bottom:1rem}}
.panel{{background:#17202a;padding:1rem 1.2rem;margin:1rem 0;border-radius:8px}}
.live{{border:1px dashed #7f8c8d}}
.replay{{border:1px solid #2471a3}}
table{{width:100%;border-collapse:collapse;font-size:0.92rem}}
th,td{{text-align:left;padding:0.4rem 0.5rem;border-bottom:1px solid #2c3e50}}
.bar{{background:#2c3e50;height:8px;border-radius:4px;margin-top:0.4rem}}
.bar span{{display:block;height:8px;background:#27ae60}}
.refs{{display:flex;gap:1rem;margin:0.6rem 0 0}}
.ref{{flex:1;background:#1a252f;padding:0.5rem;border-radius:4px;font-size:0.85rem}}
</style></head><body><main>
<div class="banner">
  <strong>historical_replay</strong> · assumption {html.escape(str(metrics.get('replay_assumption')))}.
  This score uses publication-proxy timestamps, not live-arrival proof.
  <div>prediction_asof (t*) is per row · dataset_asof {html.escape(str(metrics.get('dataset_asof')))} · run_generated_at {html.escape(str(metrics.get('run_generated_at')))}</div>
  <div>model {html.escape(str(metrics.get('model_version')))} · p_yes {html.escape(str(metrics.get('calibration')))} · 80–90% line is aspiration, not a pass.</div>
</div>
{live_panel}
{replay_card}
<div class="panel">
  <h2>Replay holdout — A logistic</h2>
  <p>Accuracy <strong>{_pct(acc)}</strong> (Wilson {_pct(a.get('wilson_lo'))}–{_pct(a.get('wilson_hi'))})
     · coverage {_pct(a.get('coverage'))} · n {a.get('n_scored')} · MAE {_num(a.get('mae'))}</p>
  {_bar(acc)}
  <div class="refs"><div class="ref">50% chance</div><div class="ref">aspiration 80%</div><div class="ref">aspiration 90%</div></div>
</div>
<div class="panel">
  <h2>Models and controls (same holdout rows)</h2>
  <table><thead><tr><th>Model</th><th>Accuracy</th><th>Wilson 95%</th><th>Coverage</th><th>End-price MAE</th><th>n</th></tr></thead>
  <tbody>{''.join(rows_html)}</tbody></table>
  <p>Train {metrics.get('n_train')} · validation {metrics.get('n_validation')} · holdout {metrics.get('n_holdout')} · skipped {metrics.get('n_skipped')} · universe {metrics.get('n_inventory_scored_universe')}</p>
</div>
<div class="panel">
  <h2>Holdout markets (first 200)</h2>
  <table><thead><tr><th>ticker</th><th>prediction_asof</th><th>pred</th><th>actual</th><th>correct</th><th>|error|</th><th>availability</th></tr></thead>
  <tbody>{''.join(table_rows) if table_rows else '<tr><td colspan="7">no holdout rows</td></tr>'}</tbody></table>
</div>
<p style="color:#7f8c8d">Read-only. Public GET only. Not a trading profit backtest. Old paper ledgers were not written.</p>
</main></body></html>
"""


def write_screen(state_dir: Path) -> Path:
    metrics_path = state_dir / "metrics.json"
    pred_path = state_dir / "predictions.csv"
    metrics = None
    predictions = []
    if metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if pred_path.is_file():
        import csv
        with pred_path.open(encoding="utf-8") as fh:
            predictions = list(csv.DictReader(fh))
            for r in predictions:
                for key in ("S_t", "R_t", "forecast_end", "expiration_value", "p_yes"):
                    if r.get(key) in ("", None):
                        r[key] = None
                    else:
                        try:
                            r[key] = float(r[key])
                        except ValueError:
                            pass
    html_text = render_html(metrics, predictions)
    out = state_dir / "results.html"
    out.write_text(html_text, encoding="utf-8")
    return out
