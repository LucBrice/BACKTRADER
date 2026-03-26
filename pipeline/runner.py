"""
pipeline/runner.py
==================
Orchestrateur multi-actifs — agnostique à la stratégie.

Responsabilités :
  - Itérer sur les actifs disponibles dans aligned_data
  - Extraire le DataFrame OHLCV par actif
  - Demander à la Stratégie de construire l'AlphaPayload
  - Passer le payload au moteur alpha_pipeline()
  - Consolider les résultats en DataFrame de synthèse
  - Déclencher la génération du rapport HTML

Point d'entrée principal :
    run_section4_all_assets(aligned_data, strategy, tf, params, ...)
"""

from __future__ import annotations
import pandas as pd
import numpy as np

from pipeline.base import Strategy
from pipeline.alpha_engine import alpha_pipeline
from pipeline.report import generate_html_report


# ============================================================
# CONFIG PAR DÉFAUT
# ============================================================
DEFAULT_TF        = "15min"
DEFAULT_HORIZON_H = 8
DEFAULT_EXPIRY    = 3
DEFAULT_TF_MIN    = 15
OUTPUT_DIR        = "Reports"


# ============================================================
# RAPPORT CONSOLE
# ============================================================

def print_report(r: dict) -> None:
    """Affiche le rapport console d'un actif — pipeline entonnoir v4.1."""
    sep = "=" * 65
    bar = "-" * 65
    def tick(b): return "✅" if b else "❌"

    print(f"\n{sep}")
    print(f"  SECTION 4 — ENTONNOIR | {r.get('asset')} [{r.get('tf')}] "
          f"H={r.get('horizon_h')} | {r.get('strategy', '?')}")
    print(sep)

    # Étape 0
    s0 = r.get("sanity_ok", False)
    print(f"\n  Étape 0 — Sanity Check         {tick(s0)}  [BLOQUANT]")
    print(f"    Signaux : {r.get('n_signals', 0)}  "
          f"(Long {r.get('n_long', 0)} / Short {r.get('n_short', 0)})")
    if r.get("sanity_nan"): print("    ❌ NaN détectés dans X ou Y")
    if r.get("sanity_inf"): print("    ❌ Inf détectés dans X ou Y")

    if not s0:
        print(f"\n  DÉCISION : NO GO ❌  [Rejet Étape 0]")
        print(f"  {r.get('fail_reason', '')}")
        print(f"{sep}\n")
        return

    # Étape 1
    s1 = r.get("step1_ok", False)
    print(f"\n  {bar}")
    print(f"  Étape 1 — Détection signal     {tick(s1)}  [BLOQUANT] (Spearman OU MI)")
    print(f"    Spearman : ρ={r.get('spearman_corr')}  "
          f"p={r.get('spearman_pval')}  {tick(r.get('spearman_go'))}")
    print(f"    MI       : {r.get('mutual_info')}  {tick(r.get('mi_go'))}")

    # Étape 2
    s2 = r.get("step2_ok", False)
    print(f"\n  {bar}")
    print(f"  Étape 2 — Discrimination stat. {tick(s2)}  "
          f"[BLOQUANT] (KS OU T-test OU Wilcoxon)")
    print(f"    KS       : stat={r.get('ks_stat')}  "
          f"p={r.get('ks_pval')}  {tick(r.get('ks_go'))}")
    print(f"    T-test   : stat={r.get('ttest_stat')}  "
          f"p={r.get('ttest_pval')}  {tick(r.get('ttest_go'))}")
    print(f"    Wilcoxon : stat={r.get('wilcoxon_stat')}  "
          f"p={r.get('wilcoxon_pval')}  {tick(r.get('wilcoxon_go'))}")

    # Étape 3
    s3 = r.get("step3_ok", False)
    print(f"\n  {bar}")
    print(f"  Étape 3 — Exploitabilité       {tick(s3)}  [CRITIQUE]")
    print(f"    Monotone  : {tick(r.get('quantile_monotone'))}")
    print(f"    Q1/Q5 diff: {r.get('q1_vs_q5_diff')}  "
          f"{tick(r.get('q1_vs_q5_exploitable'))}")

    # Étape 4
    rob = r.get("robustness_flag")
    rob_l = "Stable ✅" if rob == "stable" else ("⚠️ Fragile" if rob == "fragile" else "—")
    print(f"\n  {bar}")
    print(f"  Étape 4 — Robustesse           {rob_l}  [NON BLOQUANT]")
    print(f"    std={r.get('rolling_std')}  "
          f"median={r.get('rolling_median')}  "
          f"sign_changes={r.get('rolling_sign_changes')}")

    print(f"\n  Shuffle : ρ={r.get('shuffle_corr')}  {tick(r.get('shuffle_ok'))}")

    print(f"\n  {bar}")
    print(f"  Performance")
    print(f"    WR Long  {r.get('win_rate_long')}  |  Avg Y = {r.get('avg_Y_long')}")
    print(f"    WR Short {r.get('win_rate_short')}  |  Avg Y = {r.get('avg_Y_short')}")
    sl_l = round((r.get("avg_sl_dist_long") or 0) * 100, 3)
    sl_s = round((r.get("avg_sl_dist_short") or 0) * 100, 3)
    if r.get("avg_sl_dist_long"):
        print(f"    SL Long  {sl_l}%  |  SL Short {sl_s}%")

    print(f"\n{sep}")
    dec = r.get("decision", "NO GO")
    tp  = r.get("tests_passed", 0)
    if dec == "GO":
        print(f"  DÉCISION : GO ✅  ({tp}/4 étapes bloquantes passées)")
        if rob == "fragile":
            print("  ⚠️  Signal FRAGILE — surveiller en Walk-Forward")
    else:
        print(f"  DÉCISION : NO GO ❌  (Rejet étape {r.get('fail_step')})")
        print(f"  {r.get('fail_reason', '')}")
    print(f"{sep}\n")


# ============================================================
# RUNNER MONO-ACTIF
# ============================================================

def run_section4(
    aligned_data: dict,
    strategy:     Strategy,
    asset:        str,
    tf:           str  = DEFAULT_TF,
    params:       dict | None = None,
) -> dict:
    """
    Pré-validation Section 4 sur un seul actif.

    Paramètres
    ----------
    aligned_data : dict
        Dictionnaire produit par fetch_and_filter_data().
        Structure : aligned_data[tf]["open"|"high"|"low"|"close"][asset]

    strategy : Strategy
        Instance d'une classe héritant de Strategy.
        Ex: SweepLQStrategy()

    asset : str
        Actif à analyser.

    tf : str
        Timeframe cible.

    params : dict | None
        Paramètres passés à strategy.build_payload().
        Minimum : {"horizon_h": int}

    Retourne
    --------
    dict — résultats complets de alpha_pipeline() + clé "_payload"
    """
    params = params or {"horizon_h": DEFAULT_HORIZON_H}

    if tf not in aligned_data:
        raise KeyError(f"TF '{tf}' absent. Disponibles : {list(aligned_data.keys())}")
    data_tf = aligned_data[tf]
    if asset not in data_tf["close"].columns:
        raise KeyError(f"Asset '{asset}' absent. Disponibles : "
                       f"{list(data_tf['close'].columns)}")

    # Construction du DataFrame OHLCV pour cet actif (TF principal)
    df = pd.DataFrame({
        "open":  data_tf["open"][asset],
        "high":  data_tf["high"][asset],
        "low":   data_tf["low"][asset],
        "close": data_tf["close"][asset],
    }).dropna()



    # ── Injection MTF automatique ──────────────────────────────────────
    # Si use_mtf=True et que les TF H4/D1 sont disponibles dans aligned_data,
    # on injecte df_h4 et df_d1 dans params sans changer la signature publique.
    # Les clés cherchées : "4h" ou "4H" pour H4, "1D" ou "1d" pour D1.
    params = dict(params)   # copie pour ne pas muter le dict de l'appelant
    if params.get("use_mtf", False):
        for h4_key in ("4h", "4H", "H4"):
            if h4_key in aligned_data and asset in aligned_data[h4_key].get("close", pd.DataFrame()).columns:
                params["df_h4"] = pd.DataFrame({
                    "open":  aligned_data[h4_key]["open"][asset],
                    "high":  aligned_data[h4_key]["high"][asset],
                    "low":   aligned_data[h4_key]["low"][asset],
                    "close": aligned_data[h4_key]["close"][asset],
                }).dropna()
                break
        for d1_key in ("1D", "1d", "D1"):
            if d1_key in aligned_data and asset in aligned_data[d1_key].get("close", pd.DataFrame()).columns:
                params["df_d1"] = pd.DataFrame({
                    "open":  aligned_data[d1_key]["open"][asset],
                    "high":  aligned_data[d1_key]["high"][asset],
                    "low":   aligned_data[d1_key]["low"][asset],
                    "close": aligned_data[d1_key]["close"][asset],
                }).dropna()
                break
        if "df_h4" not in params or "df_d1" not in params:
            print(f"   ⚠️  use_mtf=True mais H4 ou D1 introuvable dans aligned_data "
                  f"(clés disponibles : {list(aligned_data.keys())}) — MTF désactivé.")
            params["use_mtf"] = False

    # La stratégie construit le payload — le runner ne sait pas comment
    payload = strategy.build_payload(df, asset, tf, params)

    # Le moteur lance le pipeline — ne sait pas quelle stratégie
    result = alpha_pipeline(payload)
    result["_payload"] = payload   # conservé pour débogage éventuel

    return result


# ============================================================
# RUNNER MULTI-ACTIFS
# ============================================================

def run_section4_all_assets(
    aligned_data:    dict,
    strategy:        Strategy,
    tf:              str  = DEFAULT_TF,
    params:          dict | None = None,
    generate_report: bool = True,
    open_browser:    bool = True,
    output_dir:      str  = OUTPUT_DIR,
) -> pd.DataFrame:
    """
    Scanne TOUS les actifs disponibles + génère le rapport HTML.

    Usage dans votre notebook :
    ---------------------------
        from pipeline.runner import run_section4_all_assets
        from strategies.sweep_lq import SweepLQStrategy

        df_summary = run_section4_all_assets(
            aligned_data,
            strategy = SweepLQStrategy(),
            tf       = "15min",
            params   = {"horizon_h": 8, "expiry_days": 3, "tf_minutes": 15},
        )

    Retourne
    --------
    pd.DataFrame — synthèse par actif, triée GO > NO GO > Tests_OK desc.
    """
    params = params or {"horizon_h": DEFAULT_HORIZON_H}
    horizon_h = params.get("horizon_h", DEFAULT_HORIZON_H)

    if tf not in aligned_data:
        raise KeyError(f"TF '{tf}' absent.")
    assets = aligned_data[tf]["close"].columns.tolist()

    all_results, rows = [], []

    for asset in assets:
        try:
            r = run_section4(aligned_data, strategy, asset, tf, params)
            all_results.append(r)
            decision = r.get("decision", "NO GO")
            rows.append({
                "Asset":     asset,
                "Strategy":  r.get("strategy", "?"),
                "Signaux":   r.get("n_signals", 0),
                "Long":      r.get("n_long", 0),
                "Short":     r.get("n_short", 0),
                "Tests_OK":  r.get("tests_passed", 0),
                "WR_Long":   r.get("win_rate_long"),
                "WR_Short":  r.get("win_rate_short"),
                "SL_Long_%": round((r.get("avg_sl_dist_long") or 0) * 100, 3),
                "Robustness":r.get("robustness_flag") or "—",
                "Fail_Step": r.get("fail_step"),
                "Decision":  decision,
            })
        except Exception as e:
            print(f"  ⚠️  {asset} — {e}")
            rows.append({
                "Asset": asset, "Strategy": str(strategy),
                "Decision": "ERREUR", "Tests_OK": 0
            })

    df_s = pd.DataFrame(rows)
    if not df_s.empty and "Decision" in df_s.columns:
        df_s["_go"] = df_s["Decision"].eq("GO").astype(int)
        df_s = (df_s.sort_values(["_go", "Tests_OK"], ascending=[False, False])
                    .drop(columns=["_go"])
                    .reset_index(drop=True))

    # ── Résumé compact ──────────────────────────────────────────────────
    go_list   = df_s[df_s["Decision"] == "GO"]["Asset"].tolist()  if not df_s.empty else []
    nogo_list = df_s[df_s["Decision"] != "GO"]["Asset"].tolist()  if not df_s.empty else []

    print(f"Section 4  |  {strategy}  |  {tf}  H={horizon_h}")
    print(f"  ✅ GO ({len(go_list)})    : {', '.join(go_list) or '—'}")
    print(f"  ❌ NO GO ({len(nogo_list)}) : {', '.join(nogo_list) or '—'}")

    if generate_report and all_results:
        generate_html_report(all_results, tf, horizon_h, output_dir, open_browser)
        print(f"  → {output_dir}/Section4_Report_{tf}.html")

    return df_s
