"""Local read-only HTML. No fake metrics. Live panel requires observed-live snapshot."""

from __future__ import annotations

import html
import json
from pathlib import Path

from kxbtc15m.v3.hero import format_correct_summary


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{100.0 * float(value):.1f}%"


def _num(value, digits=2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _money(value) -> str:
    if value is None:
        return "—"
    v = float(value)
    return f"{v:,.2f}"


def _bar(acc: float | None) -> str:
    if acc is None:
        return ""
    width = max(0.0, min(100.0, 100.0 * acc))
    return f'<div class="bar"><span style="width:{width:.1f}%"></span></div>'


def _signed_money(value) -> str:
    if value is None:
        return "—"
    v = float(value)
    sign = "+" if v >= 0 else "−"
    return f"{sign}${abs(v):,.2f}"


def _direction_label(pred_yes) -> str:
    side = str(pred_yes or "").lower()
    if side == "yes":
        return "UP"
    if side == "no":
        return "DOWN"
    return "—"


def _count_correct(rows: list[dict]) -> tuple[int, int]:
    scored = [
        r
        for r in rows
        if not r.get("skip_reason")
        and r.get("pred_yes") in {"yes", "no"}
        and str(r.get("result") or "").lower() in {"yes", "no"}
    ]
    k = sum(1 for r in scored if str(r.get("pred_yes")).lower() == str(r.get("result")).lower())
    return k, len(scored)


def _recent_strip_html(live_track: dict | None, predictions: list[dict] | None) -> str:
    recent = list((live_track or {}).get("recent") or [])
    if not recent:
        # Fall back to last scored historical_replay rows (real results only).
        fallback = []
        for r in reversed(predictions or []):
            if r.get("skip_reason"):
                continue
            if r.get("pred_yes") not in {"yes", "no"}:
                continue
            if str(r.get("result") or "").lower() not in {"yes", "no"}:
                continue
            fallback.append(r)
            if len(fallback) >= 15:
                break
        fallback.reverse()
        recent = [
            {
                "ticker": r.get("ticker"),
                "pred_yes": r.get("pred_yes"),
                "result": r.get("result"),
                "correct": str(r.get("pred_yes")).lower() == str(r.get("result")).lower(),
            }
            for r in fallback
        ]
    if not recent:
        return """
        <section class="recent" id="recent-calls">
          <h2>Recent calls</h2>
          <p class="muted">No settled scored calls yet.</p>
        </section>"""
    k, n = 0, 0
    chips = []
    for r in recent:
        n += 1
        ok = r.get("correct")
        if ok is True:
            k += 1
        mark = "✓" if ok is True else ("✗" if ok is False else "?")
        cls = "ok" if ok is True else ("bad" if ok is False else "")
        call = _direction_label(r.get("pred_yes"))
        actual = _direction_label(r.get("result"))
        chips.append(
            f'<div class="chip {cls}" title="{html.escape(str(r.get("ticker") or ""))}">'
            f'<span class="mark">{mark}</span>'
            f'<span class="call">{call}</span>'
            f'<span class="vs">vs {actual}</span>'
            f"</div>"
        )
    summary = format_correct_summary(k, n) or "—"
    return f"""
    <section class="recent" id="recent-calls">
      <div class="recent-head">
        <h2>Recent calls</h2>
        <p class="pct" id="recent-summary">{html.escape(summary)}</p>
      </div>
      <div class="chips">{''.join(chips)}</div>
    </section>"""


def _hero_html(metrics: dict) -> str:
    preview = metrics.get("preview") or {}
    cur = preview.get("current") or {}
    nxt = preview.get("next") or {}
    live_track = preview.get("live_track") or metrics.get("live_track") or {}
    stale = bool(preview.get("stale"))
    stale_badge = '<span class="badge stale" id="stale-badge">stale</span>' if stale else '<span class="badge stale hidden" id="stale-badge">stale</span>'
    if cur.get("ticker") and cur.get("pred_yes") in {"yes", "no"}:
        direction = cur.get("hero_direction") or _direction_label(cur.get("pred_yes"))
        conf_pct = cur.get("hero_confidence_pct")
        conf_label = cur.get("hero_confidence_label") or ""
        conf_txt = f"{conf_pct}% · {html.escape(str(conf_label))}" if conf_pct is not None else "—"
        why = html.escape(str(cur.get("hero_why") or ""))
        hist = cur.get("hero_historical_summary")
        hist_acc = (cur.get("hero_historical") or {}).get("accuracy")
        hist_line = "Historical backtest at this decision time: —"
        if hist:
            hist_line = (
                f"Historical backtest at this decision time: {html.escape(hist)}"
                + (f" ({_pct(hist_acc)})" if hist_acc is not None else "")
            )
        fe = cur.get("hero_forecast_end")
        fe_mode = cur.get("hero_forecast_end_mode")
        fe_html = ""
        if fe_mode == "show" and fe is not None:
            fe_html = f'<div class="stat"><span>Model end (consistent)</span><strong>${_money(fe)}</strong></div>'
        change = cur.get("hero_change")
        if change is None and cur.get("S_t") is not None and cur.get("R_t") is not None:
            change = float(cur["R_t"]) - float(cur["S_t"])
        dir_cls = "up" if direction == "UP" else "down"
        hero_body = f"""
        <div class="hero-top">
          <div>
            <p class="eyebrow">Current 15-min market {stale_badge}</p>
            <h1 id="hero-ticker">{html.escape(str(cur.get('ticker')))}</h1>
            <p class="window" id="hero-window">{html.escape(str(cur.get('open_denver') or cur.get('open_time') or ''))}
               → {html.escape(str(cur.get('close_denver') or cur.get('close_time') or ''))}
               · America/Denver</p>
          </div>
          <div class="countdown-box">
            <span class="tiny">Closes in</span>
            <strong id="hero-countdown" data-close="{html.escape(str(cur.get('close_time') or ''))}">—</strong>
          </div>
        </div>
        <div class="hero-grid">
          <div class="call {dir_cls}" id="hero-call">
            <div class="call-label">Call</div>
            <div class="call-dir" id="hero-direction">{html.escape(direction)}</div>
            <div class="call-conf" id="hero-confidence">{html.escape(conf_txt)}</div>
            <p class="why" id="hero-why">{why}</p>
            <p class="hist" id="hero-hist">{hist_line}</p>
          </div>
          <div class="stats">
            <div class="stat"><span>Start S<sub>t</sub></span><strong id="hero-st">${_money(cur.get('S_t'))}</strong></div>
            <div class="stat"><span>Live BTC</span><strong id="hero-rt">${_money(cur.get('R_t'))}</strong></div>
            <div class="stat"><span>Change</span><strong id="hero-change">{_signed_money(change)}</strong></div>
            {fe_html}
            <div class="stat"><span>Family / t*</span><strong id="hero-family">{html.escape(str(cur.get('family') or '—'))} · {html.escape(str(cur.get('decision_offset_s')))}s</strong></div>
          </div>
        </div>
        """
    else:
        hero_body = f"""
        <div class="hero-top">
          <div>
            <p class="eyebrow">Current 15-min market {stale_badge}</p>
            <h1>Unavailable</h1>
            <p class="window">No observed-live snapshot. Run <code>v3-preview</code> or <code>v3-live</code>.</p>
          </div>
        </div>
        """

    # Next market card
    if nxt and nxt.get("ticker"):
        ndir = nxt.get("hero_direction") or _direction_label(nxt.get("pred_yes"))
        nconf = nxt.get("hero_confidence_pct")
        nlab = nxt.get("hero_confidence_label") or ""
        nconf_txt = f"{nconf}% · {html.escape(str(nlab))}" if nconf is not None else "—"
        next_card = f"""
        <aside class="next-card" id="next-card">
          <p class="eyebrow">Next market (pre-open)</p>
          <h2 id="next-ticker">{html.escape(str(nxt.get('ticker')))}</h2>
          <p class="window">{html.escape(str(nxt.get('open_denver') or ''))} → {html.escape(str(nxt.get('close_denver') or ''))}</p>
          <p>Est. start <strong>${_money(nxt.get('S_t'))}</strong>
             · Call <strong id="next-dir">{html.escape(ndir)}</strong>
             · {nconf_txt}</p>
          <p class="tiny">Pre-open backtest {_pct((metrics.get('preopen_backtest') or {}).get('accuracy'))}
             · n {(metrics.get('preopen_backtest') or {}).get('n_scored')}</p>
        </aside>"""
    else:
        next_card = """
        <aside class="next-card" id="next-card">
          <p class="eyebrow">Next market (pre-open)</p>
          <h2>Unavailable</h2>
          <p>Run <code>v3-preview</code>.</p>
        </aside>"""

    track = (live_track or {}).get("summary") or {}
    all_s = (track.get("all_time") or {}).get("summary") or "—"
    today_s = (track.get("today") or {}).get("summary") or "—"
    track_html = f"""
    <div class="track" id="live-track">
      <div><span class="tiny">Live track (settled only)</span><strong id="track-all">{html.escape(str(all_s))}</strong></div>
      <div><span class="tiny">Today (America/Denver)</span><strong id="track-today">{html.escape(str(today_s))}</strong></div>
      <div><span class="tiny">Historical backtest</span><strong>see hero / Details — separate from live</strong></div>
    </div>"""

    return f"""
    <section class="hero" id="hero">
      {hero_body}
      {track_html}
    </section>
    {next_card}
    """


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
    live_from_preview = ((metrics.get("preview") or {}).get("current") or {})
    # Legacy live panel kept under Details for substance parity.
    if live_from_preview.get("ticker"):
        live_panel = f"""
        <div class="panel live">
          <h2>Current market (observed live)</h2>
          <p>{html.escape(str(live_from_preview.get('ticker')))} · offset {html.escape(str(live_from_preview.get('decision_offset_s')))}s · {html.escape(str(live_from_preview.get('family')))}</p>
          <p>Start S<sub>t</sub> {_num(live_from_preview.get('S_t'))} · Predicted end {_num(live_from_preview.get('forecast_end'))}
             · Predicted <strong>{html.escape(str(live_from_preview.get('pred_yes') or '—').upper())}</strong>
             · p_yes {_num(live_from_preview.get('p_yes'), 3)}</p>
          <p class="tiny">Raw forecast_end may be a last-price proxy from a different rule than pred_yes; the hero uses classifier direction only.
             observation_at {html.escape(str(live_from_preview.get('observation_at')))} · prediction_asof {html.escape(str(live_from_preview.get('prediction_asof')))}</p>
        </div>"""
    elif live_rows:
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
          <p><strong>unavailable</strong> — no observed-live snapshot with observation_at ≤ t*. Replay numbers below are not live. Run <code>v3-preview</code>.</p>
        </div>"""
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
        ok = None
        if str(latest_replay.get("result") or "").lower() in {"yes", "no"}:
            ok = str(latest_replay.get("pred_yes")).lower() == str(latest_replay.get("result")).lower()
        mark = "✓ correct" if ok is True else ("✗ wrong" if ok is False else "—")
        # Running % over trailing scored historical rows ending at this window
        trail = []
        for r in predictions or []:
            if r.get("availability") != "historical_replay":
                continue
            if r.get("skip_reason") or r.get("pred_yes") not in {"yes", "no"}:
                continue
            if str(r.get("result") or "").lower() not in {"yes", "no"}:
                continue
            trail.append(r)
        # Include up through latest_replay ticker if present
        if latest_replay.get("ticker"):
            clipped = []
            for r in trail:
                clipped.append(r)
                if r.get("ticker") == latest_replay.get("ticker"):
                    break
            trail = clipped or trail
        k, n = _count_correct(trail[-50:] if trail else [])
        run_summary = format_correct_summary(k, n) or "—"
        single = format_correct_summary(1 if ok else 0, 1) if ok is not None else None
        single_txt = f" · this window {single}" if single else ""
        replay_card = f"""
        <div class="panel replay">
          <h2>Latest scored window (historical replay — not live)</h2>
          <p>{html.escape(str(latest_replay.get('ticker')))}</p>
          <p>Start S<sub>t</sub> <strong>{_num(latest_replay.get('S_t'))}</strong>
             · Predicted end <strong>{_num(latest_replay.get('forecast_end'))}</strong>
             · Predicted <strong>{html.escape(str(latest_replay.get('pred_yes')).upper())}</strong>
             · Actual {html.escape(str(latest_replay.get('result') or '—').upper())}
             · {mark}</p>
          <p class="pct-line">Guessed correctly: <strong>{html.escape(run_summary)}</strong>{html.escape(single_txt)} (trailing scored replay windows)</p>
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
    holdout_scored_rows = []
    for r in predictions or []:
        if r.get("split") != "holdout":
            continue
        ok = "yes" if r.get("pred_yes") == r.get("result") else "no"
        if r.get("skip_reason"):
            ok = "skip"
        elif r.get("pred_yes") in {"yes", "no"} and str(r.get("result") or "").lower() in {"yes", "no"}:
            holdout_scored_rows.append(r)
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
    hk, hn = _count_correct(holdout_scored_rows)
    holdout_summary = format_correct_summary(hk, hn) or "—"

    acc = a.get("accuracy")
    a_n = int(a.get("n_scored") or 0)
    if acc is not None and a_n > 0:
        a_summary = format_correct_summary(int(round(float(acc) * a_n)), a_n) or "—"
    else:
        a_summary = "—"
    hero = _hero_html(metrics)
    recent = _recent_strip_html(
        (metrics.get("preview") or {}).get("live_track") or metrics.get("live_track"),
        predictions,
    )
    live_js = _LIVE_JS
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KXBTC15M V3 replay</title>
<style>
:root{{--bg:#0e151c;--panel:#17202a;--ink:#e8eef4;--muted:#8b9aab;--line:#2c3e50;--up:#2ecc71;--down:#e74c3c;--accent:#c9a227}}
*{{box-sizing:border-box}}
body{{font-family:"Segoe UI",ui-sans-serif,system-ui,sans-serif;margin:0;background:radial-gradient(1200px 600px at 10% -10%,#1a2733,var(--bg));color:var(--ink)}}
main{{max-width:1100px;margin:0 auto;padding:1.25rem}}
.banner{{background:#1c2833;border-left:4px solid var(--accent);padding:1rem 1.2rem;margin-bottom:1rem}}
.panel{{background:var(--panel);padding:1rem 1.2rem;margin:1rem 0;border-radius:10px}}
.live{{border:1px dashed #7f8c8d}}
.preview{{border:1px solid var(--accent)}}
.replay{{border:1px solid #2471a3}}
.tiny,.muted{{color:var(--muted);font-size:0.78rem}}
table{{width:100%;border-collapse:collapse;font-size:0.92rem}}
th,td{{text-align:left;padding:0.4rem 0.5rem;border-bottom:1px solid var(--line)}}
.bar{{background:#2c3e50;height:8px;border-radius:4px;margin-top:0.4rem}}
.bar span{{display:block;height:8px;background:#27ae60}}
.refs{{display:flex;gap:1rem;margin:0.6rem 0 0;flex-wrap:wrap}}
.ref{{flex:1;min-width:5rem;background:#1a252f;padding:0.5rem;border-radius:4px;font-size:0.85rem}}
.hero{{background:linear-gradient(160deg,#1b2836,#121a22 60%);border:1px solid #314355;border-radius:16px;padding:1.25rem 1.35rem;margin-bottom:1rem}}
.hero-top{{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;align-items:flex-start}}
.eyebrow{{text-transform:uppercase;letter-spacing:0.08em;font-size:0.72rem;color:var(--muted);margin:0 0 0.35rem}}
.hero h1{{margin:0;font-size:clamp(1.35rem,3vw,2rem);font-weight:700}}
.window{{color:var(--muted);margin:0.35rem 0 0}}
.countdown-box{{background:#0f171f;border-radius:12px;padding:0.75rem 1rem;min-width:7rem;text-align:right}}
.countdown-box strong{{display:block;font-size:1.6rem;font-variant-numeric:tabular-nums}}
.hero-grid{{display:grid;grid-template-columns:1.2fr 1fr;gap:1rem;margin-top:1.1rem}}
@media (max-width:760px){{.hero-grid{{grid-template-columns:1fr}}}}
.call{{border-radius:14px;padding:1.1rem 1.2rem;background:#101820;border:1px solid #2b3c4d}}
.call.up{{border-color:rgba(46,204,113,0.45);box-shadow:inset 0 0 0 1px rgba(46,204,113,0.15)}}
.call.down{{border-color:rgba(231,76,60,0.45);box-shadow:inset 0 0 0 1px rgba(231,76,60,0.15)}}
.call-label{{font-size:0.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em}}
.call-dir{{font-size:clamp(3rem,10vw,4.5rem);font-weight:800;line-height:1;margin:0.2rem 0}}
.call.up .call-dir{{color:var(--up)}}
.call.down .call-dir{{color:var(--down)}}
.call-conf{{font-size:1.15rem;font-weight:600;margin-bottom:0.6rem}}
.why{{margin:0;font-size:1rem;line-height:1.45}}
.hist{{margin:0.7rem 0 0;color:var(--muted);font-size:0.86rem}}
.stats{{display:grid;grid-template-columns:1fr 1fr;gap:0.65rem}}
.stat{{background:#101820;border-radius:10px;padding:0.7rem 0.8rem}}
.stat span{{display:block;color:var(--muted);font-size:0.72rem;margin-bottom:0.2rem}}
.stat strong{{font-size:1.05rem;font-variant-numeric:tabular-nums}}
.track{{display:grid;grid-template-columns:repeat(3,1fr);gap:0.75rem;margin-top:1rem}}
@media (max-width:760px){{.track{{grid-template-columns:1fr}}}}
.track > div{{background:#101820;border-radius:10px;padding:0.7rem 0.8rem}}
.track strong{{display:block;margin-top:0.25rem}}
.next-card{{background:var(--panel);border:1px solid var(--accent);border-radius:12px;padding:1rem 1.15rem;margin:1rem 0}}
.next-card h2{{margin:0.2rem 0;font-size:1.15rem}}
.recent{{margin:1.25rem 0}}
.recent-head{{display:flex;justify-content:space-between;gap:1rem;align-items:baseline;flex-wrap:wrap}}
.recent h2{{margin:0}}
.pct{{margin:0;font-weight:600}}
.chips{{display:flex;gap:0.5rem;overflow-x:auto;padding:0.75rem 0 0.25rem}}
.chip{{flex:0 0 auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:0.55rem 0.7rem;min-width:5.5rem}}
.chip.ok{{border-color:rgba(46,204,113,0.5)}}
.chip.bad{{border-color:rgba(231,76,60,0.5)}}
.chip .mark{{display:block;font-weight:700}}
.chip .call{{font-size:1.05rem;font-weight:700}}
.chip .vs{{display:block;color:var(--muted);font-size:0.72rem}}
.badge{{display:inline-block;margin-left:0.5rem;padding:0.12rem 0.45rem;border-radius:999px;background:#6e2f2f;color:#ffd7d7;font-size:0.7rem;vertical-align:middle}}
.badge.hidden{{display:none}}
.details > h2{{margin:1.5rem 0 0.5rem;font-size:1.35rem}}
.pct-line{{color:var(--muted)}}
code{{background:#101820;padding:0.1rem 0.35rem;border-radius:4px}}
</style></head><body><main>
<div class="banner">
  <strong>historical_replay</strong> · assumption {html.escape(str(metrics.get('replay_assumption')))}.
  This score uses publication-proxy timestamps, not live-arrival proof.
  <div>prediction_asof (t*) is per row · dataset_asof {html.escape(str(metrics.get('dataset_asof')))} · run_generated_at {html.escape(str(metrics.get('run_generated_at')))}</div>
  <div>model {html.escape(str(metrics.get('model_version')))} · p_yes {html.escape(str(metrics.get('calibration')))} · 75% / 80–90% lines are targets, not a pass.</div>
</div>
{hero}
{recent}
<section class="details">
<h2>Details</h2>
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
  <p class="pct-line">Guessed correctly: <strong>{html.escape(a_summary)}</strong></p>
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
  <p class="pct-line">Guessed correctly (scored rows in this table): <strong>{html.escape(holdout_summary)}</strong></p>
  <table><thead><tr><th>ticker</th><th>prediction_asof</th><th>pred</th><th>actual</th><th>correct</th><th>|error|</th><th>availability</th></tr></thead>
  <tbody>{''.join(table_rows) if table_rows else '<tr><td colspan="7">no holdout rows</td></tr>'}</tbody></table>
</div>
</section>
<p style="color:#7f8c8d">Read-only. Public GET only. Not a trading profit backtest. Old paper ledgers were not written.</p>
</main>
<script>
{live_js}
</script>
</body></html>
"""


_LIVE_JS = r"""
(function () {
  function fmtMoney(v) {
    if (v == null || v === "") return "—";
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return "$" + n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }
  function fmtSigned(v) {
    if (v == null || v === "") return "—";
    var n = Number(v);
    if (!isFinite(n)) return "—";
    var sign = n >= 0 ? "+" : "−";
    return sign + "$" + Math.abs(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  function tickCountdown() {
    var el = document.getElementById("hero-countdown");
    if (!el) return;
    var close = el.getAttribute("data-close");
    if (!close) { el.textContent = "—"; return; }
    var end = Date.parse(close);
    if (!isFinite(end)) { el.textContent = "—"; return; }
    var ms = end - Date.now();
    if (ms <= 0) { el.textContent = "0:00"; return; }
    var s = Math.floor(ms / 1000);
    var m = Math.floor(s / 60);
    var r = s % 60;
    el.textContent = m + ":" + pad(r);
  }
  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }
  function applyPreview(data) {
    var stale = document.getElementById("stale-badge");
    if (stale) {
      if (data && data.stale) stale.classList.remove("hidden");
      else stale.classList.add("hidden");
    }
    var cur = (data && data.current) || {};
    if (cur.ticker) {
      setText("hero-ticker", cur.ticker);
      var win = (cur.open_denver || cur.open_time || "") + " → " + (cur.close_denver || cur.close_time || "") + " · America/Denver";
      setText("hero-window", win);
      var cd = document.getElementById("hero-countdown");
      if (cd) cd.setAttribute("data-close", cur.close_time || "");
      var dir = cur.hero_direction || (cur.pred_yes === "yes" ? "UP" : (cur.pred_yes === "no" ? "DOWN" : "—"));
      setText("hero-direction", dir);
      var call = document.getElementById("hero-call");
      if (call) {
        call.classList.remove("up", "down");
        if (dir === "UP") call.classList.add("up");
        if (dir === "DOWN") call.classList.add("down");
      }
      var conf = "—";
      if (cur.hero_confidence_pct != null) conf = cur.hero_confidence_pct + "% · " + (cur.hero_confidence_label || "");
      setText("hero-confidence", conf);
      if (cur.hero_why) setText("hero-why", cur.hero_why);
      if (cur.hero_historical_summary) {
        setText("hero-hist", "Historical backtest at this decision time: " + cur.hero_historical_summary);
      }
      setText("hero-st", fmtMoney(cur.S_t));
      setText("hero-rt", fmtMoney(cur.R_t));
      var ch = cur.hero_change;
      if (ch == null && cur.S_t != null && cur.R_t != null) ch = Number(cur.R_t) - Number(cur.S_t);
      setText("hero-change", fmtSigned(ch));
      setText("hero-family", (cur.family || "—") + " · " + (cur.decision_offset_s != null ? cur.decision_offset_s + "s" : "—"));
    }
    var nxt = (data && data.next) || {};
    if (nxt.ticker) {
      setText("next-ticker", nxt.ticker);
      var nd = nxt.hero_direction || (nxt.pred_yes === "yes" ? "UP" : (nxt.pred_yes === "no" ? "DOWN" : "—"));
      setText("next-dir", nd);
    }
    var track = (data && data.live_track && data.live_track.summary) || {};
    if (track.all_time && track.all_time.summary) setText("track-all", track.all_time.summary);
    if (track.today && track.today.summary) setText("track-today", track.today.summary);
    tickCountdown();
  }
  function poll() {
    fetch("preview.json", {cache: "no-store"})
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(applyPreview)
      .catch(function () {
        var stale = document.getElementById("stale-badge");
        if (stale) stale.classList.remove("hidden");
      });
  }
  tickCountdown();
  setInterval(tickCountdown, 1000);
  setInterval(poll, 5000);
  poll();
})();
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
    track_path = state_dir / "live_track.json"
    if track_path.is_file():
        metrics["live_track"] = json.loads(track_path.read_text(encoding="utf-8"))
        if metrics.get("preview") is not None and "live_track" not in metrics["preview"]:
            metrics["preview"]["live_track"] = metrics["live_track"]
    if not metrics_path.is_file() and not summary.is_file() and not preview_path.is_file():
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
