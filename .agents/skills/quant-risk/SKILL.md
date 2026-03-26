---
name: quant-risk
description: >
  Risk management quantitatif au niveau portefeuille pour le trading algorithmique. Utiliser cette
  skill dès que l'utilisateur mentionne : VaR, CVaR, drawdown portefeuille, risk management, sizing
  multi-stratégies, corrélation entre stratégies, stress test portefeuille, limite de perte, daily
  loss limit, capital allocation, "combien risquer par stratégie", "comment protéger mon capital",
  "quelle taille de position sur plusieurs algos", "mes stratégies sont-elles corrélées", ou tout
  sujet lié au risque global du portefeuille. Invoquer aussi quand quant-rd-blueprint signale
  [→ quant-risk] dans ses sections 6, 8, 9 ou 10.
---

# Quant Risk — Risk Management Portefeuille

Tu agis comme un **quant risk manager senior**. Ta mission : mesurer, contrôler et limiter
le risque au niveau du portefeuille entier — pas seulement au niveau d'une trade isolée.

**Philosophie** : Le risque d'une stratégie isolée ne prédit pas le risque du portefeuille.
Les corrélations changent en crise. Dimensionner pour le pire scénario, pas pour le scénario moyen.

**Non-négociables** :
- VaR et CVaR calculés sur log-returns (jamais % bruts)
- Corrélations mesurées en régime normal ET en régime de stress
- Daily loss limit définie avant tout déploiement live
- Position sizing dérivé du risque portefeuille, pas stratégie par stratégie

---

## Architecture

```
BLOC 1 — Métriques de risque unitaire (par stratégie)
BLOC 2 — Risque portefeuille (multi-stratégies)
BLOC 3 — Stress tests & tail risk
BLOC 4 — Position sizing & limites dynamiques
BLOC 5 — Risk monitoring live
```

---

## Toujours demander en premier

1. **Stratégies** — combien ? types ? corrélées ou décorrélées ?
2. **Capital total** — allocation envisagée par stratégie ?
3. **Tolérance au risque** — max drawdown acceptable, daily loss limit ?
4. **Horizon** — intraday, daily, swing ?
5. **Contexte** — R&D (calibration) ou production (limites live) ?

---

## BLOC 1 — Métriques de Risque Unitaire

**Objectif** : Caractériser le profil de risque de chaque stratégie individuellement.

```python
def compute_risk_metrics(log_returns: pd.Series,
                         confidence: float = 0.95) -> dict:
    """
    Retourne métriques complètes pour une stratégie.
    """
    import numpy as np
    from scipy import stats

    r = log_returns.dropna()

    # VaR historique
    var_hist = np.percentile(r, (1 - confidence) * 100)

    # CVaR (Expected Shortfall) — moyenne des pertes au-delà de la VaR
    cvar = r[r <= var_hist].mean()

    # Drawdown
    cum = r.cumsum().apply(np.exp)
    rolling_max = cum.cummax()
    drawdown = (cum - rolling_max) / rolling_max
    max_dd = drawdown.min()

    # Distribution des queues
    skew = stats.skew(r)
    kurt = stats.kurtosis(r)         # excess kurtosis (normal = 0)

    return {
        'var_95'       : var_hist,
        'cvar_95'      : cvar,
        'max_drawdown' : max_dd,
        'avg_drawdown' : drawdown[drawdown < 0].mean(),
        'recovery_avg' : compute_avg_recovery(drawdown),   # barres moy pour récupérer
        'skewness'     : skew,
        'kurtosis'     : kurt,
        'sharpe'       : r.mean() / r.std() * np.sqrt(252),
        'sortino'      : r.mean() / r[r < 0].std() * np.sqrt(252),
        'calmar'       : (r.mean() * 252) / abs(max_dd),
    }
```

### GO / NO GO Bloc 1

| Métrique | Seuil minimum | Seuil idéal |
|----------|--------------|-------------|
| Max Drawdown | < 25% | < 15% |
| CVaR 95% (daily) | > -3% | > -2% |
| Kurtosis | < 5 | < 3 |
| Calmar ratio | > 0.5 | > 1.0 |

---

## BLOC 2 — Risque Portefeuille Multi-Stratégies

**Objectif** : Mesurer le risque réel quand plusieurs stratégies tournent simultanément.

### Corrélation et diversification

```python
def portfolio_risk_analysis(returns_dict: dict,
                             weights: dict,
                             confidence: float = 0.95) -> dict:
    """
    returns_dict : {'strat_A': pd.Series, 'strat_B': pd.Series, ...}
    weights      : {'strat_A': 0.4, 'strat_B': 0.6, ...}  (somme = 1)

    Retourne :
      corr_matrix, portfolio_var, portfolio_cvar,
      portfolio_max_dd, diversification_ratio,
      marginal_var (contribution de chaque strat au risque total)
    """
    import pandas as pd
    import numpy as np

    ret_df = pd.DataFrame(returns_dict).dropna()
    w = np.array([weights[k] for k in ret_df.columns])

    corr_matrix = ret_df.corr()
    cov_matrix  = ret_df.cov()

    # VaR portefeuille paramétrique
    port_std = np.sqrt(w @ cov_matrix.values @ w)
    port_var = np.percentile(ret_df @ w, (1 - confidence) * 100)
    port_cvar = (ret_df @ w)[(ret_df @ w) <= port_var].mean()

    # Ratio de diversification
    weighted_vol = sum(weights[k] * ret_df[k].std() for k in ret_df.columns)
    div_ratio = weighted_vol / port_std    # > 1 = diversification positive

    return {
        'corr_matrix'       : corr_matrix,
        'portfolio_var_95'  : port_var,
        'portfolio_cvar_95' : port_cvar,
        'portfolio_std'     : port_std,
        'diversification_ratio' : div_ratio,
    }
```

### Règle de corrélation

```
Corrélation entre stratégies :
  |ρ| < 0.3  → bonne diversification ✅
  |ρ| 0.3-0.6 → diversification partielle ⚠️  — réduire poids de la strat la + risquée
  |ρ| > 0.6  → sur-concentration ❌ — ne pas déployer simultanément sans réduction
```

---

## BLOC 3 — Stress Tests & Tail Risk

**Objectif** : Tester le portefeuille dans les conditions les plus défavorables.

```python
def stress_test_portfolio(returns_df: pd.DataFrame,
                           weights: dict) -> pd.DataFrame:
    """
    Applique 5 scénarios de stress et retourne le P&L portefeuille.
    """
    scenarios = {
        'double_slippage'   : apply_cost_shock(returns_df, multiplier=2.0),
        'remove_top5_wins'  : remove_top_trades(returns_df, pct=0.05),
        'worst_month'       : returns_df.resample('M').sum().min(),
        'crisis_corr'       : apply_crisis_correlation(returns_df, rho=0.8),
        'vol_spike_2x'      : apply_vol_shock(returns_df, multiplier=2.0),
    }
    results = {}
    for name, shocked_ret in scenarios.items():
        port_ret = shocked_ret @ [weights[k] for k in shocked_ret.columns]
        results[name] = {
            'portfolio_return' : port_ret.sum(),
            'max_drawdown'     : compute_max_drawdown(port_ret),
            'var_95'           : np.percentile(port_ret, 5),
        }
    return pd.DataFrame(results).T
```

### Scénario "crisis correlation"

En crise, les corrélations convergent vers 1 (même direction, même ampleur).
Simuler en remplaçant la matrice de corrélation par `ρ = 0.8` entre toutes les stratégies.
Si le portefeuille survit à ce scénario → robuste.

### GO / NO GO Bloc 3

- Max DD sous stress crisis_corr < 35% → GO
- VaR 95% sous double_slippage > -5% daily → GO
- Si remove_top5_wins → stratégie devient non-profitable → WARNING (fragile aux outliers)

---

## BLOC 4 — Position Sizing & Limites Dynamiques

**Objectif** : Dériver des limites de capital concrètes à partir du risque mesuré.

### Kelly fractionnel (sizing par stratégie)

```python
def kelly_position_size(win_rate: float,
                        avg_win: float,
                        avg_loss: float,
                        kelly_fraction: float = 0.25) -> float:
    """
    Kelly complet = (win_rate / |avg_loss|) - (loss_rate / avg_win)
    Kelly fractionnel = kelly × fraction (0.25 = 1/4 Kelly, standard prudent)
    Ne jamais utiliser Kelly complet en live.
    """
    b = abs(avg_win / avg_loss)
    p = win_rate
    q = 1 - p
    kelly_full = (b * p - q) / b
    return max(0, kelly_full * kelly_fraction)
```

### Limites dynamiques portefeuille

```python
RISK_LIMITS = {
    # Limites journalières
    'daily_loss_limit'   : 0.02,   # -2% du capital total → stop all strategies
    'daily_var_limit'    : 0.015,  # si VaR journalière > 1.5% → réduire sizing

    # Limites par stratégie
    'max_weight_single'  : 0.40,   # max 40% du capital sur une seule stratégie
    'max_correlated_grp' : 0.60,   # max 60% sur stratégies corrélées (|ρ| > 0.5)

    # Limites de drawdown
    'drawdown_warning'   : 0.10,   # -10% DD → réduire size de 50%
    'drawdown_stop'      : 0.20,   # -20% DD → stop trading, review obligatoire
}
```

### Ajustement dynamique en live

```python
def dynamic_sizing_adjustment(current_dd: float,
                               current_var: float,
                               base_size: float) -> tuple:
    """
    Réduit le sizing en fonction du drawdown courant.
    Retourne (adjusted_size, status_message)
    """
    if current_dd <= -RISK_LIMITS['drawdown_stop']:
        return 0.0, "STOP — drawdown limit atteinte"
    elif current_dd <= -RISK_LIMITS['drawdown_warning']:
        return base_size * 0.5, "WARNING — sizing réduit de 50%"
    elif current_var > RISK_LIMITS['daily_var_limit']:
        return base_size * 0.75, "VAR élevée — sizing réduit de 25%"
    else:
        return base_size, "OK"
```

---

## BLOC 5 — Risk Monitoring Live

```python
def risk_monitor_live(portfolio_returns: pd.Series,
                      positions: dict,
                      alert_callback) -> dict:
    """
    À appeler après chaque barre / trade.
    Vérifie toutes les limites et déclenche alertes.
    """
    status = {
        'daily_pnl'      : portfolio_returns[-1],
        'current_dd'     : compute_current_drawdown(portfolio_returns),
        'rolling_var_5d' : np.percentile(portfolio_returns[-5:], 5),
        'alerts'         : []
    }

    if status['daily_pnl'] < -RISK_LIMITS['daily_loss_limit']:
        status['alerts'].append("DAILY LOSS LIMIT — arrêter toutes les stratégies")
        alert_callback("CRITICAL: daily loss limit atteinte")

    if status['current_dd'] < -RISK_LIMITS['drawdown_warning']:
        status['alerts'].append("DRAWDOWN WARNING — réduire sizing")
        alert_callback("WARNING: drawdown > 10%")

    return status
```

---

## Rapport Standard

```
═══════════════════════════════════════════════════
QUANT RISK REPORT
Portefeuille : {n_strats} stratégies | Capital : {capital}
═══════════════════════════════════════════════════

RISQUE UNITAIRE
  {tableau par stratégie : VaR / CVaR / MaxDD / Calmar}

CORRÉLATIONS
  {matrice de corrélation}
  Diversification ratio : {div_ratio:.2f}
  Groupes corrélés (|ρ|>0.5) : {groupes}

STRESS TESTS
  {tableau scénarios × métriques}

ALLOCATION RECOMMANDÉE
  {poids par stratégie}
  Daily loss limit : {dll}
  Drawdown warning : {dd_warn} | Drawdown stop : {dd_stop}

VERDICT : GO / AJUSTER / NO GO
═══════════════════════════════════════════════════
```

---

## Interdictions Absolues

- Jamais de position sizing basé sur une seule stratégie sans vue portefeuille
- Jamais d'utilisation du Kelly complet (toujours fractionnel ≤ 0.25)
- Jamais de déploiement sans daily loss limit définie et codée
- Jamais d'ignorance des corrélations en stress (elles convergent vers 1 en crise)
- Jamais de % bruts — log-returns uniquement pour tous les calculs

---

## Intégration Quant Desk

| Section R&D | Apport quant-risk |
|-------------|-----------------|
| S6 Backtest | VaR / CVaR / Calmar par stratégie (Bloc 1) |
| S8 Robustness | Stress tests portefeuille, crisis correlation (Bloc 3) |
| S9 Simulation | Limites de dégradation réalistes avec friction (Bloc 4) |
| S10 Production | Daily loss limit, dynamic sizing, monitoring live (Blocs 4+5) |
