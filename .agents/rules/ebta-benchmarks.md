# EBTA Benchmarks — Référence Complète

Source : Aronson, D. (2007). *Evidence-Based Technical Analysis*. Wiley. Pages 23-29.

---

## 1. Le problème fondamental

La performance d'un backtest est une combinaison de **trois facteurs indépendants** :

```
Performance = Pouvoir prédictif réel
            + Biais de position (Position Bias)
            + Tendance nette du marché (Market Net Trend)
```

Un trader peut croire avoir un alpha alors qu'il capture simplement la tendance via un biais
d'exposition. C'est particulièrement dangereux pour les stratégies trend-following testées
sur des marchés structurellement haussiers (ex: indices actions 2010-2023).

---

## 2. Calcul du biais de position

### Formule EBTA

```
ER = [p(Long) × ADC] − [p(Short) × ADC]
```

Où :
- `ER` = Expected Return du hasard (rendement attendu sans pouvoir prédictif)
- `p(Long)` = probabilité d'être en position longue = nb_barres_long / nb_barres_total
- `p(Short)` = probabilité d'être en position courte
- `ADC` = Average Daily Change = moyenne des rendements journaliers sur la période

### Interprétation

| Valeur ER | Signification |
|-----------|--------------|
| ER > 0 | La strat est biaisée long sur un marché haussier |
| ER < 0 | La strat est biaisée short sur un marché baissier |
| ER ≈ 0 | Pas de biais — ou marché sans tendance nette |

**Règle** : Soustraire ER du PnL observé pour obtenir le "True Alpha" :
```
True Alpha = PnL_observé - ER
```

---

## 3. Méthode de détrendage (Detrending)

### Principe

Transformer la série de prix pour que l'ADC soit exactement zéro.
Quand ADC = 0 : ER = [p(L) × 0] − [p(S) × 0] = 0 pour **toutes** les règles.
→ Tout profit sur données détrendées est de l'alpha pur.

### Implémentation sur log-returns

```python
import numpy as np
import pandas as pd

def compute_log_returns(df: pd.DataFrame) -> pd.Series:
    """Standard : log(close_t / close_t-1)"""
    return np.log(df['close'] / df['close'].shift(1)).dropna()

def detrend_log_returns(log_returns: pd.Series) -> pd.Series:
    """
    Soustrait le rendement moyen de chaque observation.
    Résultat : série avec moyenne exactement nulle.
    """
    adc = log_returns.mean()
    return log_returns - adc

def reconstruct_detrended_prices(df: pd.DataFrame,
                                  log_returns_detrended: pd.Series) -> pd.Series:
    """
    Reconstruire une série de prix à partir de log-returns détrendés.
    Utile pour visualiser le marché "sans tendance".
    """
    prices_detrended = df['close'].iloc[0] * np.exp(log_returns_detrended.cumsum())
    return prices_detrended
```

### Règle critique : séparer signal et P&L

```python
# CORRECT — EBTA compliant
signals = generate_signal(df_real)          # signaux sur données RÉELLES
pnl     = (signals.shift(1) * log_returns_detrended).sum()  # P&L sur DÉTRENDÉES

# INCORRECT — biais latent
signals = generate_signal(df_detrended)     # ne jamais détrendre avant le signal
```

---

## 4. Pourquoi les log-returns et pas les pourcentages

| Propriété | % simples | Log-returns |
|-----------|-----------|-------------|
| Additivité temporelle | ❌ | ✅ |
| Symétrie gain/perte | ❌ (+10% puis -10% ≠ 0) | ✅ |
| Détrendage propre | ❌ | ✅ |
| Validité tests stat | ⚠️ | ✅ |

```python
# Mauvais : rendements asymétriques
ret_pct = df['close'].pct_change()   # +10% et -9.09% ne s'annulent pas

# Bon : log-returns symétriques
ret_log = np.log(df['close'] / df['close'].shift(1))  # +0.0953 et -0.0953 s'annulent
```

---

## 5. Cas limites et pièges

### Piège 1 — Marchés à fort trend unidirectionnel
Sur un bull market de 10 ans, même un lancer de pièce biaisé long est profitable.
→ Toujours tester en détrendant sur la période COMPLÈTE, pas juste IS.

### Piège 2 — Filtre régime qui "améliore" en IS
Un filtre régime peut sembler améliorer les résultats en IS simplement parce qu'il
augmente l'exposition dans les sous-périodes les plus haussières.
→ Appliquer EBTA compliance séparément sur chaque régime détecté.

### Piège 3 — Données courtes
Sur < 1 an de données, l'ADC n'est pas stable → le détrendage peut sur-corriger.
→ Minimum 2 ans de données, idéalement couvrant au moins un cycle complet.

### Piège 4 — Stratégies asymétriques (long-only)
Pour une stratégie long-only : p(Short) = 0, donc ER = p(Long) × ADC.
Sur un marché haussier, ER peut représenter 80%+ du profit total.
→ Particulièrement critique de vérifier le True Alpha.

---

## 6. Template de rapport EBTA

```
EBTA COMPLIANCE REPORT
─────────────────────────────────────
Période testée     : {start} → {end}
Nombre de barres   : {n}
Asset              : {symbol}

TENDANCE DU MARCHÉ
  ADC (log-return moyen)  : {adc:.6f}
  Tendance cumulée        : {(np.exp(adc * n) - 1) * 100:.1f}%

EXPOSITION DE LA STRATÉGIE  
  % du temps Long         : {p_long:.1%}
  % du temps Short        : {p_short:.1%}
  % du temps Flat         : {p_flat:.1%}
  Biais de position       : {'Long' if p_long > p_short else 'Short' if p_short > p_long else 'Neutre'}

DÉCOMPOSITION DE LA PERFORMANCE
  PnL brut (log)          : {pnl_real:.4f}
  ER du hasard            : {er_chance:.4f}  ({er_chance/pnl_real*100:.1f}% du PnL)
  True Alpha              : {true_alpha:.4f}  ({true_alpha/pnl_real*100:.1f}% du PnL)
  PnL détrendé            : {pnl_detrended:.4f}

VERDICT
  EBTA PASS  ✅  →  alpha réel confirmé
  EBTA FAIL  ❌  →  performance = biais de position — rejeter la stratégie
─────────────────────────────────────
```
