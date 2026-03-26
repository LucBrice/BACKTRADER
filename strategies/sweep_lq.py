"""
strategies/sweep_lq.py
======================
Stratégie : FausseCassure_LiquiditySweep

Logique :
  1. Prix touche un niveau LQ (bull pool ou bear pool)
  2. Dans les w2_bars suivantes, formation d'un engulfing dans la bonne direction
  3. Signal à la clôture de l'engulfing

Filtre optionnel : MTF AUTH (H1==H4 OR H4==D1)
  BUY  uniquement si MTF == +1
  SELL uniquement si MTF == -1

Paramètres :
  horizon_h      : barres forward pour le calcul Y (Section 4)
  expiry_days    : durée de vie des niveaux LQ
  w2_bars        : fenêtre max entre sweep et engulfing de confirmation
  tf_minutes     : résolution TF
  use_bias_filter: True = filtre MTF actif
  mono_position  : True = une seule position à la fois (build_payload)
                   False = tous les setups (debug)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from pipeline.base import Strategy
from pipeline.payload import AlphaPayload

from features.core import (
    detect_engulfing,
    calculate_market_bias,
    calculate_mtf_filter,
    get_stacked_liquidity,
)


class SweepLQStrategy(Strategy):

    name = "FausseCassure_MTF_LiquiditySweep"

    DEFAULT_PARAMS = {
        "horizon_h":       8,
        "expiry_days":     3,
        "w2_bars":        10,
        "tf_minutes":     15,
        "use_bias_filter": True,
        "mono_position":   True,
    }

    # ── MTF AUTH ──────────────────────────────────────────────────────────
    def _compute_mtf_auth(self, df: pd.DataFrame, params: dict) -> np.ndarray:
        bias_h1 = calculate_market_bias(df)
        df_h4, df_d1 = None, None

        if "df_h4" in params and "df_d1" in params:
            df_h4 = params["df_h4"]
            df_d1 = params["df_d1"]
        elif "aligned_data" in params and "asset" in params:
            ad, asset = params["aligned_data"], params["asset"]
            for k in ("4h","4H","H4"):
                if k in ad:
                    df_h4 = pd.DataFrame(
                        {c: ad[k][c][asset] for c in ["open","high","low","close"]}
                    ).dropna()
                    break
            for k in ("1D","1d","D1"):
                if k in ad:
                    df_d1 = pd.DataFrame(
                        {c: ad[k][c][asset] for c in ["open","high","low","close"]}
                    ).dropna()
                    break

        if df_h4 is not None and df_d1 is not None:
            bias_h4 = calculate_market_bias(df_h4).reindex(df.index, method="ffill")
            bias_d1 = calculate_market_bias(df_d1).reindex(df.index, method="ffill")
            return calculate_mtf_filter(bias_h1, bias_h4, bias_d1).values
        return bias_h1.values

    # ── Machine d'état ────────────────────────────────────────────────────
    def _run_state_machine(
        self,
        h_: np.ndarray,
        l_: np.ndarray,
        bear_eng: np.ndarray,
        bull_eng: np.ndarray,
        mtf_auth: np.ndarray,
        bull_pool: list,
        bear_pool: list,
        w2: int,
        horizon_h: int,
        use_bias_filter: bool = True,
        mono_position:   bool = True,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:

        n             = len(h_)
        signal        = np.zeros(n, float)
        is_sweep      = np.zeros(n, bool)

        phase         = 0      # 0=attente sweep  1=attente engulfing
        direction     = 0      # +1 BUY  -1 SELL
        sweep_bar     = -1
        position_open = False
        pos_close_bar = -1

        for i in range(1, n):

            # Fermeture automatique (uniquement si mono_position)
            if mono_position and position_open and i >= pos_close_bar:
                position_open = False

            next_i      = min(i + 1, n - 1)
            bull_levels = list(set(bull_pool[i] + bull_pool[next_i]))
            bear_levels = list(set(bear_pool[i] + bear_pool[next_i]))

            swept_bull = bool(bull_levels) and l_[i] <= min(bull_levels)
            swept_bear = bool(bear_levels) and h_[i] >= max(bear_levels)

            # Priorité bear si les deux simultanément
            if swept_bear and swept_bull:
                swept_bull = False

            # Nouveau sweep — reset et démarre fenêtre w2
            if swept_bear:
                phase=1; direction=-1; sweep_bar=i; is_sweep[i]=True
            elif swept_bull:
                phase=1; direction=1;  sweep_bar=i; is_sweep[i]=True

            # Attente engulfing de confirmation
            if phase == 1:
                age2 = i - sweep_bar
                if age2 > w2:
                    phase = 0
                else:
                    bias_now     = mtf_auth[i]
                    bias_ok_sell = (bias_now == -1) if use_bias_filter else True
                    bias_ok_buy  = (bias_now ==  1) if use_bias_filter else True
                    pos_free     = (not position_open) or (not mono_position)

                    if direction == -1 and bear_eng[i] and pos_free and bias_ok_sell:
                        signal[i] = -1.
                        if mono_position:
                            position_open = True
                            pos_close_bar = i + horizon_h
                        phase = 0

                    elif direction == 1 and bull_eng[i] and pos_free and bias_ok_buy:
                        signal[i] = 1.
                        if mono_position:
                            position_open = True
                            pos_close_bar = i + horizon_h
                        phase = 0

        return signal, is_sweep

    # ── build_payload ──────────────────────────────────────────────────────
    def build_payload(self, df, asset, tf, params) -> AlphaPayload:
        p          = {**self.DEFAULT_PARAMS, **params, "asset": asset}
        horizon_h  = int(p["horizon_h"])
        w2         = int(p["w2_bars"])
        tf_minutes = int(p["tf_minutes"])

        df = df.copy()

        eng      = detect_engulfing(df)
        bear_eng = eng["engulf_bear"].notna().values
        bull_eng = eng["engulf_bull"].notna().values
        mtf_auth = self._compute_mtf_auth(df, p)

        lq        = get_stacked_liquidity(df, expiry_days=p["expiry_days"],
                                          tf_minutes=tf_minutes)

        signal, _ = self._run_state_machine(
            df["high"].values, df["low"].values,
            bear_eng, bull_eng, mtf_auth,
            lq["bull_pool"], lq["bear_pool"],
            w2, horizon_h,
            use_bias_filter=p.get("use_bias_filter", True),
            mono_position=True,  # toujours True dans build_payload
        )

        signal_s   = pd.Series(signal, index=df.index)
        valid_idx  = df.index[:-horizon_h]
        X          = signal_s.loc[valid_idx]
        Y_raw_full = np.log(df["close"].shift(-horizon_h) / df["close"])
        Y_raw      = Y_raw_full.loc[valid_idx]
        Y_dir      = Y_raw.copy()
        Y_dir.loc[X == -1] = -Y_raw.loc[X == -1]
        Y_flat     = Y_raw[X == 0].dropna()

        sl_long  = ((df["close"] - df["low"])  / df["close"]).loc[valid_idx]
        sl_short = ((df["high"]  - df["close"]) / df["close"]).loc[valid_idx]

        return AlphaPayload(
            X=X, Y=Y_dir, asset=asset, tf=tf, horizon_h=horizon_h,
            sl_long=sl_long, sl_short=sl_short, Y_flat=Y_flat,
            meta={
                "strategy_name": self.name,
                "expiry_days":   p["expiry_days"],
                "w2_bars":       w2,
                "tf_minutes":    tf_minutes,
                "horizon_h":     horizon_h,
                "mtf_active":    "df_h4" in p or "aligned_data" in p,
            },
        )

    # ── build_debug_df ─────────────────────────────────────────────────────
    def build_debug_df(self, df: pd.DataFrame, params: dict,
                        asset: str = "") -> pd.DataFrame:
        p         = {**self.DEFAULT_PARAMS, **params}
        if asset: p["asset"] = asset
        horizon_h = int(p["horizon_h"])
        w2        = int(p["w2_bars"])
        tf_min    = int(p["tf_minutes"])

        df = df.copy()

        eng = detect_engulfing(df)
        df["engulf_bull"]    = eng["engulf_bull"]
        df["engulf_bear"]    = eng["engulf_bear"]
        df["bias"]           = calculate_market_bias(df)
        mtf_auth             = self._compute_mtf_auth(df, p)
        df["effective_bias"] = pd.Series(mtf_auth, index=df.index)

        # Pools — réutiliser si pré-calculés
        if "_bull_pool" in p and "_bear_pool" in p:
            bull_pool = p["_bull_pool"]
            bear_pool = p["_bear_pool"]
        else:
            lq        = get_stacked_liquidity(df, expiry_days=p["expiry_days"],
                                              tf_minutes=tf_min)
            bull_pool = lq["bull_pool"]
            bear_pool = lq["bear_pool"]

        df["bull_pool_lvl"] = pd.Series(
            [min(lvls) if lvls else np.nan for lvls in bull_pool],
            index=df.index,
        )
        df["bear_pool_lvl"] = pd.Series(
            [max(lvls) if lvls else np.nan for lvls in bear_pool],
            index=df.index,
        )

        bear_eng = df["engulf_bear"].notna().values
        bull_eng = df["engulf_bull"].notna().values

        signal, is_sweep = self._run_state_machine(
            df["high"].values, df["low"].values,
            bear_eng, bull_eng, mtf_auth,
            bull_pool, bear_pool,
            w2, horizon_h,
            use_bias_filter=p.get("use_bias_filter", True),
            mono_position=p.get("mono_position", True),
        )

        df["signal"]   = signal
        df["is_sweep"] = is_sweep
        df["is_pivot"] = np.zeros(len(df), bool)  # compatibilité debug

        return df
