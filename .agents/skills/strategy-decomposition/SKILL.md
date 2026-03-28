---
name: strategy-decomposition-agent
parent_skill: quant-rd-blueprint
mode: agentic
description: >
  Version IDE agentique du skill strategy-decomposition.
  L'agent exécute toutes les étapes de manière autonome sans interaction
  utilisateur. Il lit les fichiers sources pour classifier la stratégie,
  écrit les fichiers produits sur disque, et génère un rapport d'exécution.
  Stopper et écrire NEEDS_REVIEW.md si une ambiguïté bloque la classification.
---

# Strategy Decomposition — Version IDE Agentique

L'agent exécute ce skill de A à Z sans interaction utilisateur.
Chaque étape lit des fichiers en entrée et écrit des fichiers en sortie.
En cas d'ambiguïté non résolvable → écrire NEEDS_REVIEW.md et stopper.

---

## PROTOCOLE D'EXÉCUTION GÉNÉRAL

```
RÈGLE 1 — Lire avant d'écrire
  Toujours lire un fichier existant avant de le modifier.
  Ne jamais réécrire un fichier entier si seule une section change.

RÈGLE 2 — Fichier existant = modifier, absent = créer
  Si le fichier cible existe sur disque → modifier uniquement les sections concernées
  Si le fichier cible est absent        → créer from scratch selon les templates

RÈGLE 3 — Traçabilité obligatoire
  Écrire STEP_[N]_SUMMARY.md après chaque étape réussie
  Écrire NEEDS_REVIEW.md et stopper si une ambiguïté est détectée

RÈGLE 4 — Ne jamais toucher au moteur
  alpha_engine.py  →  jamais modifié
  pipeline/report.py → jamais modifié
  Les autres stratégies existantes → jamais modifiées
```

---

## ÉTAPE 0 — Inventaire des fichiers disponibles

L'agent commence par scanner le projet pour localiser les fichiers pertinents.

### Fichiers à chercher

```
OBLIGATOIRES — stopper si absents :
  .agents/skills/quant-rd-blueprint/references/section4-alpha-pipeline.md
  pipeline/report_synthesis.py

SOURCES DE CLASSIFICATION — lire dans cet ordre de priorité :
  1. strategies/[nom].md          si présent → stratégie déjà partiellement définie
  2. strategies/[nom].py          si présent → inférer depuis le code
  3. core.py ou fichiers sources  si présents → inférer depuis les features

OPTIONNELS :
  .agents/skills/quant-rd-blueprint/strategies/[nom].md
```

### Output de l'étape 0

Écrire `STEP_0_SUMMARY.md` :
```
# Inventaire fichiers — Étape 0

## Fichiers obligatoires
  section4-alpha-pipeline.md : [TROUVÉ / MANQUANT]
  report_synthesis.py        : [TROUVÉ / MANQUANT]

## Sources de classification disponibles
  [liste des fichiers trouvés avec chemin]

## Stratégie déjà partiellement définie ?
  [OUI → nom détecté | NON → création from scratch]

## Décision
  [CONTINUER | STOPPER → raison]
```

Si un fichier obligatoire est MANQUANT → ajouter dans NEEDS_REVIEW.md et stopper.

---

## ÉTAPE 1 — Classification de la Stratégie

### 1.1 Extraction automatique depuis les fichiers sources

L'agent lit les fichiers sources dans l'ordre de priorité défini à l'Étape 0
et extrait les indices de classification suivants :

```
INDICES À EXTRAIRE :

Signal d'entrée
  → chercher : engulfing, RSI, EMA, crossover, breakout, channel,
               sweep, liquidité, niveau, pattern, divergence

Filtre directionnel
  → chercher : bias, biais, mtf, trend_filter, direction,
               higher_timeframe, regime, session

Structure conditionnelle
  → compter le nombre de conditions (AND) requises pour un signal
  → 1 condition = signal simple | 2+ conditions = signal composite

Horizon temporel
  → chercher : timeframe, tf, minutes, hours dans les paramètres
  → déduire la durée typique depuis les noms de variables

Comportement prix
  → chercher : reversion, mean_rev, oversold, overbought → MEAN_REVERSION
  → chercher : sweep, liquidity, pool, level, bounce   → HYBRID_PULLBACK
  → chercher : breakout, break, channel, range_high    → HYBRID_BREAKOUT
  → chercher : trend, follow, momentum, ema_cross      → TREND_FOLLOWING
  → chercher : session, open, news, event, spike       → EVENT_DRIVEN
```

### 1.2 Arbre de décision automatique

```
ÉTAPE A — Comportement prix dominant détecté ?
  reversion / oversold / overbought → MEAN_REVERSION          → aller 1.3
  sweep / liquidity / pool / bounce → candidat HYBRID_PULLBACK → aller ÉTAPE B
  breakout / channel / range        → candidat HYBRID_BREAKOUT → aller ÉTAPE C
  trend / ema_cross / momentum      → candidat TREND_FOLLOWING → aller ÉTAPE D
  session / news / event            → EVENT_DRIVEN             → aller 1.3
  aucun indice clair                → écrire NEEDS_REVIEW.md   → STOPPER

ÉTAPE B — Filtre directionnel présent ?
  OUI (bias / mtf / direction trouvé) → HYBRID_PULLBACK        → aller 1.3
  NON                                 → MEAN_REVERSION         → aller 1.3

ÉTAPE C — Signal de confirmation présent ?
  OUI (engulfing / volume / pattern)  → HYBRID_BREAKOUT        → aller 1.3
  NON                                 → TREND_FOLLOWING        → aller 1.3

ÉTAPE D — Plusieurs conditions AND requises ?
  OUI                                 → HYBRID_BREAKOUT        → aller 1.3
  NON                                 → TREND_FOLLOWING        → aller 1.3
```

### 1.3 Table des types et implications

| Type | Seuil alpha bps | Implication EBTA |
|------|----------------|-----------------|
| `hybrid_pullback` | 3.0 | pnl_detrended(D) > pnl_detrended(A) |
| `mean_reversion` | 5.0 | pnl_detrended > 0 standard |
| `trend_following` | 2.0 | Comparer vs buy-and-hold |
| `hybrid_breakout` | 4.0 | pnl_detrended > 0 sur signal filtré |
| `event_driven` | 5.0 | pnl_detrended > 0 standard |

### 1.4 Seuil de confiance

```
Indices trouvés >= 3 pointant vers le même type → classification CONFIRMÉE
Indices trouvés == 2 pointant vers le même type → classification PROBABLE
  → continuer mais noter "confiance partielle" dans STEP_1_SUMMARY.md
Indices trouvés <= 1 ou contradictoires         → écrire NEEDS_REVIEW.md
  → STOPPER
```

### Output de l'étape 1

Écrire `STEP_1_SUMMARY.md` :
```
# Classification — Étape 1

## Type détecté
  [TYPE] — confiance : [CONFIRMÉE / PROBABLE]

## Indices trouvés
  [liste des indices extraits avec fichier source + ligne]

## Implications
  alpha_threshold_bps : [valeur]
  Interprétation EBTA : [règle]

## Décision
  [CONTINUER | STOPPER → raison]
```

---

## ÉTAPE 2 — Décomposition en Payloads

### 2.1 Principe universel

```
Payload A — Couche la plus macro (filtre / biais / régime)
Payload B — Signal brut sans aucun filtre
Payload C — Signal conditionnel au filtre (A + B)
Payload D — Signal complet (toutes conditions réunies)
```

Si une seule couche détectée → Payload A = D, B et C = None.

### 2.2 Extraction automatique des couches

L'agent identifie les couches depuis le code source :

```
COUCHE MACRO (→ Payload A)
  Chercher les conditions appliquées EN PREMIER ou EN AMONT du signal :
  fonctions retournant ±1/0 sur plusieurs TF, filtres de régime, biais

COUCHE SIGNAL BRUT (→ Payload B)
  Chercher le pattern ou indicateur central sans condition externe :
  fonctions de détection de pattern (engulfing, RSI cross, breakout)

COUCHE INTERMÉDIAIRE (→ Payload C)
  Chercher la combinaison A ET B :
  conditions imbriquées (if bias == 1 AND signal == 1)

COUCHE COMPLÈTE (→ Payload D)
  Chercher toutes les conditions réunies :
  séquences temporelles, fenêtres d'attente, niveaux de prix supplémentaires
```

### 2.3 Règles de décomposition par type

**HYBRID_PULLBACK**
```
A → filtre directionnel seul
B → pattern d'entrée seul (engulfing, bougie)
C → pattern conditionnel au filtre
D → filtre + niveau LQ/support + fenêtre d'attente + pattern
```

**MEAN_REVERSION**
```
A → condition extrême seule (RSI < seuil, z-score < seuil)
B → signal de retournement seul (divergence, pattern)
C → A + B combinés
D → C + filtre volatilité/régime si présent, sinon D = C
```

**TREND_FOLLOWING**
```
A → signal de tendance seul (EMA cross, ADX > seuil)
B → confirmation seule si présente (volume, momentum)
C → A + B combinés, sinon C = A
D → C + filtre de régime si présent, sinon D = C
```

**HYBRID_BREAKOUT**
```
A → détection breakout seul
B → signal de confirmation seul
C → A + B combinés
D → C + filtre directionnel si présent, sinon D = C
```

**EVENT_DRIVEN**
```
A → événement seul
B → signal post-événement seul
C → A + B combinés
D → C + contexte supplémentaire si présent, sinon D = C
```

### 2.4 Définition automatique des horizons Y

```
Extraire le timeframe signal depuis le code source (paramètre tf ou tf_minutes)

Durée trade estimée depuis le timeframe :
  TF <= 5min  → scalp   → h = 2, 4, 8
  TF <= 15min → intraday court  → h = 4, 8, 16
  TF <= 60min → intraday long   → h = 8, 16, 32
  TF > 60min  → swing           → h = 1, 2, 5 (jours)

Si timeframe non trouvé → utiliser h = 4, 8, 16 par défaut
  et noter dans STEP_2_SUMMARY.md
```

### Output de l'étape 2

Écrire `STEP_2_SUMMARY.md` :
```
# Décomposition Payloads — Étape 2

## Payloads définis
  A : [description du signal X + source code]
  B : [description du signal X + source code]
  C : [description du signal X + source code]
  D : [description du signal X + source code]
  Payloads skippés (D=C etc.) : [liste si applicable]

## Horizons Target Y
  TF signal détecté : [valeur ou "non trouvé"]
  Horizons retenus  : h = [X, Y, Z]

## Table de lecture des résultats
  [générée selon les règles Section 3 du skill parent]

## Décision
  [CONTINUER | STOPPER → raison]
```

---

## ÉTAPE 3 — Création ou Mise à Jour de strategies/[nom].md

### 3.1 Déterminer le nom du fichier

```
Si un fichier strategies/[nom].py existe → utiliser [nom] en kebab-case
Si un fichier strategies/[nom].md existe → utiliser le même nom
Sinon → inférer depuis le nom de la classe Strategy trouvée dans le code
  ex: class SweepLQStrategy → sweep-lq.md
  ex: class RSIMeanRevStrategy → rsi-mean-rev.md
```

### 3.2 Si le fichier existe — sections à mettre à jour

```
Sections à mettre à jour uniquement si leur contenu a changé :
  Section 3 — Horizons (si nouveaux horizons détectés)
  Section 4 — Payloads (si décomposition modifiée)
  Section 5 — EBTA (si type de stratégie modifié)
  Section 7 — Checklist GO/NO GO (si payloads modifiés)
  Section 8 — ReportContext (toujours synchroniser avec Étape 4)

Sections à ne jamais modifier sans raison explicite :
  Section 1 — Nature (stable une fois classifiée)
  Section 2 — Définition du signal (stable si code non modifié)
  Section 6 — Points d'ancrage (stable)
```

### 3.3 Si le fichier est absent — créer complet

Utiliser ce template en substituant toutes les variables entre [crochets] :

```markdown
---
name: [nom-kebab-case]
parent_skill: quant-rd-blueprint
description: >
  Skill spécifique à la stratégie [NomStratégie]. Invoquer dès que
  l'utilisateur travaille sur cette stratégie : prévalidation d'edge,
  construction des payloads, interprétation Section 4, passage Section 5.
---

# [NomStratégie] — Stratégie Spécifique

## 1. Nature de la Stratégie
**Type** : [type_détecté] — [description en une ligne]

[Si hybride, décrire les deux échelles :]
Échelle macro → [description couche macro]
Échelle micro → [description couche signal]
Alpha réel    → [description de la combinaison]

## 2. Définition Complète du Signal
### Modules sources
| Module | Fonction | Rôle |
|--------|----------|------|
[extraire depuis le code source]

### Séquence d'entrée LONG (symétrique SHORT)
[Conditions numérotées extraites depuis le code]

### Paramètres fixes (ne pas optimiser avant Section 6)
| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
[extraire depuis le code source]

## 3. Horizons de Mesure — Target Y
| Horizon h | Durée | Signification |
|-----------|-------|---------------|
[remplir depuis STEP_2_SUMMARY.md]

**Règle** : l'edge doit être visible sur au moins les 2 premiers horizons.

## 4. Les Payloads à Tester
### Payload A — [nom court]
Signal X  : [description]
Condition : [aucune / description]
Objectif  : [mesurer quoi ?]

### Payload B — [nom court]
[idem]

### Payload C — [nom court]
[idem]

### Payload D — Signal complet
[idem]

**Table de lecture des résultats** :
| Résultat | Interprétation |
|----------|----------------|
[remplir depuis STEP_2_SUMMARY.md]

## 5. EBTA — Interprétation Adaptée
### Rappel test blueprint
pnl_detrended = (signals.shift(1) * log_ret_detrended).sum()

### Lecture pour [NomStratégie]
| Résultat | Interprétation standard | Interprétation [NomStratégie] |
|----------|------------------------|-------------------------------|
[adapter selon le type détecté en Section 1.3]

## 6. Points d'Ancrage vers les Skills Transversaux
| Moment | Skill | Raison |
|--------|-------|--------|
| Section 4 — résultats par régime | quant-regime | [raison spécifique] |
| Section 6 — métriques backtest   | quant-risk   | [raison spécifique] |
| Section 8 — stress tests         | quant-regime | [raison spécifique] |
| Section 10 — live                | quant-risk   | [raison spécifique] |

## 7. Checklist GO / NO GO Spécifique
- [ ] Payload D : Steps 0+1+2+3 validés sur au moins 2 horizons
- [ ] EBTA : [condition spécifique au type]
- [ ] Payload D bat Payload A sur Spearman IC
- [ ] Shuffle control : rho < 0.03 sur Payload D
- [ ] Edge visible sur au moins 2 des 3 horizons
- [ ] n_signals Payload D >= 100

## 8. ReportContext
[insérer le ReportContext complet généré à l'Étape 4]
```

### Output de l'étape 3

Écrire le fichier `strategies/[nom].md` sur disque.
Écrire `STEP_3_SUMMARY.md` :
```
# Fichier Stratégie — Étape 3

## Action effectuée
  [CRÉÉ / MODIFIÉ] : strategies/[nom].md

## Sections touchées
  [liste des sections créées ou mises à jour]

## Sections inchangées
  [liste]
```

---

## ÉTAPE 4 — Mise à Jour de section4-alpha-pipeline.md

### 4.1 Section à modifier

Modifier uniquement le tableau de la section § 4.9 :
```
| Stratégie | Fichier skill | strategy_type | alpha_threshold_bps |
```

### 4.2 Règle d'insertion

```
Si la stratégie est déjà dans le tableau → mettre à jour la ligne
Si la stratégie est absente              → ajouter une ligne à la fin

Format de la ligne :
| [NomStratégie] | strategies/[nom].md | [type_détecté] | [seuil_bps] |
```

### 4.3 Ne jamais modifier

```
Toutes les autres sections de section4-alpha-pipeline.md sont en lecture seule.
Ne modifier QUE le tableau § 4.9.
```

### Output de l'étape 4

Écrire `section4-alpha-pipeline.md` mis à jour sur disque.
Écrire `STEP_4_SUMMARY.md` :
```
# section4-alpha-pipeline.md — Étape 4

## Action
  [AJOUT / MISE À JOUR] ligne : [NomStratégie]

## Ligne écrite
  | [NomStratégie] | strategies/[nom].md | [type] | [seuil] |
```

---

## ÉTAPE 5 — Mise à Jour de report_synthesis.py

### 5.1 Localiser les blocs à modifier

Dans `report_synthesis.py`, chercher les patterns suivants :

```python
# Pattern 1 — ReportContext existant pour ce type
# Chercher : strategy_type = "[type_détecté]"
# Si trouvé → mettre à jour les overrides

# Pattern 2 — Bloc de sélection du contexte selon la stratégie
# Chercher : if strategy_name == "[NomStratégie]"
# ou        : CONTEXTS = { "[NomStratégie]": ReportContext(...) }
# Si trouvé → mettre à jour
# Si absent → ajouter l'entrée
```

### 5.2 ReportContext à injecter

Utiliser le ReportContext du type détecté depuis la Section 3 du skill parent :

```python
# Substituer [NomStratégie] et [type_détecté] avec les valeurs réelles
ReportContext(
    strategy_name        = "[NomStratégie]",
    strategy_type        = "[type_détecté]",
    alpha_threshold_bps  = [seuil_bps],
    interp_overrides     = {
        # Copier les overrides du type depuis Section 3 du skill parent
        # Adapter les messages pour nommer la stratégie explicitement
    }
)
```

### 5.3 Contrainte critique — apostrophes JS

```
TOUTES les strings JS dans la f-string Python
doivent utiliser l'apostrophe typographique ' (U+2019)
JAMAIS l'apostrophe droite '

Avant d'écrire report_synthesis.py :
  Vérifier chaque nouvelle string JS ajoutée
  Remplacer automatiquement ' par ' dans les nouveaux blocs uniquement
  Ne pas toucher aux blocs existants (risque de régression)
```

### Output de l'étape 5

Écrire `report_synthesis.py` mis à jour sur disque.
Écrire `STEP_5_SUMMARY.md` :
```
# report_synthesis.py — Étape 5

## Action
  [AJOUT / MISE À JOUR] ReportContext pour [NomStratégie]

## Blocs modifiés
  [liste des lignes ou fonctions touchées]

## Blocs inchangés
  [confirmation que le reste est intact]

## Vérification apostrophes
  [OK — aucune apostrophe droite dans les nouveaux blocs]
```

---

## ÉTAPE 6 — Checklist de Cohérence et Rapport Final

### 6.1 Vérifications automatiques

```
COHÉRENCE INTER-FICHIERS
  □ Nom stratégie identique dans strategies/[nom].md,
    section4-alpha-pipeline.md § 4.9, et report_synthesis.py
  □ strategy_type identique dans les 3 fichiers
  □ alpha_threshold_bps identique dans les 3 fichiers
  □ Payloads A/B/C/D cohérents entre strategies/[nom].md § 4
    et les horizons § 4.9 de section4-alpha-pipeline.md

COHÉRENCE AVEC LE PIPELINE
  □ Clés overrides ReportContext dans la liste reconnue :
    boxplot_nogo, boxplot_weak, rolling_fragile,
    radar_discrimination, radar_exploitability
  □ Aucune modification de alpha_engine.py
  □ Aucune modification de pipeline/report.py
  □ Aucune modification des autres stratégies existantes

CONTRAINTE JS
  □ Aucune apostrophe droite ' dans les nouveaux blocs JS
    de report_synthesis.py

COMPLÉTUDE
  □ strategies/[nom].md contient les 8 sections
  □ Checklist GO/NO GO § 7 cite les payloads définis § 4
  □ Points d'ancrage quant-regime / quant-risk présents § 6
```

### 6.2 En cas d'échec d'un point

```
Point de cohérence échoué → corriger le fichier concerné
                          → relancer la vérification du point
                          → NE PAS passer au rapport final
                            tant que le point n'est pas vert
```

### 6.3 Rapport final

Écrire `INTEGRATION_REPORT.md` :
```
# Rapport d'Intégration — [NomStratégie]

## Résultat global
  [SUCCÈS / SUCCÈS PARTIEL / ÉCHEC]

## Stratégie intégrée
  Nom       : [NomStratégie]
  Type      : [type_détecté]
  Confiance : [CONFIRMÉE / PROBABLE]
  Seuil bps : [valeur]

## Fichiers produits
  ✅ strategies/[nom].md         [CRÉÉ / MODIFIÉ]
  ✅ section4-alpha-pipeline.md  [MODIFIÉ — ligne § 4.9]
  ✅ report_synthesis.py         [MODIFIÉ — ReportContext ajouté]

## Payloads définis
  A : [résumé une ligne]
  B : [résumé une ligne]
  C : [résumé une ligne]
  D : [résumé une ligne]

## Horizons Target Y
  h = [X, Y, Z] bougies [TF]

## Points nécessitant review humaine
  [liste si NEEDS_REVIEW.md existe, sinon "Aucun"]

## Prochaine étape
  Lancer run_section4_all_assets() avec les 4 payloads
  selon le notebook Cell 11 — structure définie dans strategies/[nom].md
```

---

## FICHIER NEEDS_REVIEW.md — Format Standard

Créer ce fichier et stopper l'exécution si :
- Fichier obligatoire manquant
- Classification impossible (indices insuffisants ou contradictoires)
- Ambiguïté sur les couches du signal non résolvable depuis le code

```markdown
# Action Requise — Revue Humaine

## Étape bloquée
  Étape [N] — [nom étape]

## Problème détecté
  [description précise]

## Informations manquantes
  [liste des questions auxquelles l'humain doit répondre]

## Fichiers déjà produits
  [liste des STEP_N_SUMMARY.md déjà écrits]

## Fichiers en attente
  [liste des fichiers non encore produits]

## Comment reprendre
  Répondre aux questions ci-dessus, puis relancer le skill.
  Les étapes déjà complétées ne seront pas réexécutées.
```

---

## CE QUE CE SKILL NE FAIT PAS

- Ne modifie pas `alpha_engine.py` — moteur universel, inchangé
- Ne modifie pas `pipeline/report.py` — structure HTML inchangée
- Ne crée pas de nouveau pipeline ni de nouveau runner
- Ne touche pas aux autres stratégies déjà intégrées
- Ne lance pas les tests statistiques (Section 4 du pipeline)
- Ne génère pas de prompts — exécute directement
