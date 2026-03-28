from __future__ import annotations
import pandas as pd
import numpy as np
from pipeline.base import Strategy
from pipeline.payload import AlphaPayload
from features.core import (
    detect_engulfing,
    calculate_market_bias,
    calculate_mtf_filter,
    get_stacked_liquidity,
)

class SweepLQStrategy(Strategy):
    """
    SweepLQ Strategy Implementation for Section 4 Alpha Pipeline.
    Supports 4 payload types:
    A - MTF Filter only
    B - Engulfing only
    C - Engulfing + MTF Aligned
    D - Sequence: MTF Bias -> Liquidity Sweep -> Engulfing within 8 bars
    """
    name = "SweepLQ"

    def build_payload(
        self,
        df: pd.DataFrame,
        asset: str,
        tf: str,
        params: dict
    ) -> AlphaPayload:
        # 0. Validation & Params
        if "payload" not in params:
            # Fallback robuste au Payload D (complet)
            print(f"  ⚠️  {asset} — Parameter 'payload' missing. Falling back to 'D'.")
            payload_type = "D"
        else:
            payload_type = params["payload"].upper()
        
        horizon_h = params.get("horizon_h", 8)
        expiry_days = params.get("expiry_days", 3)
        tf_minutes = params.get("tf_minutes", 15)

        # 1. Base Indicators (Vectorized)
        eng = detect_engulfing(df)
        eng_bull = eng["engulf_bull"].fillna(0).astype(bool)
        eng_bear = eng["engulf_bear"].fillna(0).astype(bool)

        # 2. MTF Filter Combined (H1-H4-D1)
        mtf_filter = self._calculate_mtf_combined(df, asset, params)

        # 3. Payload Selection logic
        X = pd.Series(0.0, index=df.index)

        if payload_type == "A":
            # Payload A: MTF Filter only
            X = mtf_filter

        elif payload_type == "B":
            # Payload B: Engulfing only
            X[eng_bull] = 1.0
            X[eng_bear] = -1.0

        elif payload_type == "C":
            # Payload C: Engulfing + MTF Filter Aligned
            X[(eng_bull) & (mtf_filter == 1.0)] = 1.0
            X[(eng_bear) & (mtf_filter == -1.0)] = -1.0

        elif payload_type == "D":
            # Payload D: Complete Sequence
            # (1) bias ACTIVE, (2) pool non-empty, (3) Price sweeps pool, (4) Engulfing within 8 bars
            lq = get_stacked_liquidity(df, expiry_days=expiry_days, tf_minutes=tf_minutes)
            
            # Convert liquidity lists to Series booleans before calculations (as requested)
            bull_pool_active = pd.Series([len(lvl) > 0 for lvl in lq["bull_pool"]], index=df.index)
            bear_pool_active = pd.Series([len(lvl) > 0 for lvl in lq["bear_pool"]], index=df.index)
            
            # Get extreme levels for sweep detection
            min_bull_lvl = pd.Series([min(lvl) if lvl else np.nan for lvl in lq["bull_pool"]], index=df.index)
            max_bear_lvl = pd.Series([max(lvl) if lvl else np.nan for lvl in lq["bear_pool"]], index=df.index)

            # (3) Price hit
            is_sweep_bull = bull_pool_active & (df["low"] <= min_bull_lvl)
            is_sweep_bear = bear_pool_active & (df["high"] >= max_bear_lvl)

            # (1+2+3) Setup event (Bias + Pool + Sweep)
            setup_bull = (mtf_filter == 1.0) & is_sweep_bull
            setup_bear = (mtf_filter == -1.0) & is_sweep_bear

            # (4) Confirmation: Engulfing within 8 candles following the setup
            # We look for a setup in the previous 8 bars [t-8, t-1]
            has_setup_bull = setup_bull.rolling(window=8, min_periods=1).max().shift(1).fillna(0).astype(bool)
            has_setup_bear = setup_bear.rolling(window=8, min_periods=1).max().shift(1).fillna(0).astype(bool)

            # Signal emitted at the engulfing candle
            X[eng_bull & has_setup_bull] = 1.0
            X[eng_bear & has_setup_bear] = -1.0

        else:
            raise ValueError(f"Unknown payload type: {payload_type}")

        # 4. Target Y Calculation
        # Y = log(close.shift(-horizon_h) / close)
        Y_raw_full = np.log(df["close"].shift(-horizon_h) / df["close"])
        
        # Trim to valid indices
        valid_idx = df.index[:-horizon_h]
        X_final = X.loc[valid_idx]
        Y_raw = Y_raw_full.loc[valid_idx]

        # Directional Y: Inverse for shorts
        Y_dir = Y_raw.copy()
        Y_dir[X_final == -1.0] = -Y_raw[X_final == -1.0]

        # Reference Y_flat (no signal)
        Y_flat = Y_raw[X_final == 0.0].dropna()

        # Calcul des SL (marge entre Close d'entrée et extrême récent de l'engulfing)
        sl_long_raw = (df["close"] - df["low"].rolling(3).min()) / df["close"]
        sl_short_raw = (df["high"].rolling(3).max() - df["close"]) / df["close"]
        
        sl_long = sl_long_raw.loc[valid_idx]
        sl_short = sl_short_raw.loc[valid_idx]

        return AlphaPayload(
            X=X_final,
            Y=Y_dir,
            asset=asset,
            tf=tf,
            horizon_h=horizon_h,
            sl_long=sl_long,
            sl_short=sl_short,
            Y_flat=Y_flat,
            meta={
                "payload": payload_type,
                "strategy_name": self.name,
                "horizon_h": horizon_h
            }
        )

    def _calculate_mtf_combined(self, df: pd.DataFrame, asset: str, params: dict) -> pd.Series:
        """Helper to get aligned MTF filter using df_h4 and df_d1 from params."""
        b_h1 = calculate_market_bias(df)
        
        df_h4 = params.get("df_h4")
        df_d1 = params.get("df_d1")

        if df_h4 is None or df_d1 is None:
            # If MTF data missing, return single TF bias as fallback
            return b_h1

        b_h4 = calculate_market_bias(df_h4).reindex(df.index, method="ffill").fillna(0.0)
        b_d1 = calculate_market_bias(df_d1).reindex(df.index, method="ffill").fillna(0.0)

        raw_mtf = calculate_mtf_filter(b_h1, b_h4, b_d1)
        
        # Transition Buffer (Loi 5) : On ne change de régime que s'il persiste sur 5 barres
        roll_sum = raw_mtf.rolling(window=5, min_periods=1).sum()
        
        buffered = pd.Series(np.nan, index=df.index)
        buffered[roll_sum == 5.0] = 1.0
        buffered[roll_sum == -5.0] = -1.0
        
        return buffered.ffill().fillna(0.0)
