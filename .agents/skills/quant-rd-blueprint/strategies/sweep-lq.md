---
name: sweep-lq
parent_skill: quant-rd-blueprint
description: >
  Skill spécifique à la stratégie SweepLQ. Invoquer ce skill dès que l'utilisateur
  travaille sur cette stratégie : prévalidation d'edge, construction des payloads,
  interprétation des résultats Section 4, ou passage aux sections suivantes.
  Ce skill ne remplace pas quant-rd-blueprint — il le spécialise.
---

# SweepLQ — Stratégie Spécifique

Ce skill s'ancre sur `quant-rd-blueprint/SKILL.md` et encapsule tout ce qui est
spécifique à la stratégie SweepLQ. Le blueprint gère le pipeline générique (Sections
1-10). Ce skill gère les décisions propres à cette stratégie.

---

## 1. Nature de la Stratégie

**Type** : Hybride — trend-following macro + mean reversion micro (pullback directionnel)

```
Échelle macro  →  Biais MTF directionnel      (trend follower)
Échelle micro  →  Sweep LQ + Engulfing        (mean reversion d'entrée)
Alpha réel     →  Timing d'entrée dans la direction du biais via le sweep
```

> Cette nature hybride a des implications directes sur l'interprétation de l'EBTA
> en Section 4. Voir section 4 ci-dessous.

---

## 2. Définition Complète du Signal

### Modules sources (`core.py`)
| Module | Fonction | Rôle |
|--------|----------|------|
| Module 2 | `calculate_market_bias()` | Biais directionnel par TF |
| Module 2 | `calculate_mtf_filter()` | Alignement multi-timeframe |
| Module 3 | `get_stacked_liquidity()` | Pools LQ actifs avec expiry |
| Module 1 | `detect_engulfing()` | Signal d'entrée de retournement |

### Séquence d'entrée LONG (symétrique pour SHORT)

```
Condition 1 — Biais MTF haussier actif
    calculate_mtf_filter(b_h1, b_h4, b_d1) == +1
    Logique : (H1 == H4 != 0) OU (H4 == D1 != 0)

Condition 2 — Pool LQ bull disponible
    bull_pool[i] non vide (au moins 1 niveau actif, non expiré)

Condition 3 — Sweep détecté
    Low[i] <= niveau_pool  →  timer démarre à bougie i

Condition 4 — Confirmation dans la fenêtre
    engulf_bull détecté entre bougie i+1 et i+8 inclus
    →  SIGNAL LONG validé à la bougie de l'engulfing
```

### Paramètres fixes (ne pas optimiser avant Section 6)

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| TF signal | M15 | Timeframe d'exécution |
| Fenêtre confirmation | 8 bougies | ~2h après sweep |
| MTF logique | H1∩H4 OU H4∩D1 | Au moins 2 TF alignés |
| Expiry pools | 3 jours (défaut core.py) | Paramètre `expiry_days` |

---

## 3. Horizons de Mesure — Target Y (Section 4)

Stratégie intraday — horizon max 4h. Tester systématiquement sur **3 horizons** :

| Horizon h | Durée M15 | Signification |
|-----------|-----------|---------------|
| 4 bougies | 1h | Retournement rapide |
| 8 bougies | 2h | Confirmation intraday court |
| 16 bougies | 4h | Horizon intraday maximum |

```python
Y = np.log(df['close'].shift(-h) / df['close'])   # rendement brut forward
# Pas de SL/TP à ce stade — on mesure la direction, pas le trade
```

**Règle d'interprétation** : l'edge doit être visible sur au moins h=4 et h=8.
Un edge qui n'apparaît qu'à h=16 est fragile — le prix "finit par" bouger mais
le signal ne prédit rien à court terme.

---

## 4. Section 4 — Les 4 Payloads à Tester

Toujours tester dans cet ordre. Chaque payload répond à une hypothèse distincte.

### Payload A — Biais seul (benchmark)
```
Signal X  : calculate_mtf_filter() → ±1/0
Condition : aucune
Objectif  : mesurer la valeur du filtre MTF seul
```

### Payload B — Engulfing seul (sans filtre)
```
Signal X  : detect_engulfing() → bull/bear sans condition
Condition : aucune
Objectif  : mesurer la valeur brute du pattern engulfing
```

### Payload C — Engulfing conditionnel au biais
```
Signal X  : engulfing détecté ET biais MTF aligné
Condition : mtf_filter actif
Objectif  : mesurer l'apport du filtre sur le signal d'entrée
```

### Payload D — Signal complet (sweep + fenêtre + engulfing + biais)
```
Signal X  : séquence complète (Conditions 1+2+3+4 toutes validées)
Condition : toutes
Objectif  : mesurer l'edge réel de la stratégie déployée
```

**Lecture des résultats** :

| Résultat | Interprétation |
|----------|----------------|
| A fort, D ≈ A | Le biais fait tout, le Sweep n'ajoute rien → revoir l'entrée |
| A faible, D fort | Le Sweep qualifie bien les entrées → edge réel combiné |
| B fort, C ≈ B | Le filtre MTF n'apporte rien → revoir le filtre |
| D seul fort | Edge complet, toutes les couches contribuent → GO |

---

## 5. EBTA — Interprétation Adaptée

> Le test EBTA standard du blueprint s'applique, mais son interprétation change
> pour cette stratégie hybride.

### Rappel test blueprint
```python
pnl_detrended = (signals.shift(1) * log_ret_detrended).sum()
# Blueprint : pnl_detrended <= 0  →  STOP (profit = biais de position)
```

### Lecture pour SweepLQ

| Résultat | Interprétation standard | Interprétation SweepLQ |
|----------|------------------------|------------------------|
| `pnl_detrended > 0` sur Payload D | Alpha réel confirmé | Le Sweep ajoute de la valeur au-delà du biais MTF |
| `pnl_detrended <= 0` sur Payload D | STOP — biais de position | Le biais MTF explique tout — l'entrée sur Sweep n'apporte rien |
| `pnl_detrended <= 0` sur Payload A | Normal attendu | Le biais seul capture la tendance — c'est son rôle |

**Règle clé** : un STOP sur Payload A n'est pas un échec — c'est la confirmation
que le filtre MTF fait son travail de direction. Le STOP critique est sur Payload D.

> Comparer `pnl_detrended(D) - pnl_detrended(A)` = valeur ajoutée du Sweep.
> Si cette différence est positive et significative → l'entrée sur Sweep a un edge propre.

---

## 6. Points d'Ancrage vers les Skills Transversaux

| Moment | Skill | Raison |
|--------|-------|--------|
| Section 4 — résultats par régime | `quant-regime` | Tester si l'edge tient en trending vs ranging |
| Section 6 — métriques backtest | `quant-risk` | VaR, drawdown attendu sur les trades M15 |
| Section 8 — stress tests | `quant-regime` | Edge conditionnel par session (London/NY) |
| Section 10 — live | `quant-risk` | Daily loss limit, sizing dynamique intraday |

---

## 8. ReportContext — Surcharge des Interprétations HTML

> Contrat défini dans `references/section4-alpha-pipeline.md` § 4.9.
> Ce bloc est passé à `generate_html_report()` pour contextualiser
> les interprétations JS qui seraient trompeuses avec une stratégie hybride.

```python
from pipeline.report import ReportContext

sweep_lq_context = ReportContext(
    strategy_name        = "SweepLQ",
    strategy_type        = "hybrid_pullback",
    alpha_threshold_bps  = 3.0,   # seuil réduit : intraday M15, spread serré

    interp_overrides = {

        # Boxplot — cas alphaL <= 0 sur Payload D
        # Générique : "Signal inversé ou logique d'entrée incorrecte"
        # Problème   : pour SweepLQ, alphaL <= 0 sur D peut signifier que
        #              le biais seul explique la performance, pas une erreur
        "boxplot_nogo": (
            "Le biais MTF explique la performance — le Sweep n'ajoute pas "
            "d'alpha d'entrée propre. Comparer avec Payload A avant de "
            "conclure à une erreur de logique."
        ),

        # Boxplot — cas alphaL faible (0 < alphaL < threshold)
        # Générique : "Alpha insuffisant — renforcer les conditions d'entrée"
        # Problème   : peut être un vrai signal faible OU signal dilué par
        #              les bars hors-fenêtre (sweep sans engulfing dans les 8 bougies)
        "boxplot_weak": (
            "Alpha net sous le seuil. Vérifier d'abord le taux de conversion "
            "sweep→engulfing : si < 30% des sweeps produisent un engulfing dans "
            "la fenêtre, la dilution explique la faiblesse — pas le signal lui-même."
        ),

        # Rolling fragile
        # Générique : "Identifier la variable de régime corrélant avec les zones positives"
        # Ajout      : préciser quelle variable de régime est pertinente pour SweepLQ
        "rolling_fragile": (
            "Edge régime-dépendant. Pour SweepLQ, tester en priorité : "
            "(1) session London/NY vs Asia, "
            "(2) volatilité ATR relative (forte vs faible), "
            "(3) alignement D1 présent ou absent. "
            "[→ quant-regime] pour segmentation complète par régime."
        ),

        # Radar — Discrimination manquante (Step 2 échoue)
        # Générique : "Revoir les conditions de sortie ou l'horizon H"
        # Problème   : pour un signal événementiel (sweep+engulfing), l'horizon
        #              H est plus critique que les conditions de sortie
        "radar_discrimination": (
            "Le signal ne sépare pas suffisamment les distributions. "
            "Pour SweepLQ : tester h=4 et h=8 avant de revoir la logique. "
            "Un Sweep sans engulfing dans la fenêtre crée du bruit — "
            "vérifier que les bars sans signal sont bien exclus du calcul."
        ),

        # Radar — Exploitabilité manquante (Step 3 échoue)
        # Générique : "Ajuster les seuils d'entrée ou l'horizon H"
        # Ajout      : orienter vers la comparaison inter-payloads
        "radar_exploitability": (
            "Edge statistique présent mais pas encore tradable. "
            "Comparer le Q1-Q5 de ce payload avec Payload A (biais seul) : "
            "si A est déjà non-monotone, l'issue est dans le filtre MTF, "
            "pas dans le Sweep."
        ),
    }
)
```

### Règle d'utilisation

Passer ce contexte à chaque appel de rapport pour les 4 payloads :

```python
generate_html_report(
    all_results,
    tf             = "15min",
    horizon_h      = 8,
    report_context = sweep_lq_context,   # ← injecté ici
    output_dir     = "Reports",
)
```

Le rapport HTML affiche les overrides **uniquement si le cas correspondant
est atteint** — les interprétations génériques restent actives pour tous
les autres cas non surchargés.

---

## 7. Checklist GO / NO GO Spécifique

Avant de passer à la Section 5, valider :

- [ ] Payload D : Steps 0+1+2+3 tous validés sur au moins 2 horizons (h=4 et h=8)
- [ ] EBTA : `pnl_detrended(D) > pnl_detrended(A)` — le Sweep ajoute de l'alpha
- [ ] Payload D bat Payload A sur Spearman IC (le signal complet > biais seul)
- [ ] Shuffle control : rho < 0.03 sur Payload D
- [ ] Edge visible sur au moins 2 des 3 horizons (h=4, h=8, h=16)
- [ ] n_signals Payload D >= 100 (sinon données insuffisantes)
