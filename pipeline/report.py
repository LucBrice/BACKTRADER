"""
pipeline/report.py
==================
Génération du rapport HTML Section 4 — agnostique à la stratégie.

Reçoit une liste de dicts produits par alpha_pipeline()
et génère un fichier HTML autonome avec :
  V1. Heatmap entonnoir multi-actifs
  V2. Distribution Y (KS) — Signal vs Flat
  V3. Rolling Spearman — Stabilité temporelle
  V4. Boxplot Y — Long / Short / Flat
  V5. Radar 4 étapes bloquantes

Point d’entrée : generate_html_report(all_results, tf, horizon_h, ...)
"""

from __future__ import annotations
import os
import json
import webbrowser
from dataclasses import dataclass, field
import numpy as np

OUTPUT_DIR = "Reports"


@dataclass
class ReportContext:
    """
    Context contract for strategy-specific report interpretations.
    Enables overriding generic JS messages and dynamic thresholds.
    """
    strategy_name:       str = "GenericStrategy"
    strategy_type:       str = "trend"        # "mean_reversion" | "trend" | "hybrid_pullback" | "breakout"
    alpha_threshold_bps: float = 5.0  # exploitability threshold (default = 5 bps)
    overrides:           dict  = field(default_factory=dict)

def _hist_bins(data, n_bins=60):
    if not data: return {"labels": [], "values": []}
    a = np.array(data)
    p1, p99 = np.percentile(a, [1, 99])
    a = a[(a >= p1) & (a <= p99)]
    counts, edges = np.histogram(a, bins=n_bins)
    width = edges[1] - edges[0]
    density = (counts / counts.sum() / width).tolist() if counts.sum() > 0 else counts.tolist()
    centers = ((edges[:-1] + edges[1:]) / 2 * 10000).round(2).tolist()
    return {"labels": centers, "values": [round(v, 6) for v in density]}


def _boxplot_stats(data):
    if not data: return {}
    a = np.array(data)
    q1, med, q3 = np.percentile(a, [25, 50, 75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5*iqr, q3 + 1.5*iqr
    return {
        "q1": round(q1, 6), "median": round(med, 6), "q3": round(q3, 6),
        "whisker_lo": round(float(a[a >= lo].min()), 6),
        "whisker_hi": round(float(a[a <= hi].max()), 6),
        "mean": round(float(a.mean()), 6), "n": len(a)
    }


def generate_html_report(all_results, tf, horizon_h,
                          report_context: ReportContext | None = None,
                          output_dir=OUTPUT_DIR, open_browser=True,
                          report_label: str | None = None):
    os.makedirs(output_dir, exist_ok=True)
    
    # Use report_label if provided, fallback to tf
    label = report_label if report_label else tf
    filepath = os.path.join(output_dir, f"Section4_Report_{label}.html")

    tf_min_str = tf.replace("min","").replace("h","60")
    try:    tf_min = int(tf_min_str)
    except: tf_min = 15

    assets_data = []
    for r in all_results:
        assets_data.append({
            # Identité & décision
            "asset":           r.get("asset", "?"),
            "decision":        r.get("decision", "NO GO"),
            "is_go":           r.get("decision", "NO GO") == "GO",
            "fail_step":       r.get("fail_step"),
            "fail_reason":     r.get("fail_reason"),
            "tests_passed":    r.get("tests_passed", 0),
            # Signaux
            "n_signals":       r.get("n_signals", 0),
            "n_long":          r.get("n_long", 0),
            "n_short":         r.get("n_short", 0),
            # Étape 0 — Sanity
            "sanity_ok":       r.get("sanity_ok", False),
            "sanity_nan":      r.get("sanity_nan", False),
            "sanity_inf":      r.get("sanity_inf", False),
            # Étape 1 — Spearman + MI
            "step1_ok":        r.get("step1_ok", False),
            "spearman_corr":   r.get("spearman_corr"),
            "spearman_pval":   r.get("spearman_pval"),
            "spearman_go":     r.get("spearman_go", False),
            "mi":              r.get("mutual_info"),
            "mi_go":           r.get("mi_go", False),
            # Étape 2 — KS + T-test + Wilcoxon
            "step2_ok":        r.get("step2_ok", False),
            "ks_stat":         r.get("ks_stat"),
            "ks_pval":         r.get("ks_pval"),
            "ks_go":           r.get("ks_go", False),
            "ttest_stat":      r.get("ttest_stat"),
            "ttest_pval":      r.get("ttest_pval"),
            "ttest_go":        r.get("ttest_go", False),
            "wilcoxon_stat":   r.get("wilcoxon_stat"),
            "wilcoxon_pval":   r.get("wilcoxon_pval"),
            "wilcoxon_go":     r.get("wilcoxon_go", False),
            # Étape 3 — Quantile
            "step3_ok":        r.get("step3_ok", False),
            "q_mono":          r.get("quantile_monotone", False),
            "q1_vs_q5_diff":   r.get("q1_vs_q5_diff"),
            "q1_vs_q5_ok":     r.get("q1_vs_q5_exploitable", False),
            "quantile_returns":r.get("quantile_returns", {}),
            "quantile_sharpes":r.get("quantile_sharpes", {}),
            # Étape 4 — Robustesse (non bloquant)
            "robustness_flag": r.get("robustness_flag"),
            "rolling_std":     r.get("rolling_std"),
            "rolling_median":  r.get("rolling_median"),
            "rolling_sign_ch": r.get("rolling_sign_changes"),
            # Shuffle control
            "shuffle_corr":    r.get("shuffle_corr"),
            "shuffle_ok":      r.get("shuffle_ok", False),
            # Performance
            "wr_long":         r.get("win_rate_long"),
            "wr_short":        r.get("win_rate_short"),
            "avg_y_long":      r.get("avg_Y_long"),
            "avg_y_short":     r.get("avg_Y_short"),
            "avg_y_flat":      r.get("avg_Y_flat"),
            "sl_long_pct":     round((r.get("avg_sl_dist_long") or 0)*100, 3),
            "sl_short_pct":    round((r.get("avg_sl_dist_short") or 0)*100, 3),
            # Graphiques
            "rolling_idx":     r.get("rolling_spearman_idx", []),
            "rolling_corr":    r.get("rolling_spearman_corr", []),
            "hist_signal":     _hist_bins(r.get("Y_signal_sample", [])),
            "hist_flat":       _hist_bins(r.get("Y_flat_sample", [])),
            "box_long":        _boxplot_stats(r.get("Y_long_sample", [])),
            "box_short":       _boxplot_stats(r.get("Y_short_sample", [])),
            "box_flat":        _boxplot_stats(r.get("Y_flat_sample", [])),
            "avg_y_flat":      round(sum(r.get("Y_flat_sample", [0])) / max(len(r.get("Y_flat_sample", [1])),1), 6),
            "detail":          r.get("detail", ""),
        })

    class NpEnc(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, (int,)) or hasattr(o, "item"): return o.item() if hasattr(o,"item") else o
            return super().default(o)
    data_json     = json.dumps(assets_data, ensure_ascii=False, cls=NpEnc)
    ctx_json      = json.dumps({
        "strategy_type": report_context.strategy_type,
        "alpha_threshold_bps": report_context.alpha_threshold_bps,
        "overrides": report_context.overrides
    }, ensure_ascii=False) if report_context else "null"

    go_count      = sum(1 for a in assets_data if a["is_go"])
    nogo_count    = len(assets_data) - go_count
    horizon_min   = horizon_h * tf_min
    strategy_name = all_results[0].get("strategy", "—") if all_results else "—" 

    HTML = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Section 4 — Pré-validation | {tf}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root {{
  --bg:#0b0d12;--bg2:#12151d;--bg3:#1a1e2a;--bg4:#212536;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.13);
  --text:#dde1f0;--muted:#6b728f;--hint:#454b63;
  --go:#00c97a;--go-dim:rgba(0,201,122,0.12);--go-border:rgba(0,201,122,0.28);
  --ng:#f0455a;--ng-dim:rgba(240,69,90,0.12);--ng-border:rgba(240,69,90,0.28);
  --amber:#f4a535;--blue:#4f9cf9;--purple:#9b7ff4;
  --mono:'Fira Code','JetBrains Mono','Courier New',monospace;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'IBM Plex Sans','Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;font-size:14px}}

/* Header */
header{{padding:2rem 2.5rem 1.4rem;border-bottom:1px solid var(--border);display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:1rem}}
.h-title{{font-size:1.25rem;font-weight:700;letter-spacing:-0.02em}}
.h-meta{{font-size:0.75rem;color:var(--muted);margin-top:5px;font-family:var(--mono)}}
.pills{{display:flex;gap:8px;flex-shrink:0;align-items:center}}
.pill{{font-size:0.72rem;font-weight:700;padding:5px 14px;border-radius:99px;letter-spacing:0.05em}}
.pill-go{{background:var(--go-dim);color:var(--go);border:1px solid var(--go-border)}}
.pill-ng{{background:var(--ng-dim);color:var(--ng);border:1px solid var(--ng-border)}}

/* Layout */
main{{padding:1.8rem 2.5rem 3rem;max-width:1440px}}
.sec-label{{font-size:0.65rem;font-weight:700;letter-spacing:0.13em;text-transform:uppercase;color:var(--muted);padding-left:10px;border-left:3px solid var(--purple);margin:2.2rem 0 1.1rem}}

/* KPI strip */
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:1.8rem}}
.kpi{{background:var(--bg2);border:1px solid var(--border);border-radius:9px;padding:1rem 1.1rem}}
.kpi .lbl{{font-size:0.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em}}
.kpi .val{{font-size:1.75rem;font-weight:700;margin-top:3px;font-family:var(--mono);line-height:1.1}}
.kpi .sub{{font-size:0.68rem;color:var(--hint);margin-top:3px}}

/* Heatmap table */
.tbl-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;overflow:auto;margin-bottom:0.5rem}}
table{{width:100%;border-collapse:collapse;font-size:0.8rem;white-space:nowrap}}
th{{padding:9px 13px;text-align:left;font-weight:600;font-size:0.67rem;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);border-bottom:1px solid var(--border)}}
td{{padding:10px 13px;border-bottom:1px solid rgba(255,255,255,0.04);font-family:var(--mono);font-size:0.78rem}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover td{{background:rgba(255,255,255,0.02)}}
.bdg{{display:inline-block;padding:2px 9px;border-radius:4px;font-size:0.68rem;font-weight:700;letter-spacing:0.04em}}
.bdg-go{{background:var(--go-dim);color:var(--go)}}
.bdg-ng{{background:var(--ng-dim);color:var(--ng)}}
.c-go{{color:var(--go)}} .c-ng{{color:var(--ng)}} .c-am{{color:var(--amber)}} .c-mu{{color:var(--muted)}}

/* Asset tabs */
.tabs{{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:1.2rem}}
.tab{{padding:5px 15px;border-radius:6px;border:1px solid var(--border);background:var(--bg2);color:var(--muted);font-size:0.78rem;cursor:pointer;transition:all .15s;font-family:var(--mono);font-weight:600}}
.tab:hover{{border-color:var(--border2);color:var(--text)}}
.tab.go.active{{border-color:var(--go-border);color:var(--go);background:var(--go-dim)}}
.tab.ng.active{{border-color:var(--ng-border);color:var(--ng);background:var(--ng-dim)}}
.tab.go{{border-color:rgba(0,201,122,0.2);color:var(--go)}}
.tab.ng{{border-color:rgba(240,69,90,0.15);color:var(--ng)}}

/* Decision banner */
.banner{{border-radius:10px;padding:1.1rem 1.5rem;display:flex;align-items:center;gap:14px;margin-bottom:1.4rem;border:1px solid}}
.banner.go{{background:var(--go-dim);border-color:var(--go-border)}}
.banner.ng{{background:var(--ng-dim);border-color:var(--ng-border)}}
.banner .icon{{font-size:1.6rem;flex-shrink:0}}
.banner .btitle{{font-size:0.95rem;font-weight:700}}
.banner .bsub{{font-size:0.75rem;color:var(--muted);margin-top:2px}}

/* Stat mini-grid */
.sg{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-bottom:1.2rem}}
@media(max-width:700px){{.sg{{grid-template-columns:1fr 1fr}}}}
.sc{{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:.85rem 1rem}}
.sc .sl{{font-size:0.67rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em}}
.sc .sv{{font-size:1.2rem;font-weight:600;margin-top:3px;font-family:var(--mono)}}
.sc .ss{{font-size:0.67rem;color:var(--hint);margin-top:2px}}

/* Test list */
.tlist{{display:flex;flex-direction:column;gap:7px;margin-bottom:1.4rem}}
.trow{{display:flex;align-items:center;gap:11px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:9px 13px}}
.trow .tn{{font-size:0.8rem;font-weight:600;flex:1}}
.trow .td{{font-size:0.72rem;color:var(--muted);font-family:var(--mono)}}
.trow .tv{{font-size:0.68rem;font-weight:700;padding:2px 8px;border-radius:4px}}

/* Charts */
.cg{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:900px){{.cg{{grid-template-columns:1fr}}}}
.cp{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:1.3rem 1.3rem 1rem}}
.cp h3{{font-size:0.67rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted);margin-bottom:.9rem;display:flex;align-items:center;gap:6px}}
.cw{{position:relative;width:100%;height:195px}}

footer{{margin-top:2.5rem;padding:1.3rem 2.5rem;border-top:1px solid var(--border);font-size:0.7rem;color:var(--hint);display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}}

/* ── Entonnoir compact (strip) ── */
.funnel-strip{{display:flex;gap:4px;flex-wrap:wrap;align-items:center;padding:9px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;margin-bottom:1.1rem}}
.fs-step{{display:flex;align-items:center;gap:4px;font-size:0.72rem;font-family:var(--mono)}}
.fs-sep{{color:var(--hint);padding:0 2px}}
.fs-lbl{{color:var(--muted);font-size:0.68rem}}
.fs-ok{{color:var(--go);font-weight:700}}.fs-ng{{color:var(--ng);font-weight:700}}.fs-am{{color:var(--amber);font-weight:700}}
/* ── Card unifiée ── */
.card{{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:11px 14px;margin-bottom:8px}}
.card-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}}
.card-title{{font-size:0.64rem;font-weight:700;text-transform:uppercase;letter-spacing:0.09em;color:var(--muted)}}
.vd{{font-size:0.64rem;font-weight:700;padding:2px 8px;border-radius:3px;border:0.5px solid}}
.vd-go{{background:rgba(0,201,122,0.10);color:var(--go);border-color:rgba(0,201,122,0.22)}}
.vd-warn{{background:rgba(244,165,53,0.10);color:var(--amber);border-color:rgba(244,165,53,0.22)}}
.vd-ng{{background:rgba(240,69,90,0.10);color:var(--ng);border-color:rgba(240,69,90,0.22)}}
.vd-neu{{background:rgba(107,114,143,0.08);color:var(--muted);border-color:rgba(107,114,143,0.2)}}
.mrow{{display:flex;align-items:baseline;gap:8px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:0.72rem}}
.mrow:last-of-type{{border-bottom:none}}
.ml{{color:var(--muted);min-width:140px;flex-shrink:0}}
.mv{{font-family:var(--mono);font-weight:600;font-size:0.71rem}}
.mv.pos{{color:var(--go)}}.mv.neg{{color:var(--ng)}}.mv.neu{{color:var(--muted)}}.mv.warn{{color:var(--amber)}}
.mn{{font-size:0.66rem;color:var(--hint);flex:1}}
.insight{{font-size:0.73rem;color:#9aa3bc;line-height:1.6;border-top:1px solid rgba(255,255,255,0.05);padding-top:8px;margin-top:8px}}
.insight b,.insight strong{{color:var(--text);font-weight:600}}
.insight .go{{color:var(--go);font-weight:600}}.insight .ng{{color:var(--ng);font-weight:600}}.insight .am{{color:var(--amber);font-weight:600}}
.brow{{display:flex;align-items:center;gap:7px;margin:2px 0;font-size:0.68rem;color:var(--muted)}}
.blbl{{min-width:36px;text-align:right}}.bbg{{flex:1;height:4px;background:rgba(255,255,255,0.07);border-radius:2px;overflow:hidden}}.bfill{{height:100%;border-radius:2px}}
.synth-block{{margin-top:1.2rem;border:1px solid rgba(155,127,244,0.18);border-radius:9px;padding:13px 15px;background:rgba(155,127,244,0.04)}}
.synth-title{{font-size:0.64rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(155,127,244,0.65);margin-bottom:9px;display:flex;align-items:center;justify-content:space-between}}
.sitem{{display:flex;gap:12px;align-items:baseline;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:0.73rem}}
.sitem:last-child{{border-bottom:none}}
.snum{{color:rgba(155,127,244,0.55);font-weight:700;font-size:0.67rem;min-width:14px;flex-shrink:0}}
.stxt{{color:#9aa3bc;line-height:1.5;flex:1}}
.stxt b,.stxt strong{{color:var(--text);font-weight:600}}
.stxt .go{{color:var(--go);font-weight:600}}.stxt .ng{{color:var(--ng);font-weight:600}}.stxt .am{{color:var(--amber);font-weight:600}}

/* ── Grid interprétation (onglet interp) ── */
.interp-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:4px}}
@media(max-width:900px){{.interp-grid{{grid-template-columns:1fr}}}}
/* Aliases pour compatibilité avec les fonctions JS existantes */
.icard{{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:11px 13px}}
.icard-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.icard-title{{font-size:0.64rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted)}}
.ivd,.ivd-go,.ivd-warn,.ivd-ng{{font-size:0.64rem;font-weight:700;padding:2px 8px;border-radius:3px;border:0.5px solid}}
.ivd-go{{background:rgba(0,201,122,0.10);color:var(--go);border-color:rgba(0,201,122,0.22)}}
.ivd-warn{{background:rgba(244,165,53,0.10);color:var(--amber);border-color:rgba(244,165,53,0.22)}}
.ivd-ng{{background:rgba(240,69,90,0.10);color:var(--ng);border-color:rgba(240,69,90,0.22)}}
.imet{{display:flex;align-items:baseline;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:0.72rem}}
.imet:last-of-type{{border-bottom:none}}
.imet-lbl{{color:var(--muted)}}.imet-val{{font-family:var(--mono);font-weight:600;font-size:0.71rem}}.imet-ctx{{font-size:0.66rem;color:var(--hint);margin-left:5px}}
.ipos{{color:var(--go)}}.ineg{{color:var(--ng)}}.ineu{{color:var(--muted)}}.iwarn{{color:var(--amber)}}
.ibar-wrap{{display:flex;align-items:center;gap:8px;margin:3px 0}}
.ibar-lbl{{font-size:0.67rem;color:var(--muted);min-width:36px}}.ibar-bg{{flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden}}.ibar-fill{{height:100%;border-radius:2px}}
.interp-block{{margin-top:10px;border-top:1px solid rgba(255,255,255,0.06);padding-top:10px}}
.interp-row{{display:flex;align-items:baseline;gap:10px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:0.72rem}}
.interp-row:last-of-type{{border-bottom:none}}
.ir-label{{color:var(--muted);min-width:150px;flex-shrink:0}}
.ir-val{{font-family:var(--mono);font-weight:600;font-size:0.72rem}}
.ir-val.pos{{color:var(--go)}}.ir-val.neg{{color:var(--ng)}}.ir-val.neu{{color:var(--muted)}}.ir-val.am{{color:var(--amber)}}
.ir-note{{font-size:0.68rem;color:var(--hint);flex:1}}
.interp-verdict{{display:inline-flex;align-items:center;gap:4px;font-size:0.67rem;font-weight:700;padding:2px 8px;border-radius:3px;margin-bottom:8px;border:0.5px solid}}
.iv-go{{background:rgba(0,201,122,0.10);color:var(--go);border-color:rgba(0,201,122,0.22)}}
.iv-warn{{background:rgba(244,165,53,0.10);color:var(--amber);border-color:rgba(244,165,53,0.22)}}
.iv-ng{{background:rgba(240,69,90,0.10);color:var(--ng);border-color:rgba(240,69,90,0.22)}}
.interp-insight{{font-size:0.73rem;color:#9aa3bc;line-height:1.55;margin-top:7px;padding-top:7px;border-top:1px solid rgba(255,255,255,0.05)}}
.interp-insight b{{color:var(--text);font-weight:600}}
.bar-mini{{display:flex;align-items:center;gap:7px;margin:2px 0;font-size:0.68rem;color:var(--muted)}}
.bar-mini-bg{{flex:1;height:4px;background:rgba(255,255,255,0.07);border-radius:2px;overflow:hidden}}.bar-mini-fill{{height:100%;border-radius:2px}}

/* ── Tooltip système ── */
.tip-wrap{{position:relative;display:inline-flex;align-items:center}}
.tip-icon{{
  display:inline-flex;align-items:center;justify-content:center;
  width:14px;height:14px;border-radius:50%;
  background:rgba(155,127,244,0.15);color:#9b7ff4;
  font-size:8px;font-weight:700;cursor:help;flex-shrink:0;
  border:1px solid rgba(155,127,244,0.28);font-style:normal;line-height:1;
  margin-left:5px;
}}
.tip-icon:hover{{background:rgba(155,127,244,0.3);border-color:rgba(155,127,244,0.5)}}
.tip-box{{
  visibility:hidden;opacity:0;
  transition:opacity .12s ease,visibility .12s;
  position:absolute;z-index:9999;
  left:calc(100% + 14px);top:50%;transform:translateY(-50%);
  width:400px;
  background:#13161f;
  border:1px solid rgba(155,127,244,0.22);
  border-radius:10px;
  box-shadow:0 16px 48px rgba(0,0,0,0.7),0 0 0 1px rgba(0,0,0,0.3);
  pointer-events:none;
  overflow:hidden;
}}
.tip-wrap:hover .tip-box{{visibility:visible;opacity:1}}
.tip-box::before{{
  content:'';position:absolute;right:100%;top:50%;transform:translateY(-50%);
  border:6px solid transparent;border-right-color:rgba(155,127,244,0.22);
}}
/* Titre */
.tb-title{{
  font-size:0.78rem;font-weight:700;color:#dde1f2;
  padding:12px 14px 10px;
  border-bottom:1px solid rgba(255,255,255,0.06);
  background:rgba(155,127,244,0.06);
  letter-spacing:-0.01em;
}}
/* Sections internes */
.tip-section{{padding:10px 14px 0}}
.tip-section:last-child{{padding-bottom:12px}}
.tip-section+.tip-section{{border-top:1px solid rgba(255,255,255,0.04)}}
/* Label de section */
.tip-label{{
  font-size:0.58rem;font-weight:700;text-transform:uppercase;
  letter-spacing:0.11em;color:rgba(155,127,244,0.6);
  margin-bottom:6px;
}}
/* Texte définition */
.tip-def{{font-size:0.75rem;color:#8a93ab;line-height:1.55;margin:0}}
/* Tableau des seuils */
.tip-rows{{display:flex;flex-direction:column;gap:0}}
.tip-row{{
  display:flex;align-items:center;gap:10px;
  padding:5px 0;
  border-bottom:1px solid rgba(255,255,255,0.04);
}}
.tip-row:last-child{{border-bottom:none}}
.tip-verdict{{
  flex-shrink:0;min-width:72px;text-align:center;
  padding:2px 8px;border-radius:4px;
  font-size:0.66rem;font-weight:700;letter-spacing:0.02em;
}}
.tv-go{{background:rgba(0,201,122,0.13);color:#00c97a;border:1px solid rgba(0,201,122,0.2)}}
.tv-ng{{background:rgba(240,69,90,0.13);color:#f0455a;border:1px solid rgba(240,69,90,0.2)}}
.tv-am{{background:rgba(244,165,53,0.13);color:#f4a535;border:1px solid rgba(244,165,53,0.2)}}
.tr-desc{{font-size:0.72rem;color:#7a8299;flex:1;line-height:1.4}}
.tr-desc code{{background:rgba(255,255,255,0.08);border-radius:3px;padding:0 5px;font-size:0.69rem;font-family:'Fira Code',monospace;color:#b8c0d4}}
/* Interprétation */
.tip-interp{{font-size:0.74rem;color:#8a93ab;line-height:1.55;display:flex;flex-direction:column;gap:6px;margin:0}}
.tip-interp .ti{{display:flex;align-items:baseline;gap:6px}}
.tip-interp .ti-dot{{
  flex-shrink:0;width:5px;height:5px;border-radius:50%;margin-top:5px;
}}
.ti-dot-go{{background:#00c97a}}
.ti-dot-ng{{background:#f0455a}}
.ti-dot-am{{background:#f4a535}}
.tip-interp strong{{font-weight:600}}
.tip-interp .go{{color:#00c97a;font-weight:600}}
.tip-interp .ng{{color:#f0455a;font-weight:600}}
.tip-interp .am{{color:#f4a535;font-weight:600}}
.tip-interp code{{background:rgba(255,255,255,0.08);border-radius:3px;padding:0 5px;font-size:0.69rem;font-family:'Fira Code',monospace;color:#b8c0d4}}
</style>
</head>
<body>

<header>
  <div>
    <div class="h-title">Section 4 — Pré-validation statistique</div>
    <div class="h-meta">TF: {tf} &nbsp;·&nbsp; Horizon: {horizon_h} barres ({horizon_min} min) &nbsp;·&nbsp; Stratégie : {strategy_name}</div>
  </div>
  <div class="pills">
    <span class="pill pill-go">GO &nbsp;{go_count}</span>
    <span class="pill pill-ng">NO GO &nbsp;{nogo_count}</span>
  </div>
</header>

<main>

<div class="sec-label">Vue d'ensemble</div>
<div class="kpi-strip">
  <div class="kpi"><div class="lbl">Actifs scannés</div><div class="val" id="k-tot">—</div><div class="sub">universe complet</div></div>
  <div class="kpi"><div class="lbl" style="color:var(--go)">Assets GO</div><div class="val c-go" id="k-go">—</div><div class="sub" id="k-go-l">—</div></div>
  <div class="kpi"><div class="lbl" style="color:var(--ng)">Assets NO GO</div><div class="val c-ng" id="k-ng">—</div><div class="sub" id="k-ng-l">—</div></div>
  <div class="kpi"><div class="lbl">Signaux totaux</div><div class="val" id="k-sig">—</div><div class="sub">tous actifs</div></div>
  <div class="kpi"><div class="lbl">Barres / actif</div><div class="val" id="k-bars">—</div><div class="sub">2020 – 2023</div></div>
</div>

<div class="sec-label">Heatmap des tests — tous actifs</div>
<div class="tbl-wrap">
<table>
<thead><tr>
  <th>Asset</th><th>Décision</th><th>Étapes</th><th>Signaux</th>
  <th id="th-sanity" style="cursor:help">E0 Sanity</th>
  <th id="th-spearman" style="cursor:help">E1 Spearman ρ</th>
  <th id="th-mi" style="cursor:help">MI</th>
  <th id="th-ks" style="cursor:help">E2 KS p</th>
  <th id="th-ttest" style="cursor:help">T-test p</th>
  <th id="th-wilcoxon" style="cursor:help">Wilcoxon p</th>
  <th id="th-quantile" style="cursor:help">E3 Quantile</th>
  <th id="th-rolling" style="cursor:help">E4 Rob.</th>
  <th id="th-shuffle" style="cursor:help">Shuffle ρ</th>
  <th>WR Long</th><th>WR Short</th><th>SL Long</th>
</tr></thead>
<tbody id="htbody"></tbody>
</table>
</div>

<div class="sec-label">Analyse détaillée par actif</div>
<div class="tabs" id="tabs"></div>
<div id="panels"></div>

</main>

<footer>
  <span>Blueprint Section 4 — Quant R&D Pipeline</span>
  <span>Généré le <span id="gd"></span></span>
</footer>

<script>
const D = {data_json};
const STRATEGY_CTX = {ctx_json};
Chart.defaults.color='#6b728f';

// ── Tooltips ─────────────────────────────────────────────────────────────
const TIPS = {{
  sanity: {{
    title: "Étape 0 — Sanity Check",
    def: "Vérifie l'intégrité de X et Y avant tout calcul : absence de NaN/Inf et volume minimum de signaux pour que les tests soient statistiquement fiables.",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO</span><span class="tr-desc">0 NaN · 0 Inf · n ≥ <code>100</code> signaux actifs</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">STOP</span><span class="tr-desc">Toute condition manquante arrête le pipeline</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">Rejet ici</span> → historique trop court, filtres trop stricts, ou bug dans <code>build_payload()</code> produisant des NaN.</span></div>
<div class="ti"><span class="ti-dot ti-dot-am"></span><span><span class="am">Correction</span> → augmenter la période de données ou assouplir les conditions d’entrée pour dépasser 100 signaux.</span></div>
</div>`
  }},
  spearman: {{
    title: "Spearman ρ — Corrélation de rang",
    def: "Mesure si signal fort et rendement élevé tendent à coïncider, sans supposer de linéarité. Valide sur tout type de signal : discret {{-1, 0, 1}} ou continu (RSI, z-score...).",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO</span><span class="tr-desc">p-value < <code>0.05</code> (valeur de ρ peu importe)</span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Normal</span><span class="tr-desc">|ρ| ∈ [0.03, 0.10] — typique en trading réel</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">NO GO seul</span><span class="tr-desc">p ≥ 0.05, mais MI peut compenser</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">ρ &gt; 0</span> → signal fort prédit hausse (momentum). <span class="go">ρ &lt; 0</span> → signal fort prédit baisse (mean-reversion).</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">p non significatif</span> → aucune relation de rang détectée. Seul MI peut compenser — sinon revoir la logique d’entrée.</span></div>
</div>`
  }},
  mi: {{
    title: "Mutual Information — Dépendance non-linéaire",
    def: "Capture toute dépendance entre X et Y, y compris les relations que Spearman rate : asymétriques, par seuil, ou conditionnelles.",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO</span><span class="tr-desc">MI > <code>0.01</code></span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Zone grise</span><span class="tr-desc">MI ∈ [0.005, 0.01] — signal faible, exploitable sur grand volume</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">NO GO seul</span><span class="tr-desc">MI = 0, mais Spearman peut compenser</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">MI = 0 + Spearman non significatif</span> → X ne contient aucune information sur Y. Revoir le timing d’entrée, l’horizon H ou les conditions du signal.</span></div>
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">MI &gt; 0.01</span> → dépendance non-linéaire présente. Continuer vers l'Étape 2.</span></div>
</div>`
  }},
  ks: {{
    title: "Test KS — Kolmogorov-Smirnov",
    def: "Compare la forme entière des distributions de rendements : signal actif vs signal inactif. Détecte tout type de décalage — moyenne, variance, ou queues.",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO</span><span class="tr-desc">p-value < <code>0.05</code></span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Borderline</span><span class="tr-desc">p ∈ [0.05, 0.10] → croiser avec T-test</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">NO GO seul</span><span class="tr-desc">p ≥ 0.05, T-test ou Wilcoxon peuvent valider l'étape</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">KS significatif</span> → les distributions diffèrent. Décalage horizontal = edge directionnel. Queues asymétriques = edge de sélection.</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">KS non significatif</span> → distributions identiques. Si T-test passe seul, l’edge est sur la moyenne uniquement — fragile, surveiller.</span></div>
</div>`
  }},
  ttest: {{
    title: "T-test de Welch — Comparaison de moyennes",
    def: "Compare la moyenne des rendements entre deux groupes extrêmes du signal. Groupes adaptés automatiquement : Long vs Short (discret) ou top 30% vs bottom 30% (continu).",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO</span><span class="tr-desc">p-value < <code>0.05</code></span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Note</span><span class="tr-desc">Sensible aux outliers → toujours croiser avec Wilcoxon</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">T-test + KS GO</span> → double preuve convergente : edge sur la moyenne et sur la distribution. Signal solide.</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">T-test NO GO</span> → les deux groupes ont la même espérance. Revoir le timing d’entrée ou les conditions de filtrage.</span></div>
</div>`
  }},
  wilcoxon: {{
    title: "Wilcoxon — Comparaison de rangs",
    def: "Version robuste du T-test basée sur les rangs plutôt que les valeurs. Insensible aux outliers extrêmes (gros trades isolés).",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO</span><span class="tr-desc">p-value < <code>0.05</code></span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Complémentaire</span><span class="tr-desc">Renforce le T-test — les deux GO = preuve solide</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">Wilcoxon GO, T-test NO GO</span> → quelques outliers faussent la moyenne, mais l’edge de fond est réel et structurel.</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">T-test GO, Wilcoxon NO GO</span> → l’edge vient de quelques trades exceptionnels, pas d'une tendance systématique. Edge fragile.</span></div>
</div>`
  }},
  quantile: {{
    title: "Étape 3 — Analyse quantile / classe ⚠️ CRITIQUE",
    def: "Vérifie que les rendements progressent de façon exploitable selon le niveau de signal. Méthode auto-adaptée : par valeur (discret) ou par bin (continu).",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO</span><span class="tr-desc">Tendance monotone OU |Q1−Q5| > <code>1 bps</code></span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">STOP</span><span class="tr-desc">Aucun pattern — même si E1 et E2 ont passé</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">Monotone</span> → "signal fort = meilleur rendement attendu". Règle d’entrée exploitable. Passer en Section 5.</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">Pas de pattern</span> → le signal est statistiquement présent mais pas encore tradable. Revoir les seuils ou l’horizon H.</span></div>
</div>`
  }},
  rolling: {{
    title: "Étape 4 — Robustesse temporelle (non bloquant)",
    def: "Fenêtre glissante de 500 signaux recalculant la corrélation Spearman à chaque pas. Révèle si l’edge est stable dans le temps ou régime-dépendant.",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">Stable</span><span class="tr-desc">std < <code>0.15</code> et changements de signe < 40%</span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Fragile</span><span class="tr-desc">std ≥ 0.15 — stratégie sensible aux régimes de marché</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">Non bloquant</span><span class="tr-desc">Un signal fragile peut quand même aller en Section 5</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">Stable</span> → edge indépendant du régime. Bon candidat pour Section 5 sans ajustement.</span></div>
<div class="ti"><span class="ti-dot ti-dot-am"></span><span><span class="am">Fragile</span> → ajouter un filtre de régime (tendance, volatilité) pour désactiver le signal en période défavorable.</span></div>
</div>`
  }},
  shuffle: {{
    title: "Shuffle Control — Détection de biais",
    def: "Mélange aléatoirement X en gardant Y intact et recalcule la corrélation. Un edge réel doit disparaître après ce shuffle.",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">OK</span><span class="tr-desc">|ρ_shuffled| < <code>0.03</code></span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">Alerte</span><span class="tr-desc">|ρ| ≥ 0.03 → biais dans la construction des données</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">ρ ≈ 0</span> → l’edge provient bien du signal. Résultats fiables.</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">ρ élevé après shuffle</span> → lookahead probable : Y calculé sur une fenêtre chevauchant X, ou normalisation incorrecte dans <code>build_payload()</code>.</span></div>
</div>`
  }},
  chart_ks: {{
    title: "Distribution Y — Signal vs Flat",
    def: "Histogrammes superposés des rendements forward Y : signal actif (bleu) vs inactif (gris). Visualisation directe de ce que le test KS mesure. Axe X en bps (0.01% = 1 bps).",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">Edge clair</span><span class="tr-desc">Courbe bleue décalée par rapport à Flat</span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Edge de queue</span><span class="tr-desc">Centres alignés, mais queues asymétriques</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">Pas d’edge</span><span class="tr-desc">Deux courbes quasi-identiques</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">Décalage horizontal</span> → edge de direction. TP/SL classique fonctionne.</span></div>
<div class="ti"><span class="ti-dot ti-dot-am"></span><span><span class="am">Queue droite plus large</span> → le signal sélectionne les gros mouvements → augmenter le TP. Queue gauche plus petite → le signal évite les grosses pertes → serrer le SL.</span></div>
</div>`
  }},
  chart_rolling: {{
    title: "Rolling Spearman ρ — Stabilité dans le temps",
    def: "Corrélation Spearman recalculée sur une fenêtre glissante de 500 signaux. Chaque point = edge local. Ligne pointillée = zéro (aucun edge).",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">Idéal</span><span class="tr-desc">Courbe régulière, légèrement au-dessus du zéro</span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Acceptable</span><span class="tr-desc">Quelques plongées négatives mais retour rapide</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">Problème</span><span class="tr-desc">Longues périodes sous zéro — edge non structurel</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">Courbe stable ∈ [0.05, 0.10]</span> → edge robuste et structurel. Aller en Section 5.</span></div>
<div class="ti"><span class="ti-dot ti-dot-am"></span><span><span class="am">Oscillations</span> → identifier la variable de régime (trend, VIX, spread) qui corrèle avec les zones positives/négatives et s’en servir comme filtre.</span></div>
</div>`
  }},
  chart_boxplot: {{
    title: "Boxplot Y — Long / Short / Flat",
    def: "Boîtes à moustaches des rendements Y par direction de signal. Médiane = barre centrale, boîte = Q1–Q3, moustaches = 1.5× IQR.",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">Bidirectionnel</span><span class="tr-desc">Long ET Short au-dessus de Flat</span></div>
<div class="tip-row"><span class="tip-verdict tv-go">Directionnel</span><span class="tr-desc">Une seule direction nettement au-dessus</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">Pas d’edge</span><span class="tr-desc">Trois boîtes superposées</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">Long >> Short</span> → biaiser vers les longs, filtrer les shorts (et inversement). <span class="am">IQR large</span> → edge bruité : SL strict. <span class="am">IQR étroite</span> → signal précis : TP large possible.</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">Médiane ≈ Flat</span> → l’edge n’est pas directionnel. Regarder le graphique KS pour détecter un edge de forme ou de queue.</span></div>
</div>`
  }},
  chart_radar: {{
    title: "Radar — 4 étapes bloquantes",
    def: "Polygone à 4 axes correspondant aux étapes du pipeline. Axe rempli = validé, axe vide = rejeté. La surface totale traduit la solidité de l’alpha.",
    seuils: `<div class="tip-rows">
<div class="tip-row"><span class="tip-verdict tv-go">GO complet</span><span class="tr-desc">Les 4 axes remplis</span></div>
<div class="tip-row"><span class="tip-verdict tv-am">Partiel</span><span class="tr-desc">2–3 axes : signal détecté, pas encore tradable</span></div>
<div class="tip-row"><span class="tip-verdict tv-ng">Minimal</span><span class="tr-desc">0–1 axe : données insuffisantes ou aucun signal</span></div>
</div>`,
    interp: `<div class="tip-interp">
<div class="ti"><span class="ti-dot ti-dot-go"></span><span><span class="go">E1+E2 pleins, E3 vide</span> → signal statistiquement prouvé mais pas encore exploitable. Revoir les seuils ou l’horizon H.</span></div>
<div class="ti"><span class="ti-dot ti-dot-ng"></span><span><span class="ng">E1 vide</span> → aucune information dans X. Revoir la logique de signal avant toute autre étape.</span></div>
</div>`
  }}
}};

// Helper : génère l’icône ⓘ avec la bulle d'aide
// pos = 'right' (défaut) | 'up' — direction d'ouverture de la bulle
function tt(key, pos='right') {{
  const t = TIPS[key];
  if (!t) return '';
  // Pour les graphiques on ouvre vers le haut pour ne pas sortir du viewport
  const boxStyle = pos==='up'
    ? 'left:50%;transform:translateX(-50%);top:auto;bottom:calc(100% + 10px);'
    : '';
  const arrowStyle = pos==='up'
    ? 'content:"";position:absolute;left:50%;transform:translateX(-50%);top:100%;border:6px solid transparent;border-top-color:rgba(155,127,244,0.35);'
    : '';
  return `<span class="tip-wrap">
    <i class="tip-icon">i</i>
    <div class="tip-box" style="${{boxStyle}}">
      <div class="tb-title">${{t.title}}</div>
      <div class="tip-section">
        <div class="tip-label">Définition</div>
        <p class="tip-def">${{t.def}}</p>
      </div>
      <div class="tip-section">
        <div class="tip-label">Seuils de validation</div>
        ${{t.seuils}}
      </div>
      <div class="tip-section">
        <div class="tip-label">Comment agir</div>
        ${{t.interp}}
      </div>
    </div>
  </span>`;
}}
Chart.defaults.font.family="'Fira Code','JetBrains Mono',monospace";
Chart.defaults.font.size=11;
const C={{go:'#00c97a',ng:'#f0455a',blue:'#4f9cf9',purple:'#9b7ff4',amber:'#f4a535',grid:'rgba(255,255,255,0.05)'}};

const f=(v,d=4)=>v==null?'—':Number(v).toFixed(d);
const p=(v,d=1)=>v==null?'—':(Number(v)*100).toFixed(d)+'%';
const bdg=(ok)=>ok?'<span class="bdg bdg-go">✅ GO</span>':'<span class="bdg bdg-ng">❌ NO GO</span>';
const cc=(v,pos=true)=>{{
  if(v==null)return'—';const n=Number(v);
  if(pos)return`<span class="${{n>0?'c-go':n<0?'c-ng':'c-mu'}}">${{f(v,5)}}</span>`;
  return`<span class="${{Math.abs(n)<0.03?'c-go':'c-ng'}}">${{f(v,4)}}</span>`;
}};

// KPIs
document.getElementById('gd').textContent=new Date().toLocaleString('fr-FR');
const go_a=D.filter(d=>d.is_go).map(d=>d.asset);
const ng_a=D.filter(d=>!d.is_go).map(d=>d.asset);
document.getElementById('k-tot').textContent=D.length;
document.getElementById('k-go').textContent=go_a.length;
document.getElementById('k-go-l').textContent=go_a.join(' · ')||'—';
document.getElementById('k-ng').textContent=ng_a.length;
document.getElementById('k-ng-l').textContent=ng_a.join(' · ')||'—';
document.getElementById('k-sig').textContent=D.reduce((s,d)=>s+(d.n_signals||0),0).toLocaleString('fr-FR');
document.getElementById('k-bars').textContent='93 192';

// Heatmap — entonnoir v4.1
const tb=document.getElementById('htbody');
D.slice().sort((a,b)=>(b.is_go-a.is_go)||(b.tests_passed-a.tests_passed)).forEach(d=>{{
  const tp=d.tests_passed;
  const tpc=tp>=4?'c-go':tp>=3?'c-am':'c-ng';
  const robC=d.robustness_flag==='stable'?'c-go':d.robustness_flag==='fragile'?'c-am':'c-mu';
  const robL=d.robustness_flag==='stable'?'Stable ✅':d.robustness_flag==='fragile'?'⚠️ Fragile':'—';
  const row=document.createElement('tr');
  row.innerHTML=`
    <td style="font-weight:700;color:${{d.is_go?'var(--go)':'var(--text)'}}">${{d.asset}}</td>
    <td>${{bdg(d.is_go)}}</td>
    <td class="${{tpc}}" style="font-weight:700">${{tp}}/4</td>
    <td>${{(d.n_signals||0).toLocaleString()}}</td>
    <td class="${{d.sanity_ok?'c-go':'c-ng'}}">${{d.sanity_ok?'✅':'❌'}}</td>
    <td class="${{d.step1_ok?'c-go':'c-ng'}}">${{f(d.spearman_corr)}} / MI ${{f(d.mi,3)}}</td>
    <td class="${{d.mi_go?'c-go':'c-ng'}}">${{f(d.mi,4)}}</td>
    <td class="${{d.ks_go?'c-go':'c-ng'}}">${{f(d.ks_pval)}}</td>
    <td class="${{d.ttest_go?'c-go':'c-ng'}}">${{f(d.ttest_pval)}}</td>
    <td class="${{d.wilcoxon_go?'c-go':'c-ng'}}">${{f(d.wilcoxon_pval)}}</td>
    <td class="${{d.step3_ok?'c-go':'c-ng'}}">${{d.q_mono?'Mono ✅':d.q1_vs_q5_ok?'Q1/Q5 ✅':'❌'}}</td>
    <td class="${{robC}}">${{robL}}</td>
    <td class="${{d.shuffle_ok?'c-go':'c-ng'}}">${{f(d.shuffle_corr)}}</td>
    <td class="${{(d.wr_long||0)>0.5?'c-go':'c-mu'}}">${{p(d.wr_long)}}</td>
    <td class="${{(d.wr_short||0)>0.5?'c-go':'c-mu'}}">${{p(d.wr_short)}}</td>
    <td class="c-mu">${{d.sl_long_pct?d.sl_long_pct.toFixed(3)+'%':'—'}}</td>`;
  tb.appendChild(row);
}});

// Tabs + panels
const tabsEl=document.getElementById('tabs');
const panelsEl=document.getElementById('panels');

function activate(i){{
  document.querySelectorAll('.tab').forEach((t,j)=>t.classList.toggle('active',j===i));
  document.querySelectorAll('.apanel').forEach((p,j)=>{{
    p.style.display=j===i?'block':'none';
    if(j===i&&!p.dataset.r){{renderPanel(D[i],i);p.dataset.r='1'}}
  }});
}}

D.forEach((d,i)=>{{
  const t=document.createElement('button');
  t.className=`tab ${{d.is_go?'go':'ng'}}`;
  t.textContent=d.asset;
  t.onclick=()=>activate(i);
  tabsEl.appendChild(t);

  const pn=document.createElement('div');
  pn.className='apanel';pn.style.display='none';
  pn.innerHTML=buildPanel(d,i);
  panelsEl.appendChild(pn);
}});
activate(0);

function buildPanel(d,i){{
  const ok=d.is_go;
  const slg=d.sl_long_pct?d.sl_long_pct.toFixed(3)+'%':'—';
  const sls=d.sl_short_pct?d.sl_short_pct.toFixed(3)+'%':'—';
  const yl=d.avg_y_long?(d.avg_y_long*10000).toFixed(2)+' bps':'—';
  const ys=d.avg_y_short?(d.avg_y_short*10000).toFixed(2)+' bps':'—';
  const robC=d.robustness_flag==='stable'?'var(--go)':d.robustness_flag==='fragile'?'var(--amber)':'var(--muted)';
  const robL=d.robustness_flag==='stable'?'Stable ✅':d.robustness_flag==='fragile'?'⚠️ Fragile':'—';

  function step_row(num, label, ok, tag, sub, items, tipKeys=[]){{
    const bg=ok?'rgba(0,201,122,0.06)':'rgba(240,69,90,0.06)';
    const bc=ok?'var(--go-border)':'var(--ng-border)';
    const tagLabel=tag?`<span style="font-size:0.65rem;font-weight:700;padding:2px 7px;border-radius:3px;background:${{tag==='BLOQUANT'?'rgba(240,69,90,.2)':tag==='CRITIQUE'?'rgba(244,165,53,.35)':'rgba(107,114,143,.25)'}};color:${{tag==='BLOQUANT'?'var(--ng)':tag==='CRITIQUE'?'var(--amber)':'var(--muted)'}}">${{tag}}</span>`:'';
    const itemsHtml=items.map((it,idx)=>{{
      const tipHtml = tipKeys[idx] ? tt(tipKeys[idx]) : '';
      return `<div style="display:flex;align-items:center;gap:5px;font-family:var(--mono);font-size:0.72rem;color:${{it.ok?'var(--go)':'var(--ng)'}}">
        ${{it.ok?'✅':'❌'}} <span style="color:var(--muted)">${{it.label}}:</span> ${{it.val}} ${{tipHtml}}
      </div>`;
    }}).join('');
    const stepTip = tipKeys[0] && num === -1 ? tt(tipKeys[0]) : '';
    return`<div style="border:1px solid ${{bc}};border-radius:8px;padding:10px 14px;background:${{bg}};margin-bottom:7px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <span style="font-size:1rem">${{ok?'✅':'❌'}}</span>
        <span style="font-size:0.75rem;font-weight:700;color:var(--muted)">Étape ${{num}}</span>
        <span style="font-size:0.82rem;font-weight:600;flex:1">${{label}}</span>
        ${{tagLabel}}
        ${{stepTip}}
      </div>
      <div style="font-size:0.7rem;color:var(--hint);margin-bottom:8px">${{sub}}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">${{itemsHtml}}</div>
    </div>`;
  }}

  const failBanner = !ok && d.fail_step != null ? `
    <div style="background:rgba(240,69,90,0.1);border:1px solid var(--ng-border);border-radius:8px;padding:9px 14px;margin-bottom:12px;font-size:0.78rem;color:var(--ng)">
      ⛔ Rejet à l'Étape ${{d.fail_step}} — ${{d.fail_reason||''}}
    </div>` : '';

  // ── Fonction centrale : génère le bloc interprétation dynamique ─────────
  function buildInterp(d){{
    const bpx = s => s!=null?(s*10000).toFixed(2)+' bps':'—';
    const bpxN = s => s!=null?+(s*10000).toFixed(2):null;
    const pct = v => v!=null?(v*100).toFixed(1)+'%':'—';
    const na = v => v!=null?v:'—';

    // ── Bloc 1 : Alpha net Long vs Flat ──────────────────────────────────
    const mLong  = bpxN(d.avg_y_long);
    const mShort = bpxN(d.avg_y_short);
    const mFlat  = d.box_flat&&d.box_flat.median!=null ? +(d.box_flat.median*10000).toFixed(2) : null;
    const alphaNet = (mLong!=null&&mFlat!=null) ? +(mLong-mFlat).toFixed(2) : null;
    const iqrLong  = (d.box_long&&d.box_long.q1!=null&&d.box_long.q3!=null)
                      ? +((d.box_long.q3-d.box_long.q1)*10000).toFixed(1) : null;
    const iqrShort = (d.box_short&&d.box_short.q1!=null&&d.box_short.q3!=null)
                      ? +((d.box_short.q3-d.box_short.q1)*10000).toFixed(1) : null;
    const iqrFlat  = (d.box_flat&&d.box_flat.q1!=null&&d.box_flat.q3!=null)
                      ? +((d.box_flat.q3-d.box_flat.q1)*10000).toFixed(1) : null;

    const alphaVerdict = alphaNet==null?'—':alphaNet>5?'Edge exploitable':alphaNet>1?'Edge faible':'Pas d’edge';
    const alphaVClass  = alphaNet==null?'icv-warn':alphaNet>5?'icv-go':alphaNet>1?'icv-warn':'icv-ng';

    const shortDiff = (mShort!=null&&mFlat!=null)?+(mShort-mFlat).toFixed(2):null;
    const shortVerdict = shortDiff==null?'—':shortDiff>1?'Edge court':Math.abs(shortDiff)<1?'Neutre':'Sous-performe Flat';
    const shortVClass  = shortDiff==null?'icv-warn':shortDiff>1?'icv-go':Math.abs(shortDiff)<1?'icv-warn':'icv-ng';

    const maxIqr = Math.max(iqrLong||0,iqrShort||0,iqrFlat||0)||1;
    const iqrLongPct  = iqrLong!=null  ? Math.round(iqrLong/maxIqr*100)  : 0;
    const iqrShortPct = iqrShort!=null ? Math.round(iqrShort/maxIqr*100) : 0;
    const iqrFlatPct  = iqrFlat!=null  ? Math.round(iqrFlat/maxIqr*100)  : 0;
    const iqrVerdict = iqrLong==null?'—':iqrLong<30?'Signal précis':iqrLong<50?'Dispersion modérée':'Signal très bruité';
    const iqrVClass  = iqrLong==null?'icv-warn':iqrLong<30?'icv-go':iqrLong<50?'icv-warn':'icv-ng';

    // ── Bloc 2 : Étapes E1–E3 valeur vs seuil ─────────────────────────────
    const THRESH_SPEARMAN=0.05, THRESH_MI=0.01, THRESH_KS=0.05;
    const spMarg = d.spearman_pval!=null ? (THRESH_SPEARMAN-d.spearman_pval).toFixed(4) : null;
    const ksMarg = d.ks_pval!=null ? (THRESH_KS-d.ks_pval).toFixed(4) : null;
    const diffBps = d.q1_vs_q5_diff!=null ? (d.q1_vs_q5_diff*10000).toFixed(2) : null;

    // ── Bloc 3 : Rolling Spearman ─────────────────────────────────────────
    const rollStd = d.rolling_std;
    const rollMed = d.rolling_median;
    const rollSC  = d.rolling_sign_ch;
    const robFlag = d.robustness_flag;
    const robLong = robFlag==='stable'?'Stable ✅':robFlag==='fragile'?'⚠️ Fragile — régime-dépendant':'Données insuffisantes';
    const robVC   = robFlag==='stable'?'icv-go':robFlag==='fragile'?'icv-warn':'icv-warn';

    // ── Bloc 4 : Recommandation synthèse ─────────────────────────────────
    const recs = [];
    if(mShort!=null&&mFlat!=null&&mShort<mFlat) recs.push('<strong>Supprimer les Short</strong> — médiane sous Flat, aucune valeur ajoutée.');
    else if(mShort!=null&&Math.abs(shortDiff||0)<1) recs.push('<strong>Filtrer les Short</strong> — médiane neutre, pas de directionnalité.');
    if(alphaNet!=null&&alphaNet>0&&alphaNet<=5) recs.push('<strong>Renforcer les filtres Long</strong> — alpha net '+alphaNet+' bps, cible > 5 bps.');
    if(iqrLong!=null&&iqrLong>50) recs.push('<strong>SL serré requis</strong> — IQR Long '+iqrLong+' bps, dispersion élevée par trade.');
    if(robFlag==='fragile') recs.push('<strong>Ajouter un filtre de régime</strong> — edge instable dans le temps.');
    if(!d.step1_ok) recs.push('<strong>Revoir la logique de signal</strong> — Spearman et MI non significatifs.');
    if(!d.step3_ok&&d.step1_ok&&d.step2_ok) recs.push('<strong>Retravailler l’horizon H</strong> — signal présent mais non exploitable par quantile.');
    if(recs.length===0) recs.push(d.is_go?'<strong>Edge validé</strong> — passer en Section 5.':'<strong>Itérer sur la logique d’entrée</strong> avant Section 5.');

    return`
    <div class="ic">
      <div class="ic-head"><span class="ic-title">Alpha long vs flat</span><span class="ic-verdict ${{alphaVClass}}">${{alphaVerdict}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Médiane Long</span><span class="ic-val ${{mLong>0?'pos':mLong<0?'neg':'neu'}}">${{mLong!=null?mLong+' bps':'—'}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Médiane Flat (référence)</span><span class="ic-val neu">${{mFlat!=null?mFlat+' bps':'—'}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Alpha net réel</span><span class="ic-val ${{alphaNet>5?'pos':alphaNet>1?'neu':'neg'}}">${{alphaNet!=null?alphaNet+' bps':'—'}}</span><span class="ic-sub">seuil d'exploitabilité > 5 bps</span></div>
      <div class="ic-insight">
        ${{alphaNet>5?('<strong>Edge exploitable</strong> — alpha net '+alphaNet+' bps au-dessus du seuil.')
          :alphaNet>1?('<strong>Edge marginal</strong> — '+alphaNet+' bps d’alpha net '+(5-alphaNet).toFixed(2)+' bps sous le seuil. Renforcer les filtres.')
          :alphaNet!=null?('<strong>Pas d’edge Long</strong> — alpha net '+alphaNet+' bps, inférieur au bruit de marché.')
          :'Données insuffisantes pour calculer l’alpha net.'}}
      </div>
    </div>

    <div class="ic">
      <div class="ic-head"><span class="ic-title">Signal Short</span><span class="ic-verdict ${{shortVClass}}">${{shortVerdict}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Médiane Short</span><span class="ic-val ${{mShort>0?'pos':mShort<0?'neg':'neu'}}">${{mShort!=null?mShort+' bps':'—'}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Différentiel vs Flat</span><span class="ic-val ${{shortDiff>0?'pos':shortDiff<0?'neg':'neu'}}">${{shortDiff!=null?(shortDiff>0?'+':'')+shortDiff+' bps':'—'}}</span></div>
      <div class="ic-insight">
        ${{shortDiff<0?('<strong>Short sous-performe Flat de '+Math.abs(shortDiff)+' bps</strong> — être en position short dégrade l’espérance. Filtrer ou supprimer.')
          :Math.abs(shortDiff||0)<1?('<strong>Short neutre</strong> — aucune directionnalité détectée (diff = '+shortDiff+' bps).')
          :('<strong>Edge Short présent</strong> — '+shortDiff+' bps au-dessus de Flat.')}}
      </div>
    </div>

    <div class="ic">
      <div class="ic-head"><span class="ic-title">Dispersion IQR par direction</span><span class="ic-verdict ${{iqrVClass}}">${{iqrVerdict}}</span></div>
      <div class="ic-bar-row"><span class="ic-bar-lbl">Long</span><div class="ic-bar-bg"><div class="ic-bar-fill" style="width:${{iqrLongPct}}%;background:#00c97a;opacity:.7"></div></div><span style="font-size:0.7rem;color:var(--muted);min-width:50px">${{iqrLong!=null?iqrLong+' bps':'—'}}</span></div>
      <div class="ic-bar-row"><span class="ic-bar-lbl">Short</span><div class="ic-bar-bg"><div class="ic-bar-fill" style="width:${{iqrShortPct}}%;background:#f0455a;opacity:.7"></div></div><span style="font-size:0.7rem;color:var(--muted);min-width:50px">${{iqrShort!=null?iqrShort+' bps':'—'}}</span></div>
      <div class="ic-bar-row"><span class="ic-bar-lbl">Flat</span><div class="ic-bar-bg"><div class="ic-bar-fill" style="width:${{iqrFlatPct}}%;background:#6b728f;opacity:.5"></div></div><span style="font-size:0.7rem;color:var(--muted);min-width:50px">${{iqrFlat!=null?iqrFlat+' bps':'—'}}</span></div>
      <div class="ic-insight">
        ${{iqrLong!=null&&iqrFlat!=null?
          ('IQR Long '+iqrLong+' bps = '+(iqrFlat>0?((iqrLong/iqrFlat-1)*100).toFixed(0):0)+'% '+(iqrLong>iqrFlat?'plus large':'plus étroite')+' que Flat — '+(iqrLong<30?'signal précis, TP serré envisageable.':iqrLong>50?'forte dispersion, SL strict indispensable.':'dispersion modérée.'))
          :'Données insuffisantes.'}}
      </div>
    </div>

    <div class="ic">
      <div class="ic-head"><span class="ic-title">Étapes E1–E3 : valeur réelle vs seuil</span></div>
      <div class="ic-row"><span class="ic-lbl">Spearman p-value</span>
        <span class="ic-val ${{d.spearman_go?'pos':'neg'}}">${{na(d.spearman_pval)}}</span>
        <span class="ic-sub">seuil < 0.05 · marge ${{spMarg!=null?(+spMarg>0?'+':'')+spMarg:'—'}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Mutual Info</span>
        <span class="ic-val ${{d.mi_go?'pos':'neg'}}">${{na(d.mi)}}</span>
        <span class="ic-sub">seuil > 0.01</span></div>
      <div class="ic-row"><span class="ic-lbl">KS p-value</span>
        <span class="ic-val ${{d.ks_go?'pos':'neg'}}">${{na(d.ks_pval)}}</span>
        <span class="ic-sub">seuil < 0.05 · marge ${{ksMarg!=null?(+ksMarg>0?'+':'')+ksMarg:'—'}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Q1/Q5 diff</span>
        <span class="ic-val ${{d.q1_vs_q5_ok?'pos':'neg'}}">${{diffBps!=null?diffBps+' bps':'—'}}</span>
        <span class="ic-sub">seuil |diff| > 1 bps</span></div>
    </div>

    <div class="ic">
      <div class="ic-head"><span class="ic-title">Robustesse temporelle</span><span class="ic-verdict ${{robVC}}">${{robFlag||'—'}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Rolling std</span>
        <span class="ic-val ${{rollStd!=null&&rollStd<0.15?'pos':'neg'}}">${{na(rollStd)}}</span>
        <span class="ic-sub">seuil < 0.15</span></div>
      <div class="ic-row"><span class="ic-lbl">Médiane rolling ρ</span>
        <span class="ic-val ${{rollMed>0?'pos':rollMed<0?'neg':'neu'}}">${{na(rollMed)}}</span></div>
      <div class="ic-row"><span class="ic-lbl">Changements de signe</span>
        <span class="ic-val neu">${{na(rollSC)}}</span></div>
      <div class="ic-insight">${{robLong}}</div>
    </div>

    <div class="ic" style="border-color:${{d.is_go?'rgba(0,201,122,0.3)':'rgba(244,165,53,0.3)'}}">
      <div class="ic-head"><span class="ic-title">Recommandations</span><span class="ic-verdict ${{d.is_go?'icv-go':'icv-warn'}}">${{d.is_go?'GO Section 5':'Itérer'}}</span></div>
      <div style="font-size:0.73rem;color:var(--muted);line-height:1.8;display:flex;flex-direction:column;gap:4px">
        ${{recs.map((r,n)=>`<div style="display:flex;gap:8px"><span style="color:${{d.is_go?'var(--go)':'var(--amber)'}};flex-shrink:0">${{n+1}}.</span><span>${{r}}</span></div>`).join('')}}
      </div>
    </div>`;
  }}

  // Funnel strip compact : une ligne, toutes étapes
  const fsStep=(num,lbl,ok,tipKey,vals)=>{{
    const vclass=ok?'fs-ok':'fs-ng';
    const icon=ok?'✅':'❌';
    const valStr=vals?` <span style="font-size:0.66rem;color:var(--hint)">(` +vals+ `)</span>`:'';
    return`<span class="fs-step">
      <span class="${{vclass}}">`+icon+`</span>
      <span class="fs-lbl">`+lbl+`</span>${{tt(tipKey)}}
      `+valStr+`
    </span>`;
  }};
  const spVal=d.spearman_pval!=null?('p='+f(d.spearman_pval)):'MI='+f(d.mi,3);
  const ksVal=d.ks_pval!=null?('KS='+f(d.ks_pval)):'—';
  const q3Val=d.q1_vs_q5_diff!=null?((d.q1_vs_q5_diff*10000).toFixed(1)+'bps'):(d.q_mono?'Mono':'—');

  return`
  <div class="banner ${{ok?'go':'ng'}}">
    <div class="icon">${{ok?'✅':'❌'}}</div>
    <div style="flex:1">
      <div class="btitle">${{ok?'GO — Edge validé':'NO GO — '+( d.fail_reason||'Rejet étape '+d.fail_step)}}</div>
      <div class="bsub" style="margin-top:4px;display:flex;gap:14px;flex-wrap:wrap">
        <span>${{d.tests_passed}}/4 étapes</span>
        <span>Signaux ${{d.n_signals}} (L ${{d.n_long}} · S ${{d.n_short}})</span>
        ${{yl!=='—'?`<span>WR Long ${{p(d.wr_long)}} · Avg ${{yl}}</span>`:''}}
        ${{d.robustness_flag?`<span>Rob. <span style="color:${{robC}}">${{robL}}</span></span>`:''}}
      </div>
    </div>
  </div>

  ${{failBanner}}

  <div class="funnel-strip">
    ${{fsStep(0,'E0 Sanity',d.sanity_ok,'sanity','n='+d.n_signals)}}
    <span class="fs-sep">›</span>
    ${{fsStep(1,'E1 Signal',d.step1_ok,'spearman',spVal)}}
    <span class="fs-sep">›</span>
    ${{fsStep(2,'E2 Discrim.',d.step2_ok,'ks',ksVal)}}
    <span class="fs-sep">›</span>
    ${{fsStep(3,'E3 Exploit.',d.step3_ok,'quantile',q3Val)}}
    <span class="fs-sep">·</span>
    ${{fsStep(4,'E4 Rob.',d.robustness_flag==='stable','rolling',d.rolling_std!=null?'std='+d.rolling_std:'—')}}
    <span style="margin-left:auto;font-size:0.67rem;color:var(--hint)">Shuffle ρ=${{f(d.shuffle_corr)}} ${{tt('shuffle')}}</span>
  </div>

  <div id="iview-stat-${{i}}">
  <div class="cg">
    <div class="cp">
      <h3 style="display:flex;align-items:center;gap:6px">
        Distribution Y — Signal vs Flat (KS)
        ${{tt('chart_ks','up')}}
      </h3>
      <div class="cw"><canvas id="cks${{i}}"></canvas></div>
      <div id="interp-ks-${{i}}" class="interp-block"></div>
    </div>
    <div class="cp">
      <h3 style="display:flex;align-items:center;gap:6px">
        Rolling Spearman ρ — Stabilité temporelle
        ${{tt('chart_rolling','up')}}
      </h3>
      <div class="cw"><canvas id="crl${{i}}"></canvas></div>
      <div id="interp-rl-${{i}}" class="interp-block"></div>
    </div>
    <div class="cp">
      <h3 style="display:flex;align-items:center;gap:6px">
        Boxplot Y — Long / Short / Flat (bps × 10⁴)
        ${{tt('chart_boxplot','up')}}
      </h3>
      <div class="cw"><canvas id="cbx${{i}}"></canvas></div>
      <div id="interp-bx-${{i}}" class="interp-block"></div>
    </div>
    <div class="cp">
      <h3 style="display:flex;align-items:center;gap:6px">
        Radar entonnoir — 4 étapes bloquantes
        ${{tt('chart_radar','up')}}
      </h3>
      <div class="cw"><canvas id="crd${{i}}"></canvas></div>
      <div id="interp-rd-${{i}}" class="interp-block"></div>
    </div>
  </div>
  <div id="interp-synth-${{i}}" style="margin-top:14px"></div>
  </div>

  ${{buildInterpSection(d,i)}}`;
}}

// ══════════════════════════════════════════════════════════════
// INTERPRÉTATION DYNAMIQUE — calculs sur données réelles
// ══════════════════════════════════════════════════════════════

// Helper commun
function icard(title, verdict, verdictClass, metrics, insight){{
  const mHtml = metrics.map(m=>`
    <div class="imet">
      <span class="imet-lbl">${{m.lbl}}</span>
      <span>
        <span class="imet-val ${{m.cls||''}}">${{m.val}}</span>
        ${{m.ctx?`<span class="imet-ctx">${{m.ctx}}</span>`:''}}
      </span>
    </div>`).join('');
  return `<div class="icard">
    <div class="icard-header">
      <span class="icard-title">${{title}}</span>
      <span class="ivd ${{verdictClass}}">${{verdict}}</span>
    </div>
    ${{mHtml}}
    <div class="insight">${{insight}}</div>
  </div>`;
}}

function bps(v){{ return v==null?'—':(v*10000).toFixed(2)+' bps'; }}
function bpsCls(v){{ return v==null?'ineu':v>0?'ipos':'ineg'; }}
function pct(v){{ return v==null?'—':(v*100).toFixed(1)+'%'; }}

// ── Interprétation 1 : Distribution KS ───────────────────────
function interpKS(d){{
  const yl = d.avg_y_long, yf = d.avg_y_short, yfl = d.avg_y_flat;
  const ks_p = d.ks_pval, ks_s = d.ks_stat;
  // Qualifier le décalage
  let verdict, vClass, insight;
  const ks_ok = ks_p != null && ks_p < 0.05;
  const ks_strong = ks_p != null && ks_p < 0.01;
  if (ks_strong) {{
    verdict = 'Discrimination forte'; vClass = 'ivd-go';
    insight = `<b>p = ${{ks_p.toFixed(4)}}</b> — les distributions signal et flat sont très différentes. Le signal déplace significativement les rendements. Vérifier si c’est un décalage de la moyenne (edge directionnel) ou des queues (edge de sélection) via le graphique.`;
  }} else if (ks_ok) {{
    verdict = 'Discrimination faible'; vClass = 'ivd-warn';
    insight = `<b>p = ${{ks_p.toFixed(4)}}</b> — les distributions diffèrent mais faiblement. L'edge peut être dans les queues plutôt que dans la moyenne. Un KS significatif + T-test non-significatif = edge de forme, pas directionnel.`;
  }} else {{
    verdict = 'Aucune discrimination'; vClass = 'ivd-ng';
    insight = `<b>p = ${{(ks_p||0).toFixed(4)}}</b> — les distributions signal et flat sont statistiquement identiques. Le signal ne modifie pas le profil des rendements. Vérifier les étapes E1 et E2 pour identifier le blocage.`;
  }}
  const stat_lbl = ks_s != null ? ks_s.toFixed(4) : '—';
  const seuil_txt = ks_ok ? `en dessous du seuil 0.05` : `au-dessus du seuil 0.05`;
  return icard('Distribution KS — signal vs flat', verdict, vClass, [
    {{lbl:'KS stat',   val:stat_lbl, cls: ks_ok?'ipos':'ineg'}},
    {{lbl:'KS p-value',val:ks_p!=null?ks_p.toFixed(4):'—', cls:ks_ok?'ipos':'ineg', ctx:seuil_txt}},
    {{lbl:'T-test p',  val:d.ttest_pval!=null?d.ttest_pval.toFixed(4):'—', cls:d.ttest_go?'ipos':'ineu'}},
    {{lbl:'Wilcoxon p',val:d.wilcoxon_pval!=null?d.wilcoxon_pval.toFixed(4):'—', cls:d.wilcoxon_go?'ipos':'ineu'}},
  ], insight);
}}

// ── Interprétation 2 : Rolling Spearman ──────────────────────
function interpRolling(d){{
  const rc = d.rolling_corr || [];
  const flag = d.robustness_flag;
  const std = d.rolling_std, med = d.rolling_median, sc = d.rolling_sign_ch;
  if (!rc.length) {{
    return icard('Rolling Spearman — stabilité', 'Insuffisant', 'ivd-ng', [
      {{lbl:'Points calculés', val:'< 500 signaux requis', cls:'ineg'}}
    ], `Pas assez de signaux pour calculer la fenêtre glissante de 500 observations. Augmenter l'historique pour débloquer cette analyse.`);
  }}
  let verdict, vClass, insight;
  if (flag === 'stable') {{
    verdict = 'Edge stable'; vClass = 'ivd-go';
    insight = `<b>std = ${{std}}</b> et <b>${{sc}} changements de signe</b> — la corrélation reste cohérente sur toute la période. L'edge est structurel, pas dépendant d'un régime de marché particulier. Bon candidat pour Section 5 sans filtre de régime.`;
  }} else if (flag === 'fragile') {{
    verdict = 'Edge fragile'; vClass = 'ivd-warn';
    insight = `<b>std = ${{std}}</b> — la corrélation oscille fréquemment. L'edge fonctionne sur certaines périodes et échoue sur d'autres. Identifier la variable de régime (tendance, volatilité implicite) qui corrèle avec les zones positives pour construire un filtre de désactivation.`;
  }} else {{
    verdict = 'Non calculé'; vClass = 'ivd-ng';
    insight = `Résultat de robustesse non disponible pour cet actif.`;
  }}
  const pct_pos = rc.length ? (rc.filter(v=>v>0).length/rc.length*100).toFixed(0)+'%' : '—';
  const max_r = rc.length ? Math.max(...rc).toFixed(3) : '—';
  const min_r = rc.length ? Math.min(...rc).toFixed(3) : '—';
  return icard('Rolling Spearman — stabilité temporelle', verdict, vClass, [
    {{lbl:'Médiane rolling ρ', val:med!=null?med.toFixed(3):'—', cls:med>0?'ipos':med<0?'ineg':'ineu', ctx:'objectif ∈ [0.05, 0.10]'}},
    {{lbl:'Std de la courbe',  val:std!=null?std.toFixed(3):'—', cls:std<0.15?'ipos':'iwarn', ctx:`seuil < 0.15`}},
    {{lbl:'% fenêtres > 0',    val:pct_pos, cls:'ineu'}},
    {{lbl:'Changements de signe', val:sc!=null?sc:'—', cls:sc<rc.length*0.4?'ipos':'iwarn', ctx:`seuil < ${{Math.round(rc.length*0.4)}}`}},
  ], insight);
}}

// ── Interprétation 3 : Boxplot ────────────────────────────────
function interpBoxplot(d){{
  const bl = d.box_long, bs = d.box_short, bf = d.box_flat;
  if (!bl || !bl.median) {{
    return icard('Boxplot — Long / Short / Flat', 'Données manquantes', 'ivd-ng', [], `Distributions non calculables — vérifier que n_long et n_short sont suffisants.`);
  }}
  const medL  = bl.median*10000, medS = bs&&bs.median?bs.median*10000:null;
  const medF  = bf&&bf.median?bf.median*10000:0;
  const iqrL  = bl.q3&&bl.q1 ? (bl.q3-bl.q1)*10000 : null;
  const iqrS  = bs&&bs.q3&&bs.q1 ? (bs.q3-bs.q1)*10000 : null;
  const iqrF  = bf&&bf.q3&&bf.q1 ? (bf.q3-bf.q1)*10000 : null;
  const alphaL = medF!=null ? (medL-medF).toFixed(2) : null;
  const alphaS = medF!=null&&medS!=null ? (medS-medF).toFixed(2) : null;

  const thresh = STRATEGY_CTX?.alpha_threshold_bps ?? 5;

  // Verdict boxplot
  const longOk = medL > medF + 2;
  const shortOk = medS != null && medS > medF + 2;
  let verdict, vClass;
  if (longOk && shortOk) {{ verdict='Edge bidirectionnel'; vClass='ivd-go'; }}
  else if (longOk)        {{ verdict='Edge Long uniquement'; vClass='ivd-go'; }}
  else if (shortOk)       {{ verdict='Edge Short uniquement'; vClass='ivd-warn'; }}
  else                    {{ verdict='Edge insuffisant'; vClass='ivd-ng'; }}

  // Qualifier IQR
  const iqrRatioL = iqrF ? (iqrL/iqrF) : null;
  const iqrComment = iqrRatioL > 1.3 ? `IQR Long ${{(iqrRatioL*100-100).toFixed(0)}}% plus large que Flat — signal bruité, SL strict requis.`
    : iqrRatioL < 0.9 ? `IQR Long plus étroit que Flat — signal précis, TP large possible.`
    : `IQR Long comparable à Flat — dispersion normale.`;

  const alphaComment = alphaL
    ? (alphaL > thresh ? `Alpha net <b>${{alphaL}} bps</b> au-dessus du seuil de ${{thresh}} bps.’`
       : alphaL > 0 ? (STRATEGY_CTX?.overrides?.boxplot_weak ?? `Alpha net <b>${{alphaL}} bps</b> — edge présent mais faible (seuil : > ${{thresh}} bps).’`)
       : (STRATEGY_CTX?.overrides?.boxplot_nogo ?? `Alpha net <b>${{alphaL}} bps</b> — en dessous du seuil d’exploitabilité de ${{thresh}} bps.’`))
    : '';

  const shortComment = medS!=null
    ? (medS < medF-1 ? ` Signal Short sous-performe Flat de ${{Math.abs(alphaS).toFixed(2)}} bps — à filtrer.`
       : medS > medF+2 ? ` Signal Short sur-performe Flat de ${{alphaS}} bps — exploitable.`
       : ` Signal Short ≈ Flat — aucun edge directionnel Short détecté.`)
    : '';

  const metrics = [
    {{lbl:'Médiane Long',    val:medL.toFixed(2)+' bps', cls:bpsCls(bl.median), ctx:`alpha net vs Flat : ${{alphaL}} bps`}},
    {{lbl:'Médiane Flat',    val:medF.toFixed(2)+' bps', cls:'ineu', ctx:'référence'}},
  ];
  if (medS!=null) metrics.push({{lbl:'Médiane Short', val:medS.toFixed(2)+' bps', cls:bpsCls(bs.median), ctx:`vs Flat : ${{alphaS}} bps`}});
  if (iqrL!=null) metrics.push({{lbl:'IQR Long / Flat', val:`${{iqrL.toFixed(0)}} / ${{iqrF?iqrF.toFixed(0):'—'}} bps`, cls:iqrRatioL>1.3?'iwarn':'ipos'}});

  return icard('Boxplot — Long / Short / Flat', verdict, vClass, metrics,
    alphaComment + shortComment + ' ' + iqrComment);
}}

// ── Interprétation 4 : Radar ──────────────────────────────────
function interpRadar(d){{
  const steps = [d.sanity_ok, d.step1_ok, d.step2_ok, d.step3_ok];
  const passed = steps.filter(Boolean).length;
  const names = ['Sanity (E0)','Signal (E1)','Discrim. (E2)','Exploit. (E3)'];
  const failed_names = names.filter((_,i)=>!steps[i]);
  const passed_names = names.filter((_,i)=>steps[i]);

  let verdict, vClass, insight;
  if (passed === 4) {{
    verdict = '4/4 — GO complet'; vClass = 'ivd-go';
    const rob = d.robustness_flag;
    insight = `Les 4 étapes bloquantes sont validées.${{'stable'===rob?' Edge également robuste dans le temps (Étape 4 stable).':' fragile'===rob?' ⚠️ Edge fragile dans le temps — ajouter un filtre de régime avant Section 5.':''}}`;
  }} else if (passed === 3) {{
    const missing = failed_names[0]||'';
    verdict = `3/4 — Bloqué à ${{missing}}`; vClass = 'ivd-warn';
    insight = `Signal presque complet — seule l'étape <b>${{missing}}</b> bloque. ${{
      !d.step1_ok?'Aucune corrélation signal→rendement détectée. Revoir la logique d’entrée.’':
      !d.step2_ok?(STRATEGY_CTX?.overrides?.radar_discrimination ?? 'Les distributions Long/Short et Flat ne diffèrent pas statistiquement. Vérifier les conditions de sortie.’'):
      !d.step3_ok?(STRATEGY_CTX?.overrides?.radar_exploitability ?? 'Pas de tendance monotone entre les classes de signal. Revoir les seuils ou l’horizon H.’'):''
    }}`;
  }} else if (passed >= 1) {{
    verdict = `${{passed}}/4 — Edge partiel`; vClass = 'ivd-ng';
    insight = `Étapes validées : <b>${{passed_names.join(', ')||'aucune'}}</b>. Étapes manquantes : <b>${{failed_names.join(', ')}}</b>. Signal statistiquement insuffisant pour aller en Section 5.`;
  }} else {{
    verdict = '0/4 — Aucun signal'; vClass = 'ivd-ng';
    insight = `Aucune étape validée. Vérifier en priorité E0 (volume de signaux) puis E1 (logique de signal).`;
  }}

  const step_items = steps.map((ok,i)=>`
    <div class="imet">
      <span class="imet-lbl">${{names[i]}}</span>
      <span class="imet-val ${{ok?'ipos':'ineg'}}">${{ok?'✅ Validée':'❌ Rejetée'}}</span>
    </div>`).join('');

  return `<div class="icard">
    <div class="icard-header">
      <span class="icard-title">Radar — score entonnoir</span>
      <span class="ivd ${{vClass}}">${{verdict}}</span>
    </div>
    ${{step_items}}
    <div class="insight">${{insight}}</div>
  </div>`;
}}

// ── Synthèse finale ───────────────────────────────────────────
function interpSynthese(d){{
  const bl = d.box_long, bf = d.box_flat;
  const medL  = bl&&bl.median  ? bl.median*10000  : null;
  const medF  = bf&&bf.median  ? bf.median*10000  : 0;
  const iqrL  = bl&&bl.q3&&bl.q1 ? (bl.q3-bl.q1)*10000 : null;
  const iqrF  = bf&&bf.q3&&bf.q1 ? (bf.q3-bf.q1)*10000 : null;
  const alphaL = medL!=null ? (medL - medF) : null;
  const bs = d.box_short;
  const medS = bs&&bs.median ? bs.median*10000 : null;
  const alphaS = medS!=null ? (medS - medF) : null;
  const rc = d.rolling_corr||[];
  const pct_pos = rc.length ? (rc.filter(v=>v>0).length/rc.length*100).toFixed(0) : null;

  // Construire les items de synthèse
  const items = [];

  // Item 1 : décision pipeline
  if (d.is_go) {{
    items.push({{cls:'ipos', text:`<b>Pipeline GO (${{d.tests_passed}}/4 étapes)</b> — l’alpha est statistiquement prouvé. Passer en Section 5.`}});
  }} else {{
    const reason = d.fail_reason || `Rejet à l'Étape ${{d.fail_step}}`;
    items.push({{cls:'ineg', text:`<b>Pipeline NO GO</b> — ${{reason}}. Corriger avant d’aller en Section 5.`}});
  }}

  // Item 2 : alpha net Long
  if (alphaL != null) {{
    const alphaTxt = alphaL > 5 ? `Alpha Long solide : <b>+${{alphaL.toFixed(2)}} bps</b> au-dessus de Flat.`
      : alphaL > 2 ? `Alpha Long faible : <b>+${{alphaL.toFixed(2)}} bps</b> — sous le seuil de 5 bps.`
      : alphaL > 0 ? `Alpha Long marginal : <b>+${{alphaL.toFixed(2)}} bps</b> — à la limite de l'exploitabilité.`
      : `Alpha Long négatif : <b>${{alphaL.toFixed(2)}} bps</b> — le Long sous-performe le marché sans signal.`;
    items.push({{cls: alphaL>5?'ipos':alphaL>2?'iwarn':'ineg', text: alphaTxt}});
  }}

  // Item 3 : Short
  if (alphaS != null) {{
    const shortTxt = alphaS > 5 ? `Signal Short exploitable : <b>+${{alphaS.toFixed(2)}} bps</b> au-dessus de Flat.`
      : alphaS > 0 ? `Signal Short marginal : <b>+${{alphaS.toFixed(2)}} bps</b> — edge insuffisant.`
      : `Signal Short à filtrer : <b>${{alphaS.toFixed(2)}} bps</b> vs Flat — sous-performe sans signal.`;
    items.push({{cls: alphaS>5?'ipos':alphaS>0?'iwarn':'ineg', text: shortTxt}});
  }}

  // Item 4 : dispersion Long
  if (iqrL!=null && iqrF!=null) {{
    const ratio = iqrL/iqrF;
    const dispTxt = ratio > 1.3 ? `Dispersion Long élevée : IQR ${{iqrL.toFixed(0)}} bps (${{(ratio*100-100).toFixed(0)}}% au-dessus de Flat). <b>SL strict indispensable.</b>`
      : ratio < 0.9 ? `Dispersion Long maîtrisée : IQR ${{iqrL.toFixed(0)}} bps — signal précis, TP large possible.`
      : `Dispersion Long normale : IQR ${{iqrL.toFixed(0)}} bps — comparable au marché sans signal.`;
    items.push({{cls: ratio>1.3?'iwarn':'ipos', text: dispTxt}});
  }}

  // Item 5 : robustesse temporelle
  if (rc.length > 0) {{
    const flag = d.robustness_flag;
    const robTxt = flag==='stable' ? `Edge robuste dans le temps (${{pct_pos}}% des fenêtres positives, std = ${{d.rolling_std}}). Pas de filtre de régime requis en priorité.`
      : flag==='fragile' ? `Edge <b>fragile</b> (${{pct_pos}}% des fenêtres positives, std = ${{d.rolling_std}}). Ajouter un filtre de régime pour désactiver le signal en période défavorable.`
      : `Robustesse non calculée.`;
    items.push({{cls: flag==='stable'?'ipos':'iwarn', text: robTxt}});
  }}

  // Item 6 : shuffle
  if (d.shuffle_ok === false) {{
    items.push({{cls:'ineg', text:`<b>⚠️ Shuffle élevé (ρ = ${{d.shuffle_corr}})</b> — biais potentiel dans la construction de X ou Y. Vérifier <code>build_payload()</code> avant de conclure.`}});
  }}

  const itemsHtml = items.map((it,idx)=>`
    <div class="synth-item">
      <span class="synth-num">${{idx+1}}</span>
      <span class="synth-text ${{it.cls}}">${{it.text}}</span>
    </div>`).join('');

  const overall = d.is_go
    ? `<span class="vd vd-go">GO — prêt pour Section 5</span>`
    : `<span class="vd vd-ng">NO GO — retravailler le signal</span>`;

  return `<div class="synth-block" style="margin-top:1rem">
    <div class="synth-title">
      <span>Synthèse & recommandations</span>
      ${{overall}}
    </div>
    ${{itemsHtml}}
  </div>`;
}}

function buildInterpSection(d,i){{
  return `<div style="margin-top:14px;border-top:1px solid var(--border);padding-top:14px">
    <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--hint);padding-left:8px;border-left:2px solid var(--purple);margin-bottom:10px">Analyse détaillée</div>
    <div class="interp-grid">
      ${{interpKS(d)}}
      ${{interpRolling(d)}}
      ${{interpBoxplot(d)}}
      ${{interpRadar(d)}}
    </div>
    ${{interpSynthese(d)}}
  </div>`;
}}

function renderPanel(d,i){{
  // V2 — Distribution KS
  const ks=document.getElementById('cks'+i);
  if(ks&&d.hist_signal&&d.hist_signal.labels.length){{
    new Chart(ks,{{type:'bar',
      data:{{labels:d.hist_signal.labels,datasets:[
        {{label:'Signal',data:d.hist_signal.values,backgroundColor:'rgba(79,156,249,0.5)',borderColor:C.blue,borderWidth:.5,barPercentage:1,categoryPercentage:1}},
        {{label:'Flat',  data:d.hist_flat.values,  backgroundColor:'rgba(107,114,143,0.25)',borderColor:C.grid,borderWidth:.5,barPercentage:1,categoryPercentage:1}}
      ]}},
      options:{{responsive:true,maintainAspectRatio:false,animation:false,
        plugins:{{legend:{{display:true,labels:{{boxWidth:9,padding:10}}}}}},
        scales:{{
          x:{{grid:{{color:C.grid}},ticks:{{maxTicksLimit:7,callback:v=>v}}}},
          y:{{grid:{{color:C.grid}},ticks:{{maxTicksLimit:5}}}}
        }}
      }}
    }});
  }}

  // V3 — Rolling Spearman
  const rl=document.getElementById('crl'+i);
  if(rl&&d.rolling_idx&&d.rolling_idx.length>2){{
    new Chart(rl,{{type:'line',
      data:{{labels:d.rolling_idx,datasets:[
        {{label:'ρ rolling',data:d.rolling_corr,borderColor:C.purple,backgroundColor:'rgba(155,127,244,.08)',borderWidth:1.5,pointRadius:0,fill:true,tension:.3}},
        {{label:'zéro',data:Array(d.rolling_idx.length).fill(0),borderColor:'rgba(255,255,255,.12)',borderWidth:1,borderDash:[5,4],pointRadius:0}}
      ]}},
      options:{{responsive:true,maintainAspectRatio:false,animation:false,
        plugins:{{legend:{{display:false}}}},
        scales:{{
          x:{{grid:{{color:C.grid}},ticks:{{display:false}}}},
          y:{{grid:{{color:C.grid}},ticks:{{maxTicksLimit:5}}}}
        }}
      }}
    }});
  }}

  // V4 — Boxplot (floating bar + scatter)
  const bx=document.getElementById('cbx'+i);
  if(bx){{
    const groups=[
      {{l:'Long', s:d.box_long,  c:C.go}},
      {{l:'Short',s:d.box_short, c:C.ng}},
      {{l:'Flat', s:d.box_flat,  c:'#6b728f'}},
    ];
    const ds=[];
    groups.forEach(g=>{{
      if(!g.s||!g.s.q1) return;
      const sc=g.s;
      ds.push({{type:'bar',label:g.l,data:[{{x:g.l,y:[sc.q1*10000,sc.q3*10000]}}],
        backgroundColor:g.c+'44',borderColor:g.c,borderWidth:1.5,borderSkipped:false,barThickness:30}});
      ds.push({{type:'scatter',label:'_',
        data:[{{x:g.l,y:sc.median*10000}}],
        backgroundColor:g.c,pointRadius:16,pointStyle:'line',pointBorderWidth:2.5,pointBorderColor:g.c,showLine:false}});
      ds.push({{type:'scatter',label:'__',
        data:[{{x:g.l,y:sc.whisker_hi*10000}},{{x:g.l,y:sc.whisker_lo*10000}}],
        backgroundColor:g.c,pointRadius:4,showLine:false}});
    }});
    new Chart(bx,{{data:{{datasets:ds}},options:{{responsive:true,maintainAspectRatio:false,animation:false,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{type:'category',grid:{{color:C.grid}}}},
        y:{{grid:{{color:C.grid}},ticks:{{maxTicksLimit:5}},
           title:{{display:true,text:'bps (×10⁴)',color:'#6b728f',font:{{size:10}}}}}}
      }}
    }}}});
  }}

  // V5 — Radar
  const rd=document.getElementById('crd'+i);
  if(rd){{
    new Chart(rd,{{type:'radar',
      data:{{
        labels:['E0 Sanity','E1 Signal','E2 Discrim.','E3 Exploit.'],
        datasets:[{{
          label:d.asset,
          data:[d.sanity_ok?1:0,d.step1_ok?1:0,d.step2_ok?1:0,d.step3_ok?1:0],
          backgroundColor:d.is_go?'rgba(0,201,122,.15)':'rgba(240,69,90,.12)',
          borderColor:d.is_go?C.go:C.ng,borderWidth:2,
          pointBackgroundColor:d.is_go?C.go:C.ng,pointRadius:5,
        }}]
      }},
      options:{{responsive:true,maintainAspectRatio:false,animation:false,
        plugins:{{legend:{{display:false}}}},
        scales:{{r:{{
          min:0,max:1,ticks:{{display:false,stepSize:.5}},
          grid:{{color:'rgba(255,255,255,0.08)'}},
          angleLines:{{color:'rgba(255,255,255,0.06)'}},
          pointLabels:{{font:{{size:11}},color:'#6b728f'}}
        }}}}
      }}
    }});
  }}

  // ── Interprétations dynamiques ──────────────────────────────────────────
  const n4=v=>v==null?null:+(v*10000).toFixed(2);
  const bps=v=>v==null?'—':(v>=0?'+':'')+v.toFixed(2)+' bps';
  const pct=v=>v==null?'—':+(v*100).toFixed(1)+'%';
  const sign=v=>v>0?'pos':v<0?'neg':'neu';

  // ── Helpers HTML ──
  function irow(label,val,cls,note){{
    return`<div class="interp-row"><span class="ir-label">${{label}}</span><span class="ir-val ${{cls}}">${{val}}</span><span class="ir-note">${{note||''}}</span></div>`;
  }}
  function iverdict(text,type){{
    // Si l'actif est GO global, les verdicts partiels négatifs
    // passent en warn (orange) pour ne pas créer de confusion avec la décision finale
    const effective = (d.is_go && type==='ng') ? 'warn' : type;
    return`<div class="interp-verdict iv-${{effective}}">${{text}}</div>`;
  }}
  function ibar(label,val,max,color){{
    const w=Math.min(100,Math.round(Math.abs(val)/max*100));
    return`<div class="bar-mini"><span style="min-width:42px">${{label}}</span><div class="bar-mini-bg"><div class="bar-mini-fill" style="width:${{w}}%;background:${{color}}"></div></div><span style="min-width:38px;text-align:right;font-family:var(--mono);font-size:0.68rem">${{bps(val)}}</span></div>`;
  }}

  // ── Interp 1 — Distribution KS ─────────────────────────────────────────
  (function(){{
    const el=document.getElementById('interp-ks-'+i);
    if(!el) return;
    const ks_p=d.ks_pval, ks_s=d.ks_stat;
    if(ks_p==null){{el.innerHTML='<div style="font-size:0.7rem;color:var(--muted)">Données insuffisantes pour l’analyse KS.</div>';return;}}
    const avgL=n4(d.avg_y_long), avgS=n4(d.avg_y_short), avgF=n4(d.avg_y_flat||0);
    const type= ks_p<0.01?'go': ks_p<0.05?'warn':'ng';
    const verdict= ks_p<0.01?'Distributions très différentes': ks_p<0.05?'Différence significative':'Distributions similaires';
    el.innerHTML=
      iverdict(verdict, type)+
      irow('KS stat',ks_s.toFixed(4), ks_s>0.1?'pos':'neu', ks_s>0.1?'Décalage notable':'Décalage faible')+
      irow('p-value',ks_p.toFixed(4), ks_p<0.05?'pos':'neg', ks_p<0.05?'< 0.05 → distributions statistiquement différentes':'≥ 0.05 → distributions non discernables')+
      `<div class="interp-insight">${{
        ks_p<0.01 ? `<b>Séparation forte</b> — la présence du signal modifie significativement la distribution des rendements. Edge structurel détecté.` :
        ks_p<0.05 ? `<b>Séparation modérée</b> — le signal déplace partiellement la distribution. Edge présent mais diffus — compléter avec T-test et Wilcoxon.` :
        `<b>Aucune séparation</b> — les rendements avec et sans signal suivent la même distribution. Revoir la logique de signal ou allonger l’horizon H.`
      }}</div>`;
  }})();

  // ── Interp 2 — Rolling Spearman ────────────────────────────────────────
  (function(){{
    const el=document.getElementById('interp-rl-'+i);
    if(!el) return;
    const rc=d.rolling_corr, std=d.rolling_std, med=d.rolling_median, sc=d.rolling_sign_ch;
    if(!rc||rc.length<3){{el.innerHTML='<div style="font-size:0.7rem;color:var(--muted)">Historique insuffisant pour la rolling Spearman (min 500 signaux).</div>';return;}}
    const flag=d.robustness_flag;
    const type=flag==='stable'?'go':flag==='fragile'?'warn':'neu';
    const verdict=flag==='stable'?'Edge stable dans le temps':flag==='fragile'?'Edge instable — régime-dépendant':'Stabilité non calculée';
    const pct_pos=rc.filter(v=>v>0).length/rc.length*100;
    el.innerHTML=
      iverdict(verdict, type)+
      irow('Médiane ρ rolling', med!=null?med.toFixed(4):'—', med>0.02?'pos':med<-0.02?'neg':'neu', med>0.02?'Edge positif en médiane':med<-0.02?'Edge inversé en médiane':'Edge nul en médiane')+
      irow('Std de la courbe', std!=null?std.toFixed(4):'—', std!=null&&std<0.15?'pos':'neg', std!=null&&std<0.15?'< 0.15 → stable':'≥ 0.15 → instable')+
      irow('Fenêtres positives', pct_pos.toFixed(1)+'%', pct_pos>55?'pos':pct_pos<40?'neg':'neu', pct_pos>55?'Majoritairement en edge':pct_pos<40?'Majoritairement sans edge':'Edge intermittent')+
      irow('Changements de signe', sc!=null?sc:'—', sc!=null&&sc<rc.length*0.4?'pos':'neg', sc!=null&&sc<rc.length*0.4?'< 40% des fenêtres':'≥ 40% — oscillations fréquentes')+
      `<div class="interp-insight">${{
        flag==='stable' ? `<b>Edge robuste</b> — la corrélation reste cohérente sur l’ensemble de la période. Comportement prévisible en Walk-Forward. Bon candidat pour Section 5.` :
        flag==='fragile' ? `<b>Edge régime-dépendant</b> — la corrélation oscille. Identifier la variable de régime (trend, volatilité, spread) corrélant avec les zones positives pour construire un filtre de désactivation.` :
        `<b>Historique trop court</b> pour évaluer la stabilité temporelle. Augmenter la période de données.`
      }}</div>`;
  }})();

  // ── Interp 3 — Boxplot Long/Short/Flat ─────────────────────────────────
  (function(){{
    const el=document.getElementById('interp-bx-'+i);
    if(!el) return;
    const bL=d.box_long, bS=d.box_short, bF=d.box_flat;
    if(!bL||!bF){{el.innerHTML='<div style="font-size:0.7rem;color:var(--muted)">Données insuffisantes pour l’analyse boxplot.</div>';return;}}
    const mL=n4(bL.median), mS=bS?n4(bS.median):null, mF=n4(bF.median);
    const iqrL=n4(bL.q3-bL.q1), iqrS=bS?n4(bS.q3-bS.q1):null, iqrF=n4(bF.q3-bF.q1);
    const alphaL=(mL!=null&&mF!=null)?+(mL-mF).toFixed(2):null;
    const alphaS=(mS!=null&&mF!=null)?+(mS-mF).toFixed(2):null;
    const iqrRatio=iqrF>0?(iqrL/iqrF).toFixed(2):null;

    const type= alphaL!=null&&alphaL>5?'go': alphaL!=null&&alphaL>0?'warn':'ng';
    const verdict= alphaL!=null&&alphaL>5?'Edge Long exploitable': alphaL!=null&&alphaL>0?'Edge Long faible':'Aucun edge directionnel';
    const maxBps=Math.max(Math.abs(mL||0),Math.abs(mS||0),Math.abs(mF||0),1);

    el.innerHTML=
      iverdict(verdict, type)+
      ibar('Long', mL||0, maxBps, C.go)+
      (mS!=null?ibar('Short', mS, maxBps, C.ng):'')+
      ibar('Flat', mF||0, maxBps, '#6b728f')+
      `<div style="margin-top:8px">` +
      (alphaL!=null?irow('Alpha net Long-Flat', bps(alphaL), sign(alphaL), alphaL>5?'> 5 bps seuil exploitable':alphaL>0?'Positif mais < 5 bps seuil':'Négatif — Long sous-performe Flat'):'') +
      (alphaS!=null?irow('Alpha net Short-Flat', bps(alphaS), sign(alphaS), alphaS>0?'Short sur-performe Flat':'Short sous-performe Flat'):'') +
      (iqrRatio!=null?irow('IQR Long / IQR Flat', iqrRatio+'×', parseFloat(iqrRatio)<1.3?'pos':'neg', parseFloat(iqrRatio)<1.3?'Dispersion comparable à Flat':'Long plus dispersé que Flat — signal bruité'):'') +
      `</div>` +
      `<div class="interp-insight">${{
        alphaL==null ? `Pas assez de signaux Long pour calculer l’alpha.` :
        alphaL>5 ? `<b>Edge exploitable</b> — alpha net Long de +${{alphaL}} bps au-dessus de Flat. ${{alphaS!=null&&alphaS>5?' Edge Short également présent — stratégie bidirectionnelle viable.':alphaS!=null&&alphaS<0?' Filtrer les Short — ils sous-performent.'  :''}}` :
        alphaL>0 ? `<b>Alpha insuffisant</b> — +${{alphaL}} bps vs seuil de 5 bps. L'IQR Large (${{iqrL}} bps) noie le signal. Renforcer les conditions d’entrée pour réduire la dispersion.` :
        `<b>Long sous-performe Flat</b> — median Long (${{mL}} bps) < Flat (${{mF}} bps). Signal inversé ou logique d’entrée incorrecte.`
      }}</div>`;
  }})();

  // ── Interp 4 — Radar ───────────────────────────────────────────────────
  (function(){{
    const el=document.getElementById('interp-rd-'+i);
    if(!el) return;
    const steps=[d.sanity_ok,d.step1_ok,d.step2_ok,d.step3_ok];
    const passed=steps.filter(Boolean).length;
    const labels=['Sanity','Signal','Discrimination','Exploitabilité'];
    const missing=labels.filter((_,j)=>!steps[j]);
    const type=passed===4?'go':passed>=2?'warn':'ng';
    const verdict=passed===4?'Pipeline complet — 4/4':passed===3?'3/4 — un axe manquant':passed===2?'2/4 — edge partiel':'0-1/4 — pas d’alpha';

    const diagMap={{
      'Signal': 'Aucune relation détectée entre X et Y. Revoir la logique de signal de A à Z.',
      'Discrimination': 'Le signal existe mais ne sépare pas les bons et mauvais trades. Revoir les conditions de sortie ou l’horizon H.',
      'Exploitabilité': 'Edge statistique prouvé mais pas encore tradable. Ajuster les seuils d’entrée ou l’horizon H.',
      'Sanity': 'Données corrompues ou historique trop court. Corriger les données avant tout.'
    }};

    const rows=labels.map((lbl,j)=>`<div class="interp-row">
      <span class="ir-label">${{lbl}}</span>
      <span class="ir-val ${{steps[j]?'pos':'neg'}}">${{steps[j]?'✅ Validé':'❌ Rejeté'}}</span>
      <span class="ir-note">${{!steps[j]?diagMap[lbl]||'':''}}</span>
    </div>`).join('');

    el.innerHTML=
      iverdict(verdict, type)+
      rows+
      `<div class="interp-insight">${{
        passed===4 ? `<b>Entonnoir complet</b> — les 4 étapes bloquantes sont validées. L'alpha est statistiquement prouvé et exploitable. Passer en Section 5.` :
        missing.length===1 ? `<b>Un axe manquant : ${{missing[0]}}</b> — ${{diagMap[missing[0]]||''}}` :
        `<b>Axes manquants : ${{missing.join(', ')}}</b> — corriger dans cet ordre : ${{missing.map(m=>diagMap[m]).filter(Boolean).join(' Puis : ')}}`
      }}</div>`;
  }})();

}}
// Render premier actif
document.querySelectorAll('.apanel')[0].dataset.r='1';
renderPanel(D[0],0);

// Attacher les tooltips aux en-têtes de la heatmap
const thMap = [
  ['th-sanity','sanity'],['th-spearman','spearman'],['th-mi','mi'],
  ['th-ks','ks'],['th-ttest','ttest'],['th-wilcoxon','wilcoxon'],
  ['th-quantile','quantile'],['th-rolling','rolling'],['th-shuffle','shuffle']
];
thMap.forEach(([id,key])=>{{
  const el=document.getElementById(id);
  if(!el||!TIPS[key]) return;
  const t=TIPS[key];
  const wrap=document.createElement('span');
  wrap.className='tip-wrap';
  wrap.style.position='relative';
  wrap.innerHTML=`${{el.textContent}}<i class="tip-icon" style="margin-left:4px">i</i>
    <div class="tip-box" style="left:0;top:calc(100% + 8px);transform:none;">
      <div class="tb-title">${{t.title}}</div>
      <div class="tip-section"><div class="tip-label">Définition</div><p class="tip-def">${{t.def}}</p></div>
      <div class="tip-section"><div class="tip-label">Seuils</div>${{t.seuils}}</div>
    </div>`;
  el.textContent='';
  el.appendChild(wrap);
}});
</script>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(HTML)


    if open_browser:
        webbrowser.open(f"file://{os.path.abspath(filepath)}")
    return filepath


# ============================================================
# RAPPORT CONSOLE
# ============================================================
