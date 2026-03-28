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
    html_diag_blocks = []
    html_rob_blocks = []

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

        # ---- BLOC 3: Lecture comparative ----
        if d_D8 == "GO" and sp_D8 > sp_A8:
            diag_txt = "Edge complet &mdash; Sweep ajoute de l’alpha au biais"
            diag_act = "D&eacute;ployable pour tests OOS/Walk-Forward."
            icon = "✅"
        elif d_A8 == "GO" and d_D8 != "GO":
            diag_txt = "Biais seul suffisant &mdash; Sweep n’ajoute rien"
            diag_act = "Revoir la logique d’entr&eacute;e ou traiter en trend-following pur."
            icon = "⚠️"
        elif d_B8 == "GO" and d_C8 != "GO":
            diag_txt = "Engulfing valide mais filtre MTF d&eacute;grade le signal"
            diag_act = "D&eacute;sactiver le filtre MTF ou l’adapter."
            icon = "⚠️"
        else:
            diag_txt = "Aucun edge d&eacute;tect&eacute; sur cet asset"
            diag_act = "Abandonner ou revoir l’hypoth&egrave;se fondamentale."
            icon = "❌"

        html_diag_blocks.append(
            f'<div class="diag-card">'
            f'<div class="diag-title">{icon} {asset}</div>'
            f'<div class="diag-txt">{diag_txt}</div>'
            f'<div class="diag-act">&rarr; {diag_act}</div>'
            f'</div>'
        )

        # ---- BLOC 4: Robustesse D ----
        def _bar(h_lbl, rho, go):
            if rho == -999.0:
                val = 0
                r_txt = "N/A"
            else:
                val = max(0, min(100, rho * 1000))
                r_txt = str(round(rho, 3))
            
            color = "var(--go)" if go == "GO" else "var(--ng)"
            cls_txt = "c-go" if go == "GO" else "c-ng"
            
            return (
                f'<div style="display:flex;align-items:center;gap:10px;margin:3px 0;">'
                f'<span style="width:30px;font-size:0.75rem;color:var(--muted)">h={h_lbl}</span>'
                f'<div style="flex:1;background:var(--bg3);height:10px;border-radius:2px;overflow:hidden;border:1px solid var(--border)">'
                f'<div style="width:{val}%;background:{color};height:100%"></div>'
                f'</div>'
                f'<span style="width:105px;font-size:0.75rem;font-family:var(--mono);">ρ = {r_txt}'
                f' <span class="{cls_txt}">({go})</span></span>'
                f'</div>'
            )

        b_robust = "Edge robuste" if (d_D4 == "GO" and d_D8 == "GO") else "Edge fragile / Inexistant"
        if d_D16 == "GO" and d_D4 != "GO" and d_D8 != "GO":
            b_robust = "Edge fragile (uniquement h=16)."

        html_rob_blocks.append(
            f'<div class="rob-card">'
            f'<div style="font-weight:700;margin-bottom:8px">{asset}</div>'
            f'{_bar("4", sp_D4, d_D4)}'
            f'{_bar("8", sp_D8, d_D8)}'
            f'{_bar("16", sp_D16, d_D16)}'
            f'<div class="bsub" style="margin-top:8px;border-top:1px dashed var(--border);padding-top:6px">{b_robust}</div>'
            f'</div>'
        )

    table_html = (
        f'<table class="synth-table"><thead><tr>'
        f'<th>Asset</th>'
        f'<th>A_h4</th><th>A_h8</th><th>A_h16</th>'
        f'<th>B_h8</th><th>C_h8</th>'
        f'<th>D_h4</th><th>D_h8</th><th>D_h16</th>'
        f'</tr></thead><tbody>{"".join(html_rows)}</tbody></table>'
    )

    verdicts_html = f'<div class="b-grid">{"".join(html_verdict_blocks)}</div>'
    diags_html    = f'<div class="b-grid">{"".join(html_diag_blocks)}</div>'
    robs_html     = f'<div class="b-grid">{"".join(html_rob_blocks)}</div>'

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

/* Cards */
.diag-card, .rob-card {{ background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:1.1rem; }}
.diag-title {{ font-weight:700; margin-bottom: 8px; font-size: 0.95rem; }}
.diag-txt {{ font-size: 0.85rem; font-weight: 500; color:var(--text); line-height:1.4 }}
.diag-act {{ margin-top: 8px; font-size: 0.75rem; color: var(--amber); }}
.bsub {{ font-size:0.75rem; color:var(--muted); }}

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

.c-go{{color:var(--go)}} .c-ng{{color:var(--ng)}}
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

    <div class="sec-label">BLOC 3 — Lecture comparative (Diagnostic Alpha)</div>
    {diags_html}

    <div class="sec-label">BLOC 4 — Robustesse Multi-Horizons (Payload D)</div>
    {robs_html}
  </main>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(HTML)

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(filepath)}")

    return filepath
