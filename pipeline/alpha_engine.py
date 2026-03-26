"""
pipeline/alpha_engine.py
========================
Moteur statistique Section 4 — pipeline entonnoir v4.1.

Ce module est AGNOSTIQUE à toute stratégie.
Il reçoit un AlphaPayload et retourne un dict de résultats statistiques.

Pipeline séquentiel (bloquant sauf Étape 4) :
  Étape 0 — Sanity Check            → BLOQUANT
  Étape 1 — Détection signal        → BLOQUANT  (Spearman OU MI)
  Étape 2 — Discrimination stat.    → BLOQUANT  (KS OU T-test OU Wilcoxon)
  Étape 3 — Exploitabilité trading  → CRITIQUE  (Monotone OU Q1/Q5)
  Étape 4 — Robustesse temporelle   → NON BLOQUANT (flag 'fragile')

Adaptation automatique du type de signal
-----------------------------------------
Le moteur détecte automatiquement si X est discret ou continu, et adapte
les méthodes de comparaison en conséquence — sans intervention de la stratégie.

  X DISCRET  (ex: {-1, 0, 1}, {0, 1, 2} — peu de valeurs uniques)
    → Étape 2 : T-test / Wilcoxon comparent les groupes de valeurs distinctes
                (Long vs Short, ou top-classe vs bottom-classe)
    → Étape 3 : rendement moyen par valeur de signal

  X CONTINU  (ex: RSI, z-score, MI — distribution continue)
    → Étape 2 : T-test / Wilcoxon comparent quantile(70%) vs quantile(30%)
    → Étape 3 : pd.qcut en QUANTILE_N bins

Critère de détection :
    ratio = n_valeurs_uniques / n_total
    ratio < DISCRETE_RATIO_THRESH → X DISCRET
    ratio ≥ DISCRETE_RATIO_THRESH → X CONTINU

Point d'entrée unique : alpha_pipeline(payload) -> dict
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ks_2samp, ttest_ind, wilcoxon
from sklearn.feature_selection import mutual_info_regression
import warnings

from pipeline.payload import AlphaPayload

warnings.filterwarnings("ignore")


# ============================================================
# CONFIG — seuils du pipeline
# ============================================================
MIN_SIGNALS           = 100    # blueprint v4.1 : minimum 100 observations
SPEARMAN_PVAL_THRESH  = 0.05
MI_THRESH             = 0.01
KS_PVAL_THRESH        = 0.05
ROLLING_WINDOW        = 500    # barres pour la rolling Spearman
QUANTILE_N            = 5      # bins pour X continu (pd.qcut)
DISCRETE_RATIO_THRESH = 0.05   # si n_unique/n_total < 5% → X discret
MIN_GROUP_SIZE        = 5      # taille minimale d'un groupe pour T-test/Wilcoxon


# ============================================================
# HELPERS INTERNES
# ============================================================

def _safe_round(v, d: int = 4):
    """Arrondit v si numérique, retourne None sinon."""
    try:
        return round(float(v), d)
    except (TypeError, ValueError):
        return None


def _detect_signal_type(x: np.ndarray) -> str:
    """
    Détecte automatiquement le type du signal X.

    Retourne
    --------
    'discrete'  : peu de valeurs uniques (signal catégoriel)
    'continuous' : distribution continue
    """
    n_unique = len(np.unique(x))
    ratio    = n_unique / len(x)
    return "discrete" if ratio < DISCRETE_RATIO_THRESH else "continuous"


def _get_comparison_groups(
    df_sig: pd.DataFrame,
    signal_type: str,
) -> tuple[pd.Series, pd.Series, str]:
    """
    Construit les deux groupes à comparer pour T-test et Wilcoxon.

    Pour X DISCRET  : groupe_haut = valeur max de X (ex: +1 = Long)
                      groupe_bas  = valeur min de X (ex: -1 = Short)
                      Si X unidirectionnel ({0,1} ou {0,-1}) :
                        groupe_haut = signal actif
                        groupe_bas  = barres flat (X==0)

    Pour X CONTINU  : groupe_haut = top 30% de X
                      groupe_bas  = bottom 30% de X

    Retourne (Y_high, Y_low, description_str)
    """
    X = df_sig["_X"]
    Y = df_sig["_Y"]

    if signal_type == "discrete":
        unique_vals = sorted(X.unique())
        v_max = unique_vals[-1]
        v_min = unique_vals[0]

        # Signal bidirectionnel (ex: {-1, 0, 1} ou {-1, 1})
        if v_min < 0 and v_max > 0:
            Y_high = Y[X == v_max]
            Y_low  = Y[X == v_min]
            desc   = f"Long (X={v_max}) vs Short (X={v_min})"

        # Signal unidirectionnel positif ({0, 1})
        elif v_min >= 0 and v_max > 0:
            Y_high = Y[X == v_max]
            Y_low  = Y[X == 0] if 0 in unique_vals else Y[X == v_min]
            desc   = f"Signal actif (X={v_max}) vs Flat (X=0)"

        # Signal unidirectionnel négatif ({-1, 0})
        elif v_max <= 0 and v_min < 0:
            Y_high = Y[X == 0] if 0 in unique_vals else Y[X == v_max]
            Y_low  = Y[X == v_min]
            desc   = f"Flat (X=0) vs Signal actif (X={v_min})"

        else:
            # Fallback : deux extrêmes quelles que soient les valeurs
            Y_high = Y[X == v_max]
            Y_low  = Y[X == v_min]
            desc   = f"X={v_max} vs X={v_min}"

    else:  # continuous
        q70 = X.quantile(0.7)
        q30 = X.quantile(0.3)
        Y_high = Y[X > q70]
        Y_low  = Y[X < q30]
        desc   = "Top 30% vs Bottom 30% de X"

    return Y_high, Y_low, desc


def _build_quantile_analysis(
    df_sig: pd.DataFrame,
    signal_type: str,
) -> dict:
    """
    Analyse par quantile / classe — adaptée au type de X.

    Pour X DISCRET  : groupe par valeur unique de X
                      (rendement moyen et Sharpe par classe de signal)

    Pour X CONTINU  : pd.qcut en QUANTILE_N bins

    Retourne un dict avec :
        returns    : {label: mean_Y}
        sharpes    : {label: sharpe}
        vals       : np.array des means dans l'ordre des groupes
        n_groups   : int
        method     : 'discrete_groups' | 'quantile_bins'
    """
    X = df_sig["_X"]
    Y = df_sig["_Y"]

    if signal_type == "discrete":
        unique_vals = sorted(X.unique())
        rows = []
        for v in unique_vals:
            y_group = Y[X == v]
            if len(y_group) < 3:
                continue
            mean_y = float(y_group.mean())
            std_y  = float(y_group.std())
            sharpe = mean_y / (std_y + 1e-10)
            rows.append({
                "label":  str(round(v, 4)),
                "mean":   mean_y,
                "sharpe": sharpe,
                "n":      len(y_group),
            })

        returns = {r["label"]: _safe_round(r["mean"], 6) for r in rows}
        sharpes = {r["label"]: _safe_round(r["sharpe"], 4) for r in rows}
        vals    = np.array([r["mean"] for r in rows])
        method  = "discrete_groups"

    else:  # continuous
        try:
            df_sig = df_sig.copy()
            df_sig["_q"] = pd.qcut(X, q=QUANTILE_N, duplicates="drop", labels=False)
            qr = df_sig.groupby("_q")["_Y"].agg(["mean", "std", "count"])
            qr["sharpe"] = qr["mean"] / (qr["std"].replace(0, np.nan) + 1e-10)
            returns = {str(int(k)): _safe_round(float(v), 6) for k, v in qr["mean"].items()}
            sharpes = {str(int(k)): _safe_round(float(v), 4) for k, v in qr["sharpe"].items()}
            vals    = qr["mean"].values
            method  = "quantile_bins"
        except Exception:
            return {"returns": {}, "sharpes": {}, "vals": np.array([]),
                    "n_groups": 0, "method": "quantile_bins"}

    return {
        "returns":  returns,
        "sharpes":  sharpes,
        "vals":     vals,
        "n_groups": len(vals),
        "method":   method,
    }


def _rolling_spearman(df_sig: pd.DataFrame) -> tuple[list, list]:
    """Calcule la rolling Spearman sur la fenêtre ROLLING_WINDOW."""
    ri, rc = [], []
    n = len(df_sig)
    if n < ROLLING_WINDOW:
        return ri, rc
    step = max(1, n // 120)
    for i in range(ROLLING_WINDOW, n, step):
        w = df_sig.iloc[i - ROLLING_WINDOW : i]
        if len(w) < 50:
            continue
        c_r, _ = spearmanr(w["_X"], w["_Y"])
        ri.append(i)
        rc.append(_safe_round(c_r))
    return ri, rc


# ============================================================
# PIPELINE ENTONNOIR v4.1
# ============================================================

def alpha_pipeline(payload: AlphaPayload) -> dict:
    """
    Pipeline entonnoir v4.1 — validation statistique séquentielle stricte.
    Adaptatif : détecte automatiquement le type de signal (discret/continu).

    Paramètres
    ----------
    payload : AlphaPayload
        Contrat de données produit par la stratégie.

    Retourne
    --------
    dict avec les clés :
        decision          : 'GO' | 'NO GO'
        fail_step         : int | None
        fail_reason       : str | None
        robustness_flag   : 'stable' | 'fragile' | None
        tests_passed      : int (0–4)
        signal_type       : 'discrete' | 'continuous'
        comparison_method : description des groupes comparés
        detail            : str résumé
        + tous les résultats intermédiaires
        + échantillons pour visualisations HTML
    """
    r: dict = {
        "asset":     payload.asset,
        "tf":        payload.tf,
        "horizon_h": payload.horizon_h,
        "strategy":  payload.strategy_name,
        "meta":      payload.meta,
    }

    # ── Extraction et alignement ───────────────────────────────────────────
    idx   = payload.X.index.intersection(payload.Y.index)
    X_all = payload.X.loc[idx]
    Y_all = payload.Y.loc[idx]

    mask_sig  = X_all != 0
    X_sig_raw = X_all[mask_sig]
    Y_sig_raw = Y_all[mask_sig]

    valid = np.isfinite(X_sig_raw.values) & np.isfinite(Y_sig_raw.values)
    X_sig = X_sig_raw[valid]
    Y_sig = Y_sig_raw[valid]

    r["n_signals"] = len(X_sig)
    r["n_long"]    = int((X_sig > 0).sum())
    r["n_short"]   = int((X_sig < 0).sum())

    Y_flat = (payload.Y_flat.dropna() if payload.Y_flat is not None
              else Y_all[~mask_sig].dropna())

    # ── Détection du type de signal ────────────────────────────────────────
    # Effectuée ICI une seule fois, utilisée par E2 et E3
    signal_type = _detect_signal_type(X_sig.values)
    r["signal_type"] = signal_type

    # ──────────────────────────────────────────────────────────────────────
    # ÉTAPE 0 — SANITY CHECK (bloquant)
    # ──────────────────────────────────────────────────────────────────────
    has_nan = bool(X_sig_raw.isnull().any() or Y_sig_raw.isnull().any())
    has_inf = bool(not np.isfinite(X_sig_raw.values).all()
                   or not np.isfinite(Y_sig_raw.values).all())

    r["sanity_nan"] = has_nan
    r["sanity_inf"] = has_inf
    r["sanity_ok"]  = (not has_nan) and (not has_inf) and (r["n_signals"] >= MIN_SIGNALS)

    if not r["sanity_ok"]:
        reasons = []
        if has_nan: reasons.append("NaN détectés dans X ou Y")
        if has_inf: reasons.append("Inf détectés dans X ou Y")
        if r["n_signals"] < MIN_SIGNALS:
            reasons.append(f"Observations insuffisantes : {r['n_signals']} < {MIN_SIGNALS}")
        r.update({"decision": "NO GO", "fail_step": 0,
                  "fail_reason": " | ".join(reasons),
                  "tests_passed": 0, "robustness_flag": None,
                  "detail": f"Étape 0 Sanity=❌ | {' | '.join(reasons)}"})
        _add_empty_viz_samples(r)
        return r

    df_sig = pd.DataFrame({"_X": X_sig.values, "_Y": Y_sig.values},
                           index=X_sig.index)

    # ──────────────────────────────────────────────────────────────────────
    # ÉTAPE 1 — DÉTECTION DE SIGNAL (bloquant)
    # Condition : Spearman p < 0.05  OU  MI > 0.01
    # ──────────────────────────────────────────────────────────────────────
    # Spearman nécessite au moins 2 valeurs distinctes dans X
    # Si X est constant (ex: 100% short, 0 longs), retourne NaN
    if len(df_sig["_X"].unique()) >= 2:
        corr, pval = spearmanr(df_sig["_X"], df_sig["_Y"])
        r["spearman_corr"] = _safe_round(corr)
        r["spearman_pval"] = _safe_round(pval)
        r["spearman_go"]   = bool(pval is not None
                                  and not np.isnan(float(pval))
                                  and pval < SPEARMAN_PVAL_THRESH)
    else:
        r["spearman_corr"] = None
        r["spearman_pval"] = None
        r["spearman_go"]   = False  # MI seul décidera

    mi = mutual_info_regression(
        df_sig["_X"].values.reshape(-1, 1), df_sig["_Y"].values
    )[0]
    r["mutual_info"] = _safe_round(mi)
    r["mi_go"]       = bool(mi > MI_THRESH)

    r["step1_ok"] = r["spearman_go"] or r["mi_go"]

    # ──────────────────────────────────────────────────────────────────────
    # ÉTAPE 2 — DISCRIMINATION STATISTIQUE (bloquant)
    # Condition : KS p < 0.05  OU  T-test p < 0.05  OU  Wilcoxon p < 0.05
    # ──────────────────────────────────────────────────────────────────────

    # KS : distribution signal vs flat (identique quel que soit le type)
    if len(Y_flat) > 10:
        ks_s, ks_p = ks_2samp(df_sig["_Y"].values, Y_flat.values)
        r["ks_stat"] = _safe_round(ks_s)
        r["ks_pval"] = _safe_round(ks_p)
        r["ks_go"]   = bool(ks_p < KS_PVAL_THRESH)
    else:
        r["ks_stat"] = r["ks_pval"] = None
        r["ks_go"]   = False

    # T-test + Wilcoxon : groupes adaptés au type de X
    Y_high, Y_low, comp_desc = _get_comparison_groups(df_sig, signal_type)
    r["comparison_method"] = comp_desc

    # Fallback : si un groupe est trop petit (ex: signal quasi-unidirectionnel
    # avec 1 seul long sur 111 short), comparer le groupe dominant contre Y_flat
    if len(Y_high) < MIN_GROUP_SIZE or len(Y_low) < MIN_GROUP_SIZE:
        # Identifier le groupe dominant
        big_group   = Y_high if len(Y_high) >= len(Y_low) else Y_low
        small_group = Y_high if len(Y_high) <  len(Y_low) else Y_low
        if len(big_group) >= MIN_GROUP_SIZE and len(Y_flat) >= MIN_GROUP_SIZE:
            Y_high = big_group
            Y_low  = Y_flat
            comp_desc += " (fallback: dominant vs flat)"
            r["comparison_method"] = comp_desc
        # else : vraiment pas assez de données — on laisse None

    if len(Y_high) >= MIN_GROUP_SIZE and len(Y_low) >= MIN_GROUP_SIZE:
        tt_s, tt_p = ttest_ind(Y_high, Y_low, equal_var=False)
        r["ttest_stat"] = _safe_round(tt_s)
        r["ttest_pval"] = _safe_round(tt_p)
        r["ttest_go"]   = bool(tt_p < KS_PVAL_THRESH)

        try:
            n_min = min(len(Y_high), len(Y_low))
            wil_s, wil_p = wilcoxon(
                Y_high.values[:n_min] - Y_low.values[:n_min]
            )
            r["wilcoxon_stat"] = _safe_round(wil_s)
            r["wilcoxon_pval"] = _safe_round(wil_p)
            r["wilcoxon_go"]   = bool(wil_p < KS_PVAL_THRESH)
        except Exception:
            r["wilcoxon_stat"] = r["wilcoxon_pval"] = None
            r["wilcoxon_go"]   = False
    else:
        r["ttest_stat"] = r["ttest_pval"] = None
        r["ttest_go"]   = False
        r["wilcoxon_stat"] = r["wilcoxon_pval"] = None
        r["wilcoxon_go"]   = False

    r["step2_ok"] = r["ks_go"] or r["ttest_go"] or r["wilcoxon_go"]

    # ──────────────────────────────────────────────────────────────────────
    # ÉTAPE 3 — EXPLOITABILITÉ TRADING (critique — bloquant)
    # Condition : tendance monotone OU extrêmes significatifs
    # ──────────────────────────────────────────────────────────────────────
    qa = _build_quantile_analysis(df_sig, signal_type)

    r["quantile_returns"]  = qa["returns"]
    r["quantile_sharpes"]  = qa["sharpes"]
    r["quantile_method"]   = qa["method"]
    r["quantile_n_groups"] = qa["n_groups"]

    vals = qa["vals"]

    if len(vals) >= 2:
        mono_up   = bool(all(vals[i] <= vals[i+1] for i in range(len(vals)-1)))
        mono_down = bool(all(vals[i] >= vals[i+1] for i in range(len(vals)-1)))
        r["quantile_monotone"]    = mono_up or mono_down

        diff = float(vals[-1] - vals[0])
        r["q1_vs_q5_diff"]        = _safe_round(diff, 6)
        r["q1_vs_q5_exploitable"] = abs(diff) > 0.0001
    else:
        r["quantile_monotone"]    = False
        r["q1_vs_q5_diff"]        = None
        r["q1_vs_q5_exploitable"] = False

    # Si un seul groupe (signal quasi-unidirectionnel), comparer ce groupe vs Y_flat
    if len(vals) == 1 and len(Y_flat) >= MIN_GROUP_SIZE:
        flat_mean = float(Y_flat.mean())
        diff_vs_flat = float(vals[0]) - flat_mean
        r["q1_vs_q5_diff"]        = _safe_round(diff_vs_flat, 6)
        r["q1_vs_q5_exploitable"] = abs(diff_vs_flat) > 0.0001
        r["quantile_returns"]["flat"] = _safe_round(flat_mean, 6)
        r["quantile_method"]          = r.get("quantile_method","") + "+flat_comparison"

    r["step3_ok"] = r["quantile_monotone"] or r["q1_vs_q5_exploitable"]

    # ── Décision fail ──────────────────────────────────────────────────────
    fail_step = None
    if not r["step1_ok"]:
        fail_step = 1
        r["fail_reason"] = (f"Aucun signal détecté "
                            f"(Spearman p={r['spearman_pval']} | MI={r['mutual_info']})")
    elif not r["step2_ok"]:
        fail_step = 2
        r["fail_reason"] = (f"Aucune discrimination [{signal_type}] "
                            f"(KS p={r['ks_pval']} | T-test p={r['ttest_pval']} "
                            f"| Wilcoxon p={r['wilcoxon_pval']}) — {comp_desc}")
    elif not r["step3_ok"]:
        fail_step = 3
        r["fail_reason"] = (f"Pas de tendance exploitable [{qa['method']}] "
                            f"— {qa['n_groups']} groupes, diff={r['q1_vs_q5_diff']}")

    # ──────────────────────────────────────────────────────────────────────
    # ÉTAPE 4 — ROBUSTESSE TEMPORELLE (non bloquant)
    # ──────────────────────────────────────────────────────────────────────
    ri, rc = _rolling_spearman(df_sig)
    r["rolling_spearman_idx"]  = ri
    r["rolling_spearman_corr"] = rc

    if rc:
        rc_arr = np.array(rc)
        r["rolling_std"]          = _safe_round(float(rc_arr.std()))
        r["rolling_median"]       = _safe_round(float(np.median(rc_arr)))
        r["rolling_sign_changes"] = int(np.sum(np.diff(np.sign(rc_arr)) != 0))
        r["robustness_flag"]      = (
            "fragile"
            if r["rolling_std"] > 0.15 or r["rolling_sign_changes"] > len(rc) * 0.4
            else "stable"
        )
    else:
        r["rolling_std"] = r["rolling_median"] = r["rolling_sign_changes"] = None
        r["robustness_flag"] = None

    # ── Shuffle control ────────────────────────────────────────────────────
    if len(df_sig["_X"].unique()) >= 2:
        cs, _ = spearmanr(
            df_sig["_X"].sample(frac=1, random_state=42).values,
            df_sig["_Y"].values
        )
        r["shuffle_corr"] = _safe_round(cs)
        r["shuffle_ok"]   = bool(cs is not None
                                  and not np.isnan(float(cs))
                                  and abs(cs) < 0.03)
    else:
        # X constant → le shuffle ne change rien → pas de biais possible
        r["shuffle_corr"] = None
        r["shuffle_ok"]   = True

    # ── Métriques de performance ───────────────────────────────────────────
    dl = df_sig[df_sig["_X"] > 0]
    ds = df_sig[df_sig["_X"] < 0]

    r["win_rate_long"]  = _safe_round((dl["_Y"] > 0).mean()) if len(dl) else None
    r["win_rate_short"] = _safe_round((ds["_Y"] > 0).mean()) if len(ds) else None
    r["avg_Y_long"]     = _safe_round(dl["_Y"].mean(), 6)    if len(dl) else None
    r["avg_Y_short"]    = _safe_round(ds["_Y"].mean(), 6)    if len(ds) else None

    if payload.sl_long is not None:
        sl_l = payload.sl_long.reindex(X_sig.index).dropna()
        r["avg_sl_dist_long"] = _safe_round(sl_l.mean(), 6) if len(sl_l) else None
    else:
        r["avg_sl_dist_long"] = None

    if payload.sl_short is not None:
        sl_s = payload.sl_short.reindex(X_sig.index).dropna()
        r["avg_sl_dist_short"] = _safe_round(sl_s.mean(), 6) if len(sl_s) else None
    else:
        r["avg_sl_dist_short"] = None

    # ── Échantillons pour visualisations ───────────────────────────────────
    n_samp = min(2000, len(df_sig))
    r["Y_signal_sample"] = df_sig["_Y"].dropna().sample(n_samp, random_state=42).tolist()
    r["Y_flat_sample"]   = Y_flat.dropna().sample(
        min(2000, len(Y_flat)), random_state=42).tolist()
    r["Y_long_sample"]   = dl["_Y"].dropna().tolist()
    r["Y_short_sample"]  = ds["_Y"].dropna().tolist()

    # ── Décision finale ────────────────────────────────────────────────────
    r["tests_passed"] = sum([
        r.get("sanity_ok",  False),
        r.get("step1_ok",   False),
        r.get("step2_ok",   False),
        r.get("step3_ok",   False),
    ])
    r["fail_step"] = fail_step
    r["decision"]  = "GO" if fail_step is None else "NO GO"
    if fail_step is None:
        r["fail_reason"] = None

    r["detail"] = (
        f"E0 Sanity=✅ | "
        f"E1 Signal={'✅' if r.get('step1_ok') else '❌'} "
        f"(Spearman={'✅' if r['spearman_go'] else '❌'} | MI={'✅' if r['mi_go'] else '❌'}) | "
        f"E2 Discrim={'✅' if r.get('step2_ok') else '❌'} [{signal_type}] "
        f"(KS={'✅' if r['ks_go'] else '❌'} | T={'✅' if r['ttest_go'] else '❌'} | "
        f"W={'✅' if r['wilcoxon_go'] else '❌'}) | "
        f"E3 Exploit={'✅' if r.get('step3_ok') else '❌'} [{qa['method']}] | "
        f"E4 Rob={'stable ✅' if r.get('robustness_flag') == 'stable' else '⚠️ fragile' if r.get('robustness_flag') == 'fragile' else '—'}"
    )

    return r


# ============================================================
# HELPER PRIVÉ
# ============================================================

def _add_empty_viz_samples(r: dict) -> None:
    """Remplit les champs de visualisation avec des valeurs vides (arrêt Étape 0)."""
    for key in ["Y_signal_sample", "Y_flat_sample", "Y_long_sample",
                "Y_short_sample", "rolling_spearman_idx", "rolling_spearman_corr"]:
        r.setdefault(key, [])
    for key in ["spearman_corr", "spearman_pval", "spearman_go",
                "mutual_info", "mi_go", "step1_ok",
                "ks_stat", "ks_pval", "ks_go",
                "ttest_stat", "ttest_pval", "ttest_go",
                "wilcoxon_stat", "wilcoxon_pval", "wilcoxon_go", "step2_ok",
                "quantile_returns", "quantile_sharpes", "quantile_monotone",
                "q1_vs_q5_diff", "q1_vs_q5_exploitable", "step3_ok",
                "shuffle_corr", "shuffle_ok",
                "win_rate_long", "win_rate_short",
                "avg_Y_long", "avg_Y_short",
                "avg_sl_dist_long", "avg_sl_dist_short",
                "comparison_method", "quantile_method", "quantile_n_groups"]:
        r.setdefault(key, None)
    r.setdefault("signal_type", "unknown")
    r.setdefault("detail", f"Étape 0 Sanity=❌ | {r.get('fail_reason', '')}")
