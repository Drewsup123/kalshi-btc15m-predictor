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
    preview = (metrics.get("preview") or {}).get("next") or (metrics.get("preview") or {}).get("current")
    nxt = (metrics.get("preview") or {}).get("next")
    if nxt and nxt.get("ticker"):
        preview_card = f"""
        <div class="panel preview">
          <h2>Next market preview</h2>
          <p><strong>{html.escape(str(nxt.get('label') or 'PREVIEW / pre-open'))}</strong>
             · {html.escape(str(nxt.get('ticker')))}</p>
          <p>Open {html.escape(str(nxt.get('open_denver') or nxt.get('open_time')))} · Close {html.escape(str(nxt.get('close_denver') or nxt.get('close_time')))} America/Denver</p>
          <p>Estimated start <strong>{_num(nxt.get('S_t'))}</strong> ({html.escape(str(nxt.get('S_t_source') or 'latest print'))})
             · Predicted end <strong>{_num(nxt.get('forecast_end'))}</strong>
             · Predicted <strong>{html.escape(str(nxt.get('pred_yes') or '—').upper())}</strong>
             · p_yes {_num(nxt.get('p_yes'), 3)} uncalibrated</p>
          <p>Pre-open backtest { _pct((metrics.get('preopen_backtest') or {}).get('accuracy')) }
             (Wilson {_pct((metrics.get('preopen_backtest') or {}).get('wilson_lo'))}–{_pct((metrics.get('preopen_backtest') or {}).get('wilson_hi'))})
             · coverage {_pct((metrics.get('preopen_backtest') or {}).get('coverage'))}
             · n {(metrics.get('preopen_backtest') or {}).get('n_scored')}</p>
        </div>"""
    else:
        preview_card = """
        <div class="panel preview">
          <h2>Next market preview</h2>
          <p><strong>PREVIEW / pre-open unavailable</strong> — run <code>v3-preview</code> (public GET, no scheduler).</p>
        </div>"""
    sweep = metrics.get("sweep") or {}
    hold_label = html.escape(str(sweep.get("holdout_label") or ""))
    n_var = sweep.get("n_variants_tried")
    sweep_banner = ""
    if sweep:
        sweep_banner = f"""<div class="banner">Sweep holdout: <strong>{hold_label}</strong> · {n_var} variants tried on train/val.
        75% is a target, not a pass. {html.escape(str(sweep.get('multiple_comparisons') or ''))}</div>"""
    curve_rows = []
    table_sweep = []
    hold_sweep = sweep.get("holdout") or metrics.get("sweep_holdout") or []
    for fam in ("C_lastprice", "D_brownian_16", "A_logistic_z", "I_yes_last"):
        pts = [r for r in hold_sweep if r.get("family") == fam and r.get("offset_s") not in (None, 0)]
        pts = sorted(pts, key=lambda r: r.get("offset_s") or 0)
        cells = "".join(
            f"<td>{_pct(p.get('accuracy'))}<br><span class='tiny'>cov {_pct(p.get('coverage'))}</span></td>"
            for p in pts
        )
        if pts:
            curve_rows.append(f"<tr><td>{html.escape(fam)}</td>{cells}</tr>")
    for r in hold_sweep:
        table_sweep.append(
            "<tr>"
            f"<td>{html.escape(str(r.get('id')))}</td>"
            f"<td>{r.get('offset_s')}</td>"
            f"<td>{_pct(r.get('accuracy'))}</td>"
            f"<td>{_pct(r.get('wilson_lo'))}–{_pct(r.get('wilson_hi'))}</td>"
            f"<td>{_pct(r.get('coverage'))}</td>"
            f"<td>{r.get('n_scored')}</td>"
            f"<td>{html.escape(str(r.get('split')))}</td>"
            "</tr>"
        )
    heads = ""
    if curve_rows:
        offs = sorted({r.get("offset_s") for r in hold_sweep if r.get("family") == "C_lastprice" and r.get("offset_s")})
        heads = "".join(f"<th>+{o}s</th>" for o in offs)
    curve_html = ""
    if curve_rows:
        curve_html = f"""<div class="panel">
          <h2>Accuracy vs decision time (same holdout label)</h2>
          <p>75% reference. Coverage is never omitted.</p>
          <table><thead><tr><th>Family</th>{heads}</tr></thead><tbody>{''.join(curve_rows)}</tbody></table>
        </div>"""
    sweep_table_html = ""
    if table_sweep:
        sweep_table_html = f"""<div class="panel">
          <h2>Full strategy table</h2>
          <table><thead><tr><th>variant</th><th>t_dec offset s</th><th>Accuracy</th><th>Wilson 95%</th><th>Coverage</th><th>n</th><th>split</th></tr></thead>
          <tbody>{''.join(table_sweep)}</tbody></table>
        </div>"""
    chosen = ((sweep.get("selection") or {}).get("chosen")) or {}
    chosen_html = ""
    if chosen:
        chosen_html = f"""<div class="panel">
          <h2>Selected on train/val only</h2>
          <p>{html.escape(str(chosen.get('id')))} · walk-forward/val acc {_pct(chosen.get('accuracy'))}
             · coverage {_pct(chosen.get('coverage'))} · rule {html.escape(str((sweep.get('selection') or {}).get('rule')))}</p>
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
.preview{{border:1px solid #c9a227}}
.replay{{border:1px solid #2471a3}}
.tiny{{color:#7f8c8d;font-size:0.75rem}}
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
  <div>model {html.escape(str(metrics.get('model_version')))} · p_yes {html.escape(str(metrics.get('calibration')))} · 75% / 80–90% lines are targets, not a pass.</div>
</div>
{sweep_banner}
{live_panel}
{preview_card}
{replay_card}
{chosen_html}
{curve_html}
<div class="panel">
  <h2>Replay holdout — A logistic</h2>
  <p>Accuracy <strong>{_pct(acc)}</strong> (Wilson {_pct(a.get('wilson_lo'))}–{_pct(a.get('wilson_hi'))})
     · coverage {_pct(a.get('coverage'))} · n {a.get('n_scored')} · MAE {_num(a.get('mae'))}</p>
  {_bar(acc)}
  <div class="refs"><div class="ref">50% chance</div><div class="ref">target 75%</div><div class="ref">aspiration 80%</div><div class="ref">aspiration 90%</div></div>
</div>
{sweep_table_html}
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
    if metrics is None:
        metrics = {}
    summary = state_dir / "sweep" / "summary.json"
    if summary.is_file():
        sweep = json.loads(summary.read_text(encoding="utf-8"))
        metrics["sweep"] = sweep
        metrics["sweep_holdout"] = sweep.get("holdout")
        metrics["preopen_backtest"] = sweep.get("preopen_holdout")
    preview_path = state_dir / "preview.json"
    if preview_path.is_file():
        metrics["preview"] = json.loads(preview_path.read_text(encoding="utf-8"))
    if not metrics_path.is_file() and not summary.is_file():
        metrics = None
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
