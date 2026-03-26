---
name: quant-team-laws
description: Lois suprêmes et interdictions absolues pour le trading quantitatif (R&D et Production).
trigger: always_on
---

# Quant Team Laws — Les Lois Suprêmes

Ces lois sont **non-négociables** et prévalent sur toute autre instruction de génération de code ou d'analyse.

## 1. Intégrité des Données & Biais
- **Zéro Lookahead Bias** : Une feature au temps `t` ne doit utiliser QUE des données disponibles à `t`.
- **Zéro Survivorship Bias** : Utiliser un univers de symboles complet (actifs délistés inclus si possible).
- **Log-Returns Uniquement** : Tous les calculs statistiques (VaR, CVaR, rendements) doivent utiliser des log-returns. Jamais de pourcentages bruts.
- **Zéro Paramètre Fantôme** : Tout paramètre (fenêtre, seuil) doit être documenté et configurable.

## 2. Validation de l'Alpha (Section 4 & EBTA)
- **Gate Statistique** : Pas de GO sans validation des 4 étapes de la Section 4 (Sanité, Détection, Discrimination, Exploitabilité).
- **Seuil Minimum** : Jamais de conclusion statistique sur moins de 100 observations par régime.
- **EBTA Compliance** : Tout profit doit être validé sur données détrendées (log-detrending) pour prouver qu'il ne provient pas d'un simple biais de position.

## 3. Gestion des Risques & Sizing (Quant Risk)
- **Loi de Kelly** : Jamais de Kelly complet. Utiliser uniquement le **Kelly Fractionnel (≤ 0.25)**.
- **Daily Loss Limit** : Aucun code de production ne doit être généré sans une limite de perte journalière (Daily Loss Limit) explicitement définie et codée.
- **Vue Portefeuille** : Le sizing d'une position ne doit jamais être calculé isolément ; il doit dériver du risque global du portefeuille.
- **Corrélation de Crise** : Ne jamais ignorer que les corrélations convergent vers 1 en période de stress.

## 4. Stratégie & Portefeuille
- **Audit de Module** : Ne jamais recréer un module (loader, indicateur) que l'utilisateur possède déjà sans confirmation.
- **Diversification MV** : Pas d'optimisation Mean-Variance sans contraintes strictes de poids minimum/maximum.
- **Validation OOS** : Aucune stratégie ou portefeuille ne doit être validé sans un test Out-Of-Sample (OOS) prouvant la stabilité des métriques.

## 5. Analyse de Régime (Quant Regime)
- **Transition Buffer** : Jamais de changement de régime sur une seule barre. Appliquer un buffer de transition (minimum 5 barres).
- **Simplicité HMM** : Pas plus de 3 états HMM sans justification statistique majeure (éviter l'overfitting).

---

> [!IMPORTANT]
> Si une demande de l'utilisateur ou une suggestion de l'IA contredit l'une de ces lois, l'IA DOIT signaler la contradiction et proposer une alternative conforme.
