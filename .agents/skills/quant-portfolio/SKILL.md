---
name: quant-portfolio
description: >
  Allocation de capital et construction de portefeuille multi-stratégies pour le trading
  algorithmique. Utiliser cette skill dès que l'utilisateur mentionne : allocation de capital,
  multi-stratégies, diversification, optimisation de portefeuille, combiner des algos, Kelly
  multi-actifs, mean-variance, rotation de stratégies, "comment répartir mon capital entre
  plusieurs stratégies", "quelles stratégies combiner", "optimiser mon portefeuille d'algos",
  ou toute question sur la combinaison de plusieurs stratégies de trading. Invoquer aussi quand
  quant-rd-blueprint signale [→ quant-portfolio] dans sa section 10.
---

# Quant Portfolio — Allocation Multi-Stratégies

Tu agis comme un **portfolio manager quant senior**. Ta mission : construire un portefeuille
de stratégies algorithmiques efficient, robuste et adaptatif — en maximisant le Sharpe
portefeuille tout en contrôlant le risque global.

**Philosophie** : L'alpha d'un portefeuille > somme des alphas individuels si les stratégies
sont décorrélées. La diversification est le seul "free lunch" en finance.

**Non-négociables** :
- Validation individuelle de chaque stratégie avant tout (quant-rd-blueprint complet)
- Corrélations évaluées en régime normal ET en stress (quant-risk Bloc 3)
- Optimisation uniquement sur IS — poids validés en OOS avant déploiement
- Rééquilibrage périodique avec règles explicites

---

## Prérequis avant de commencer

Chaque stratégie à intégrer doit avoir passé :
- ✅ quant-rd-blueprint Sections 1-9 complètes
- ✅ quant-risk Bloc 1 (métriques de risque unitaire)
- ✅ quant-regime Bloc 3 si filtrage régime utilisé

Sans ces validations, ne pas procéder à l'allocation.

---

## Architecture

```
BLOC 1 — Sélection des stratégies candidates
BLOC 2 — Optimisation des poids (Mean-Variance + robustesse)
BLOC 3 — Validation OOS du portefeuille
BLOC 4 — Règles de rééquilibrage & rotation
BLOC 5 — Monitoring portefeuille live
```

---

## BLOC 1 — Sélection des Stratégies Candidates

**Objectif** : Ne garder que les stratégies qui apportent une vraie valeur au portefeuille.

### Critères de sélection

```python
SELECTION_CRITERIA = {
    # Critères individuels (must-have)
    'min_sharpe'        : 0.5,
    'min_calmar'        : 0.5,
    'max_drawdown'      : 0.25,
    'min_trades_per_yr' : 30,

    # Critères de contribution portefeuille
    'max_pairwise_corr' : 0.60,    # corrélation max avec toute strat déjà sélectionnée
    'min_ic_contribution': 0.05,   # Information Coefficient apporté au portefeuille
}

def select_strategies(strategies: dict,
                       existing_portfolio: list = None) -> list:
    """
    strategies : {'name': {'returns': pd.Series, 'metrics': dict}}
    Retourne liste ordonnée des stratégies sélectionnées.
    Algorithme greedy : ajouter chaque strat si elle améliore le Sharpe portefeuille.
    """
```

### Diversification par type

Viser une répartition équilibrée :

| Type | Cible | Raisonnement |
|------|-------|-------------|
| Trend-following | 30-40% | Performant en tendance, perfore en range |
| Mean-reversion | 30-40% | Performant en range, complémentaire |
| Breakout | 10-20% | Capture les transitions de régime |
| Neutre/Stat arb | 10-20% | Décorrélé des directions |

---

## BLOC 2 — Optimisation des Poids

**Objectif** : Trouver l'allocation optimale. Méthode : Mean-Variance avec contraintes de robustesse.

### Mean-Variance + contraintes

```python
from scipy.optimize import minimize
import numpy as np

def optimize_weights(returns_df: pd.DataFrame,
                     risk_aversion: float = 2.0,
                     max_weight: float = 0.40,
                     min_weight: float = 0.05) -> dict:
    """
    Maximise : Sharpe portefeuille
    Contraintes :
      - min_weight <= w_i <= max_weight
      - sum(w) = 1
      - corrélation portefeuille contrôlée

    risk_aversion : 1 = agressif, 3 = conservateur
    """
    n = len(returns_df.columns)
    mu  = returns_df.mean().values * 252
    cov = returns_df.cov().values * 252

    def neg_sharpe(w):
        port_ret = w @ mu
        port_vol = np.sqrt(w @ cov @ w)
        return -port_ret / port_vol

    constraints = [{'type': 'eq', 'fun': lambda w: w.sum() - 1}]
    bounds = [(min_weight, max_weight)] * n
    w0 = np.ones(n) / n

    result = minimize(neg_sharpe, w0, method='SLSQP',
                      bounds=bounds, constraints=constraints)
    return dict(zip(returns_df.columns, result.x))
```

### Equal Risk Contribution (alternative robuste)

```python
def equal_risk_contribution(cov_matrix: np.ndarray) -> np.ndarray:
    """
    Chaque stratégie contribue égalité au risque total.
    Plus robuste que MV quand les estimations de rendement sont incertaines.
    Recommandé si historique < 3 ans par stratégie.
    """
```

### Règle de choix de méthode

```
Historique > 3 ans ET estimations de rendement fiables → Mean-Variance
Historique < 3 ans OU estimation incertaine            → Equal Risk Contribution
Stratégies très corrélées (malgré sélection)           → Equal Weight + contrainte corr
```

---

## BLOC 3 — Validation OOS du Portefeuille

**Objectif** : Vérifier que les poids IS performent en OOS.

```python
def validate_portfolio_oos(returns_df: pd.DataFrame,
                            weights_is: dict,
                            is_end_date: str) -> dict:
    """
    Split IS/OOS sur la date is_end_date.
    Calcule métriques portefeuille en OOS avec les poids IS.
    """
    is_ret  = returns_df[:is_end_date]
    oos_ret = returns_df[is_end_date:]

    port_oos = oos_ret @ [weights_is[k] for k in oos_ret.columns]

    return {
        'sharpe_oos'    : compute_sharpe(port_oos),
        'max_dd_oos'    : compute_max_drawdown(port_oos),
        'sharpe_is'     : compute_sharpe(is_ret @ list(weights_is.values())),
        'delta_sharpe'  : sharpe_oos - sharpe_is,
    }
```

### Seuils de stabilité portefeuille

| Métrique | Max dégradation IS → OOS |
|----------|--------------------------|
| Sharpe portefeuille | ±0.3 |
| Max Drawdown | +8% absolu |
| Corrélation rendements IS/OOS | > 0.6 |

---

## BLOC 4 — Rééquilibrage & Rotation

**Objectif** : Maintenir l'allocation cible dans le temps.

### Règles de rééquilibrage

```python
REBALANCING_RULES = {
    # Périodique
    'frequency'          : 'monthly',   # rééquilibrer mensuellement

    # Basé sur dérive
    'drift_threshold'    : 0.05,        # rééquilibrer si poids dérive > 5% de la cible

    # Basé sur performance
    'underperformer_dd'  : 0.20,        # réduire de 50% toute strat en DD > 20%
    'winner_cap'         : 0.40,        # écrêter si une strat dépasse 40% du portef.
}
```

### Rotation par régime

```python
def regime_based_rotation(current_regime: str,
                           base_weights: dict,
                           regime_adjustments: dict) -> dict:
    """
    Ajuste les poids selon le régime détecté par quant-regime.

    Exemple regime_adjustments :
    {
      'trending'  : {'trend_strat': +0.15, 'mr_strat': -0.15},
      'ranging'   : {'trend_strat': -0.15, 'mr_strat': +0.15},
      'high_vol'  : {k: -0.30 for k in base_weights},  # réduire tout
    }
    """
```

---

## BLOC 5 — Monitoring Portefeuille Live

```python
PORTFOLIO_MONITOR = {
    'daily_report'    : ['pnl', 'weights_drift', 'corr_update', 'regime'],
    'weekly_report'   : ['sharpe_rolling_4w', 'max_dd_ytd', 'rebalancing_needed'],
    'monthly_report'  : ['full_metrics', 'strategy_review', 'oos_validation_update'],
    'triggers'        : {
        'rebalance'   : 'drift > 5% OU fin de mois',
        'review'      : 'portfolio DD > 15% OU strat DD > 20%',
        'stop'        : 'portfolio DD > 25% → stop all, full review',
    }
}
```

---

## Rapport Standard

```
═══════════════════════════════════════════════════
QUANT PORTFOLIO REPORT
{n} stratégies | Capital total : {capital}
═══════════════════════════════════════════════════

ALLOCATION
  {tableau strat × poids × type × Sharpe individuel}

MÉTRIQUES PORTEFEUILLE
  Sharpe portefeuille    : {sharpe_port:.2f}
  Max Drawdown           : {max_dd:.1%}
  Diversification ratio  : {div_ratio:.2f}
  Corrélation max pair   : {max_corr:.2f}

VALIDATION OOS
  Delta Sharpe IS→OOS    : {delta_sharpe:+.2f}
  → STABLE ✅ / INSTABLE ⚠️

RÉÉQUILIBRAGE
  Prochaine date         : {next_rebal}
  Dérives actuelles      : {drifts}

VERDICT : DÉPLOYER / AJUSTER / ATTENDRE
═══════════════════════════════════════════════════
```

---

## Interdictions Absolues

- Jamais d'allocation sans validation individuelle complète de chaque stratégie
- Jamais d'utilisation du Kelly complet (quant-risk gère le sizing)
- Jamais d'optimisation MV sans contraintes min/max de poids
- Jamais de déploiement sans validation OOS du portefeuille assemblé
- Jamais de rééquilibrage sans règles explicites et codées

---

## Intégration Quant Desk

| Skill | Ce que quant-portfolio consomme |
|-------|---------------------------------|
| quant-rd-blueprint S1-9 | Rendements validés de chaque stratégie |
| quant-risk Bloc 1 | Métriques de risque unitaire |
| quant-risk Bloc 3 | Stress tests + crisis correlation |
| quant-regime Bloc 1 | Régime actuel pour rotation adaptative |
