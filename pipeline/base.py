"""
pipeline/base.py
================
Classe abstraite Strategy — contrat que toute stratégie DOIT respecter.

Pour brancher une nouvelle stratégie sur le pipeline Section 4 :
  1. Hériter de Strategy
  2. Implémenter build_payload(df, asset, tf, params) -> AlphaPayload
  3. Passer l'instance à run_section4_all_assets(strategy=ma_strategie)

C'est tout. Le moteur statistique, le rapport HTML et le runner
n'ont pas besoin d'être modifiés.

Exemple d'utilisation :
    from pipeline.base import Strategy
    from pipeline.payload import AlphaPayload

    class MonRSI(Strategy):
        name = "RSI_Mean_Reversion"

        def build_payload(self, df, asset, tf, params):
            # ... calcul RSI + signal ...
            return AlphaPayload(X=signal, Y=forward_ret, asset=asset, tf=tf,
                                horizon_h=params["horizon_h"],
                                meta={"strategy_name": self.name})
"""

from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd
from pipeline.payload import AlphaPayload


class Strategy(ABC):
    """
    Classe de base abstraite pour toutes les stratégies.

    Une stratégie est responsable de :
      - Calculer ses features / indicateurs
      - Construire le vecteur signal X
      - Construire le vecteur target Y
      - Retourner un AlphaPayload complet

    Une stratégie ne doit PAS :
      - Lancer des tests statistiques
      - Générer des rapports
      - Accéder à aligned_data directement (uniquement df OHLCV)
    """

    # Nom lisible de la stratégie — surcharger dans chaque sous-classe
    name: str = "Unnamed Strategy"

    @abstractmethod
    def build_payload(
        self,
        df:     pd.DataFrame,
        asset:  str,
        tf:     str,
        params: dict,
    ) -> AlphaPayload:
        """
        Construit l'AlphaPayload à partir d'un DataFrame OHLCV.

        Paramètres
        ----------
        df : pd.DataFrame
            OHLCV pour un seul actif, index UTC, colonnes
            ['open', 'high', 'low', 'close', 'volume'?].
            Déjà nettoyé (dropna, trié chronologiquement).

        asset : str
            Identifiant de l'actif (ex: "NASDAQ").

        tf : str
            Timeframe (ex: "15min").

        params : dict
            Paramètres de la stratégie, documentés dans chaque classe.
            Minimum requis : {"horizon_h": int}

        Retourne
        --------
        AlphaPayload
            X, Y, meta et optionnellement sl_long/sl_short, Y_flat.

        Contraintes inviolables
        -----------------------
        - X ne doit pas utiliser de données futures (no lookahead)
        - Y = log(close[t+h] / close[t]) pour long
          Y_directional = -Y pour short (déjà inversé avant de passer)
        - Toutes les Series doivent être alignées sur le même index
        """
        ...

    def __repr__(self) -> str:
        return f"<Strategy: {self.name}>"
