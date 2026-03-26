"""
pipeline/payload.py
===================
Contrat d'interface entre la couche Stratégie et le Moteur statistique.

AlphaPayload est un dataclass pur — aucune logique, que des données.
C'est la seule chose que :
  - une Stratégie DOIT produire
  - le moteur alpha_engine ACCEPTE en entrée

Règle stricte : tout ce qui est ici doit être agnostique à la stratégie.
Interdiction d'importer features.py, indicators.py ou tout module métier.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class AlphaPayload:
    """
    Contrat de données entre Stratégie → Moteur statistique.

    Paramètres obligatoires
    -----------------------
    X : pd.Series
        Vecteur signal (ex: -1, 0, 1 ou valeur continue).
        Index = timestamps UTC, aligné sur Y.
        Ne doit contenir AUCUNE donnée future (no lookahead).

    Y : pd.Series
        Forward log-return sur horizon_h barres.
        Y = log(close[t+h] / close[t])
        Pour les signaux SHORT, Y_directional = -Y (déjà inversé).
        Index = timestamps UTC, aligné sur X.

    Paramètres de contexte
    ----------------------
    asset     : str   — identifiant de l'actif  (ex: "NASDAQ")
    tf        : str   — timeframe               (ex: "15min")
    horizon_h : int   — horizon forward en barres

    Colonnes auxiliaires (optionnelles mais recommandées)
    -----------------------------------------------------
    sl_long  : pd.Series | None
        Distance SL normalisée pour les signaux LONG.
        sl_long = (entry_price - sl_price) / entry_price

    sl_short : pd.Series | None
        Distance SL normalisée pour les signaux SHORT.
        sl_short = (sl_price - entry_price) / entry_price

    Y_flat : pd.Series | None
        Forward returns sur les barres SANS signal (benchmark).
        Utilisé par le KS test. Si None, le moteur le calcule
        depuis Y en prenant les barres où X == 0.

    meta : dict
        Champ libre pour les métadonnées de la stratégie.
        Ex: {"strategy_name": "SweepLQ", "expiry_days": 3}
        Non utilisé par le moteur — passé tel quel dans le rapport.
    """

    # ── Obligatoires ──────────────────────────────────────────
    X:         pd.Series
    Y:         pd.Series
    asset:     str
    tf:        str
    horizon_h: int

    # ── Optionnels ────────────────────────────────────────────
    sl_long:   pd.Series | None = field(default=None)
    sl_short:  pd.Series | None = field(default=None)
    Y_flat:    pd.Series | None = field(default=None)
    meta:      dict             = field(default_factory=dict)

    # ── Validation à la construction ──────────────────────────
    def __post_init__(self):
        if not isinstance(self.X, pd.Series):
            raise TypeError("AlphaPayload.X doit être un pd.Series")
        if not isinstance(self.Y, pd.Series):
            raise TypeError("AlphaPayload.Y doit être un pd.Series")
        if len(self.X) != len(self.Y):
            raise ValueError(
                f"AlphaPayload : X ({len(self.X)}) et Y ({len(self.Y)}) "
                f"doivent avoir la même longueur"
            )
        if self.X.index.dtype != self.Y.index.dtype:
            raise TypeError("AlphaPayload : X et Y doivent avoir le même dtype d'index")
        if not self.asset:
            raise ValueError("AlphaPayload.asset ne peut pas être vide")
        if not self.tf:
            raise ValueError("AlphaPayload.tf ne peut pas être vide")
        if self.horizon_h <= 0:
            raise ValueError("AlphaPayload.horizon_h doit être > 0")

    @property
    def n_signals(self) -> int:
        """Nombre de barres avec signal actif (X != 0)."""
        return int((self.X != 0).sum())

    @property
    def n_long(self) -> int:
        return int((self.X > 0).sum())

    @property
    def n_short(self) -> int:
        return int((self.X < 0).sum())

    @property
    def strategy_name(self) -> str:
        return self.meta.get("strategy_name", "Unknown")
