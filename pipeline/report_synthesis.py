import os
import json
import numpy as np

OUTPUT_DIR = "Reports"

def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return -999.0

def generate_synthesis_report(
    results_by_payload: dict[str, list[dict]],
    output_dir: str = OUTPUT_DIR,
    open_browser: bool = True,
) -> str:
    """
    Génère le rapport Section4_Synthesis.html avec 4 blocs d'analyse,
    sur la base des 8 runs du SweepLQ.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "Section4_Synthesis.html")

    # Extraire les assets du run D_Full_h8 qui est le plus central
    master_key = "D_Full_h8"
    if master_key not in results_by_payload:
        print(f"⚠️ Clé {master_key} manquante dans results_by_payload. Runs existants : {list(results_by_payload.keys())}")
        return ""

    assets = sorted([r.get("asset") for r in results_by_payload[master_key] if r.get("asset")])
    
    # Prétraitement pour construire rapidement les données par vue/bloc
    def get_run_val(run_key, asset_name, field, default=None):
        if run_key not in results_by_payload: return default
        for r in results_by_payload[run_key]:
            if r.get("asset") == asset_name:
                return r.get(field, default)
        return default

    html_rows = []
    html_verdict_blocks = []
    html_asset_blocks = []

    for asset in assets:
        # Extractions des décisions
        d_D4 = get_run_val("D_Full_h4", asset, "decision", "NO GO")
        d_D8 = get_run_val("D_Full_h8", asset, "decision", "NO GO")
        d_D16 = get_run_val("D_Full_h16", asset, "decision", "NO GO")
        d_A8 = get_run_val("A_Bias_h8", asset, "decision", "NO GO")
        d_B8 = get_run_val("B_Engulf_h8", asset, "decision", "NO GO")
        d_C8 = get_run_val("C_Engulf_Bias_h8", asset, "decision", "NO GO")
        
        # Extractions des Spearman (pour pnl_detrended proxy)
        sp_D8 = _safe_float(get_run_val("D_Full_h8", asset, "spearman_corr", -999.0))
        sp_A8 = _safe_float(get_run_val("A_Bias_h8", asset, "spearman_corr", -999.0))
        sp_D4 = _safe_float(get_run_val("D_Full_h4", asset, "spearman_corr", -999.0))
        sp_D16 = _safe_float(get_run_val("D_Full_h16", asset, "spearman_corr", -999.0))

        # ---- BLOC 1: Verdict global ----
        # GO si Payload D validé sur h=4 ET h=8 ET Spearman(D_h8) > Spearman(A_h8)
        is_global_go = (d_D4 == "GO" and d_D8 == "GO" and sp_D8 > sp_A8)
        
        reason = ""
        if is_global_go:
            reason = "Edge complet validé multi-horizons (h=4, h=8) et valeur ajoutée PnL prouvée."
            v_cls, v_lbl = "go", "GO"
        else:
            v_cls, v_lbl = "ng", "NO GO"
            if d_D4 != "GO" or d_D8 != "GO":
                reason = "Payload D (Sweep complet) non validé sur h=4 et h=8."
            elif sp_D8 <= sp_A8:
                reason = "Le Sweep n’ajoute aucune performance statistique par rapport au Biais seul."

        html_verdict_blocks.append(
            f'<div class="banner {v_cls}">'
            f'<div class="btitle">{asset} &mdash; {v_lbl}</div>'
            f'<div class="bsub">{reason}</div>'
            f'</div>'
        )

        # ---- BLOC 2: Matrice de décision ----
        cols = ["A_Bias_h4", "A_Bias_h8", "A_Bias_h16", "B_Engulf_h8", "C_Engulf_Bias_h8", "D_Full_h4", "D_Full_h8", "D_Full_h16"]
        tds = f"<td><strong>{asset}</strong></td>"
        for c in cols:
            dec = get_run_val(c, asset, "decision", "NO GO")
            ok = get_run_val(c, asset, "tests_passed", 0)
            wr = get_run_val(c, asset, "win_rate_long")
            wr_str = f"{round(wr*100, 1)}%" if wr is not None else "—"
            
            bdg = "bdg-go" if dec == "GO" else "bdg-ng"
            tds += f'<td><span class="bdg {bdg}">{dec}</span><br><span style="font-size:0.65rem;color:var(--muted)">{ok}/4 | WR: {wr_str}</span></td>'
        
        html_rows.append(f"<tr>{tds}</tr>")

        # ---- BLOC 3: ANALYSE PAR ASSET ----
        global_bdg_cls = "bdg-go" if is_global_go else "bdg-ng"
        global_bdg_lbl = "GO" if is_global_go else "NO GO"

        def _get_sig_row(label, p_key):
            d = get_run_val(p_key, asset, "decision", "NO GO")
            d_bdg = "bdg-go" if d == "GO" else "bdg-ng"
            
            sp = _safe_float(get_run_val(p_key, asset, "spearman_corr", -999.0))
            pval = _safe_float(get_run_val(p_key, asset, "spearman_pval", -999.0))
            
            sp_str = f"{sp:.3f}" if sp != -999.0 else "—"
            if pval == -999.0:
                p_bdg, p_icon = "", ""
            elif pval < 0.05:
                p_bdg = "c-go"; p_icon = "p&lt;0.05"
            elif pval < 0.10:
                p_bdg = "c-amber"; p_icon = "p&lt;0.10"
            else:
                p_bdg = "c-ng"; p_icon = "p&ge;0.10"
                
            p_html = f"&rho;={sp_str} <span class='{p_bdg}'>({p_icon})</span>" if sp != -999.0 else "—"
            
            step3 = get_run_val(p_key, asset, "step3_ok", False)
            q_diff = get_run_val(p_key, asset, "q1_vs_q5_diff", 0.0)
            q_mono = get_run_val(p_key, asset, "q_mono", False)
            
            expl_icon = "✅" if step3 else "❌"
            mono_str = "monotone" if q_mono else "non monotone"
            expl_title = f"{q_diff:.2f} bps | {mono_str}"

            def _fmt_wr_side(prefix):
                wr = get_run_val(p_key, asset, f"win_rate_{prefix}")
                avg_y = get_run_val(p_key, asset, f"avg_y_{prefix}")
                n = get_run_val(p_key, asset, f"n_{prefix}", 0)
                wr_title = f"{avg_y * 10000:.1f} bps | n={n}" if avg_y is not None else f"N/A bps | n={n}"
                if wr is None or n == 0:
                    return "<span style='color:var(--muted)'>&mdash;</span>"
                if wr >= 0.52:
                    return f"<span class='c-go' title='{wr_title}'>{wr*100:.1f}%</span>"
                elif wr >= 0.48:
                    return f"<span style='color:var(--muted)' title='{wr_title}'>{wr*100:.1f}%</span>"
                else:
                    return f"<span class='c-ng' title='{wr_title}'>{wr*100:.1f}%</span>"

            wr_l = _fmt_wr_side("long")
            wr_s = _fmt_wr_side("short")
            
            return f"<tr><td>{label}</td><td>h=8</td><td><span class='bdg {d_bdg}'>{d}</span></td><td>{p_html}</td><td title='{expl_title}'>{expl_icon}</td><td>{wr_l}</td><td>{wr_s}</td></tr>"

        sig_rows = [
            _get_sig_row("A &mdash; Biais seul", "A_Bias_h8"),
            _get_sig_row("B &mdash; Engulfing seul", "B_Engulf_h8"),
            _get_sig_row("C &mdash; Engulf + Biais", "C_Engulf_Bias_h8"),
            _get_sig_row("D &mdash; Signal complet", "D_Full_h8")
        ]

        def _get_rob_row(h_label, p_key):
            sp = _safe_float(get_run_val(p_key, asset, "spearman_corr", -999.0))
            pval = _safe_float(get_run_val(p_key, asset, "spearman_pval", -999.0))
            
            sp_str = f"&rho;={sp:.3f}" if sp != -999.0 else "&rho;=N/A"
            if pval == -999.0:
                p_bdg, p_icon = "", ""
            elif pval < 0.05:
                p_bdg = "c-go"; p_icon = "p&lt;0.05 ✅"
            elif pval < 0.10:
                p_bdg = "c-amber"; p_icon = "p&lt;0.10 ⚠️"
            else:
                p_bdg = "c-ng"; p_icon = "p&ge;0.10 ❌"
                
            p_html = f"{sp_str} <span class='{p_bdg}'>{p_icon}</span>" if sp != -999.0 else "—"
            
            step3 = get_run_val(p_key, asset, "step3_ok", False)
            q_diff = get_run_val(p_key, asset, "q1_vs_q5_diff", 0.0)
            q_mono = get_run_val(p_key, asset, "q_mono", False)
            expl_icon = "✅" if step3 else "❌"
            expl_title = f"{q_diff:.2f} bps | {'monotone' if q_mono else 'non monotone'}"
            
            rob_flag = get_run_val(p_key, asset, "robustness_flag")
            r_std = get_run_val(p_key, asset, "rolling_std")
            r_sc = get_run_val(p_key, asset, "rolling_sign_ch")
            r_corr = get_run_val(p_key, asset, "rolling_corr") or []
            pos_win = len([x for x in r_corr if x is not None and x > 0])
            tot_win = len(r_corr)
            pct_win = int(pos_win/tot_win*100) if tot_win > 0 else 0

            r_std_str = f"{r_std:.3f}" if r_std is not None else "N/A"
            r_sc_str = str(r_sc) if r_sc is not None else "N/A"
            rob_title = f"std: {r_std_str} | {r_sc_str} chg | {pct_win}% fenêtres positives"
            
            if rob_flag == "stable":
                rob_html = f"<span class='c-go' title='{rob_title}'>Stable ✅</span>"
            elif rob_flag == "fragile":
                rob_html = f"<span class='c-amber' title='{rob_title}'>Fragile ⚠️</span>"
            else:
                rob_html = f"<span style='color:var(--muted)' title='{rob_title}'>N/A</span>"

            def _fmt_wr_side(prefix):
                wr = get_run_val(p_key, asset, f"win_rate_{prefix}")
                avg_y = get_run_val(p_key, asset, f"avg_y_{prefix}")
                n = get_run_val(p_key, asset, f"n_{prefix}", 0)
                wr_title = f"{avg_y * 10000:.1f} bps | n={n}" if avg_y is not None else f"N/A bps | n={n}"
                if wr is None or n == 0:
                    return "<span style='color:var(--muted)'>&mdash;</span>"
                if wr >= 0.52:
                    return f"<span class='c-go' title='{wr_title}'>{wr*100:.1f}%</span>"
                elif wr >= 0.48:
                    return f"<span style='color:var(--muted)' title='{wr_title}'>{wr*100:.1f}%</span>"
                else:
                    return f"<span class='c-ng' title='{wr_title}'>{wr*100:.1f}%</span>"

            wr_l = _fmt_wr_side("long")
            wr_s = _fmt_wr_side("short")
                
            return f"<tr><td>{h_label}</td><td>{p_html}</td><td title='{expl_title}'>{expl_icon}</td><td>{rob_html}</td><td>{wr_l}</td><td>{wr_s}</td></tr>"

        rob_rows = [
            _get_rob_row("h=4 (1h)", "D_Full_h4"),
            _get_rob_row("h=8 (2h)", "D_Full_h8"),
            _get_rob_row("h=16 (4h)", "D_Full_h16")
        ]

        if d_D8 == "GO" and sp_D8 > sp_A8:
            src_edge = "Le Sweep ajoute de l’alpha au biais (D bat A sur Spearman IC)"
            cas_detect = src_edge
        elif d_A8 == "GO" and d_D8 != "GO":
            src_edge = "Le biais seul explique la performance &mdash; le Sweep n’ajoute rien.<br>Revoir les conditions d’entr&eacute;e ou le pool LQ."
            cas_detect = "Biais seul explique perf"
        elif d_B8 == "GO" and d_C8 != "GO":
            src_edge = "Engulfing valide sans filtre &mdash; le filtre MTF d&eacute;grade le signal.<br>Revoir la logique MTF."
            cas_detect = "Filtre MTF d&eacute;grade signal"
        elif d_C8 == "GO" and d_D8 != "GO":
            src_edge = "Signal filtr&eacute; valide &mdash; le pool LQ n’ajoute rien.<br>Tester sans condition de sweep."
            cas_detect = "Signal filtr&eacute; valide sans LQ"
        else:
            src_edge = "Aucune couche de signal ne g&eacute;n&egrave;re d’edge sur cet asset."
            cas_detect = "Aucun edge d&eacute;tect&eacute;"

        def _is_valid_hor(p_key):
            pval = _safe_float(get_run_val(p_key, asset, "spearman_pval", -999.0))
            step3 = get_run_val(p_key, asset, "step3_ok", False)
            rob_flag = get_run_val(p_key, asset, "robustness_flag")
            return (pval != -999.0 and pval < 0.05) and step3 and (rob_flag != "fragile")

        h4_val = _is_valid_hor("D_Full_h4")
        h8_val = _is_valid_hor("D_Full_h8")
        h16_val = _is_valid_hor("D_Full_h16")
        
        hor_target = ""
        if h4_val and h8_val and h16_val:
            hor_rec = "Edge robuste tous horizons &mdash; optimal : h=4 (1h)"
            hor_target = "h=4 (1h)"
        elif h4_val and h8_val and not h16_val:
            hor_rec = "Edge intraday court &mdash; horizon max recommand&eacute; : h=8 (2h)"
            hor_target = "h=8 (2h)"
        elif not h4_val and h8_val and not h16_val:
            hor_rec = "Edge uniquement &agrave; 2h &mdash; tester h=6 pour affiner"
            hor_target = "h=6/8 (2h)"
        elif not h4_val and not h8_val and h16_val:
            hor_rec = "Signal trop lent &mdash; investiguer avant Section 5"
            hor_target = "h=16 (4h)"
        elif h4_val and not h8_val and not h16_val:
            hor_rec = "Edge uniquement &agrave; 1h &mdash; tr&egrave;s court, spread critique"
            hor_target = "h=4 (1h)"
        else:
            hor_rec = "Aucun horizon valid&eacute; sur Payload D"
            hor_target = "N/A"

        vigil_items = []
        if d_B8 == "NO GO":
            vigil_items.append("Engulfing seul sans valeur &mdash; filtre MTF indispensable")
        if get_run_val("D_Full_h8", asset, "robustness_flag") == "fragile":
            vigil_items.append("Edge r&eacute;gime-d&eacute;pendant &mdash; invoquer quant-regime avant Section 5")
        
        wr_D8_long = get_run_val("D_Full_h8", asset, "win_rate_long")
        wr_D8_short = get_run_val("D_Full_h8", asset, "win_rate_short")
        
        if (wr_D8_short is not None and wr_D8_short < 0.48) and (wr_D8_long is not None and wr_D8_long >= 0.48):
            vigil_items.append(f"WR Short insuffisant ({wr_D8_short*100:.1f}%) &mdash; strat&eacute;gie asym&eacute;trique. Envisager de filtrer les entr&eacute;es Short sur cet asset.")
        elif (wr_D8_long is not None and wr_D8_long < 0.48) and (wr_D8_short is not None and wr_D8_short < 0.48):
            vigil_items.append(f"Win rate insuffisant des deux c&ocirc;t&eacute;s (L:{wr_D8_long*100:.1f}% S:{wr_D8_short*100:.1f}%) &mdash; aucun edge directionnel. Exclure cet asset.")
        elif wr_D8_long is not None and wr_D8_long < 0.48:
            vigil_items.append(f"Win rate Long insuffisant ({wr_D8_long*100:.1f}%) &mdash; revoir conditions d’entr&eacute;e")

        if get_run_val("D_Full_h8", asset, "shuffle_ok", True) == False:
            vigil_items.append("Shuffle control &eacute;chou&eacute; &mdash; v&eacute;rifier le lookahead dans build_payload")
        n_sig_D8 = get_run_val("D_Full_h8", asset, "n_signals", 0)
        if n_sig_D8 > 0 and n_sig_D8 < 150:
            vigil_items.append(f"Volume de signaux faible (N={n_sig_D8}) &mdash; r&eacute;sultats peu stables")
            
        vigil_html = ""
        if vigil_items:
            v_lis = "".join([f"<li>{v}</li>" for v in vigil_items])
            vigil_html = f"<div class='c-title' style='margin-top:12px;'>⚠️ Points de vigilance</div><ul style='margin-left:20px;font-size:0.85rem;color:var(--amber)'>{v_lis}</ul>"

        if is_global_go:
            action_txt = f"<span class='c-go'>Passer Section 5 sur {asset} &mdash; horizon cible : {hor_target}</span>"
        else:
            action_txt = f"<span class='c-ng'>Exclure {asset} &mdash; {cas_detect}</span>"

        asset_block = f'''
        <div class="asset-card">
            <div class="a-header">
                <strong>{asset}</strong> <span class="bdg {global_bdg_cls}">{global_bdg_lbl}</span>
            </div>
            
            <div class="a-section">SECTION 1 &mdash; DIAGNOSTIC SIGNAL (comparaison A/B/C/D)</div>
            <div class="a-tbl-wrap">
                <table class="a-table">
                    <thead><tr><th>Payload</th><th>Horizon ref</th><th>D&eacute;cision</th><th>&rho; Spearman</th><th>Exploitable</th><th>WR Long</th><th>WR Short</th></tr></thead>
                    <tbody>{"".join(sig_rows)}</tbody>
                </table>
            </div>
            
            <div class="a-section">SECTION 2 &mdash; ROBUSTESSE HORIZON (Payload D uniquement)</div>
            <div class="a-tbl-wrap">
                <table class="a-table">
                    <thead><tr><th>Horizon</th><th>Spearman &rho; (p-value)</th><th>Exploitable</th><th>Stabilit&eacute;</th><th>WR Long</th><th>WR Short</th></tr></thead>
                    <tbody>{"".join(rob_rows)}</tbody>
                </table>
            </div>
            
            <div class="a-section">SECTION 3 &mdash; CONCLUSION INT&Eacute;GR&Eacute;E</div>
            <div class="a-conc">
                <div class="c-title">🔍 Source de l’edge</div>
                <div class="c-text">{src_edge}</div>
                
                <div class="c-title" style="margin-top:12px;">⏱&lrm; Horizon recommand&eacute;</div>
                <div class="c-text">{hor_rec}</div>
                
                {vigil_html}
                
                <div class="c-title" style="margin-top:12px;">➡️ Action</div>
                <div class="c-text" style="font-weight:700">{action_txt}</div>
            </div>
        </div>'''
        html_asset_blocks.append(asset_block)

    table_html = (
        f'<table class="synth-table"><thead><tr>'
        f'<th>Asset</th>'
        f'<th>A_h4</th><th>A_h8</th><th>A_h16</th>'
        f'<th>B_h8</th><th>C_h8</th>'
        f'<th>D_h4</th><th>D_h8</th><th>D_h16</th>'
        f'</tr></thead><tbody>{"".join(html_rows)}</tbody></table>'
    )

    verdicts_html = f'<div class="b-grid">{"".join(html_verdict_blocks)}</div>'
    assets_html   = "".join(html_asset_blocks)

    HTML = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Section 4 — Synthesis Report</title>
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

header{{padding:2rem 2.5rem 1.4rem;border-bottom:1px solid var(--border);}}
.h-title{{font-size:1.4rem;font-weight:700;letter-spacing:-0.02em;color:var(--text)}}

main{{padding:1.8rem 2.5rem 3rem;max-width:1440px}}
.sec-label{{font-size:0.75rem;font-weight:700;letter-spacing:0.13em;text-transform:uppercase;color:var(--muted);padding-left:10px;border-left:3px solid var(--purple);margin:2.5rem 0 1.2rem}}

.b-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:15px;margin-bottom:2rem}}

/* Banners */
.banner{{border-radius:10px;padding:1.1rem 1.5rem;display:flex;flex-direction:column;gap:5px;border:1px solid}}
.banner.go{{background:var(--go-dim);border-color:var(--go-border)}}
.banner.ng{{background:var(--bg3);border-color:var(--border)}}
.banner .btitle{{font-size:1.05rem;font-weight:700}}
.banner.go .btitle{{color:var(--go)}}
.banner.ng .btitle{{color:var(--ng)}}
.banner .bsub{{font-size:0.8rem;color:var(--muted);line-height:1.4}}

/* Table */
.tbl-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;overflow:auto;margin-bottom:2rem}}
table{{width:100%;border-collapse:collapse;font-size:0.85rem;white-space:nowrap}}
th{{padding:12px 15px;text-align:left;font-weight:600;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);border-bottom:1px solid var(--border)}}
td{{padding:12px 15px;border-bottom:1px solid rgba(255,255,255,0.04);}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover td{{background:rgba(255,255,255,0.02)}}
.bdg{{display:inline-block;padding:3px 10px;border-radius:4px;font-size:0.7rem;font-weight:700;letter-spacing:0.04em}}
.bdg-go{{background:var(--go-dim);color:var(--go)}}
.bdg-ng{{background:var(--ng-dim);color:var(--ng)}}

.c-go{{color:var(--go)}} .c-ng{{color:var(--ng)}} .c-amber{{color:var(--amber)}}

/* Analyse par Asset */
.asset-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; margin-bottom: 2rem; overflow:hidden; }}
.a-header {{ background:var(--bg3); padding:1rem 1.5rem; font-size:1.1rem; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:15px; }}
.a-section {{ background: rgba(255,255,255,0.02); padding: 8px 1.5rem; font-size:0.75rem; font-weight:700; color:var(--muted); letter-spacing:0.05em; border-bottom:1px solid var(--border); border-top:1px solid var(--border); margin-top:-1px; }}
.a-tbl-wrap {{ overflow-x:auto; padding-bottom: 10px; }}
.a-table {{ width:100%; border-collapse:collapse; font-size:0.85rem; white-space:nowrap; }}
.a-table th {{ padding:10px 1.5rem; text-align:left; font-weight:600; font-size:0.7rem; color:var(--muted); border-bottom:1px solid var(--border); }}
.a-table td {{ padding:10px 1.5rem; border-bottom:1px solid rgba(255,255,255,0.04); }}
.a-conc {{ padding: 1.2rem 1.5rem; }}
.c-title {{ font-weight:700; font-size:0.85rem; color:var(--text); margin-bottom:4px; }}
.c-text {{ font-size:0.85rem; color:var(--text); margin-left: 20px; line-height:1.4; }}
</style>
</head>
<body>
  <header>
    <div class="h-title">📊 Section 4 &mdash; Synth&egrave;se SweepLQ</div>
    <div style="font-size:0.8rem;color:var(--muted);margin-top:5px">Consolidation des 8-runs Multi-Payload Multi-Horizon</div>
  </header>
  <main>
    <div class="sec-label">BLOC 1 — Verdict global multi-horizons</div>
    {verdicts_html}

    <div class="sec-label">BLOC 2 — Matrice de décision statistique</div>
    <div class="tbl-wrap">
      {table_html}
    </div>

    <div class="sec-label">BLOC 3 — Analyse par Asset</div>
    {assets_html}
  </main>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(HTML)

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(filepath)}")

    return filepath
