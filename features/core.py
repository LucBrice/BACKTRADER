import pandas as pd
import numpy as np

# =========================================================
# 🛠️ HELPER VISUALISATION
# =========================================================
def set_viz(obj, type="overlay", **kwargs):
    if isinstance(obj, (pd.DataFrame, pd.Series)):
        obj.attrs["viz_type"] = type
        for k, v in kwargs.items(): obj.attrs[k] = v
    return obj

# =========================================================
# 🕯️ MODULE 1 : DETECTION DES ENGULFING (SIGNAL)
# =========================================================
def detect_engulfing(df):
    h, l, o, c = df["high"], df["low"], df["open"], df["close"]
    body_high, body_low = np.maximum(o, c), np.minimum(o, c)

    # Bullish
    bull_2 = (l < l.shift(1)) & (c > body_high.shift(1))
    bull_3 = (l.shift(1) < l.shift(2)) & (c.shift(1) <= body_high.shift(2)) & (c > body_high.shift(1))
    # Bearish
    bear_2 = (h > h.shift(1)) & (c < body_low.shift(1))
    bear_3 = (h.shift(1) > h.shift(2)) & (c.shift(1) >= body_low.shift(2)) & (c < body_low.shift(1))

    return {
        "engulf_bull": (bull_2 | bull_3).astype(float).replace(0, np.nan),
        "engulf_bear": (bear_2 | bear_3).astype(float).replace(0, np.nan)
    }

# =========================================================
# 🌍 MODULE 2 : MARKET BIAS & MTF FILTER
# =========================================================
def calculate_market_bias(df, return_details=False):
    h, l, o, c = df["high"], df["low"], df["open"], df["close"]
    h1, h2, l1, l2, o1, o2, c1, c2 = h.shift(1), h.shift(2), l.shift(1), l.shift(2), o.shift(1), o.shift(2), c.shift(1), c.shift(2)
    bh2, bl2 = np.maximum(o2, c2), np.minimum(o2, c2)
 
    engulf        = (h1 > h2) & (l1 < l2)
    engulf_bull   = engulf & (c1 > bh2)
    engulf_bear   = engulf & (c1 < bl2)
    engulf_neutre = engulf & (c1 >= bl2) & (c1 <= bh2)
 
    bullish1 = (h1 > h2) & (c1 > h2)
    bullish2 = (l1 < l2) & (c1 > l2)
    bearish1 = (l1 < l2) & (c1 < l2)
    bearish2 = (h1 > h2) & (c1 < h2)
 
    bull = engulf_bull | ((bullish1 | bullish2) & ~engulf)
    bear = engulf_bear | ((bearish1 | bearish2) & ~engulf)
 
    bias = c.copy() * 0.0
    bias[bull] = 1.0
    bias[bear] = -1.0
    bias[engulf_neutre] = 0.0
    
    if not return_details:
        return bias
        
    if isinstance(c, pd.DataFrame):
        reason = pd.DataFrame("Neutral", index=c.index, columns=c.columns)
    else:
        reason = pd.Series("Neutral", index=c.index)
        
    reason = reason.mask(engulf_bull, "Bullish (Engulfing)")
    reason = reason.mask(bullish1 & ~engulf, "Bullish (H1>H2 & C1>H2)")
    reason = reason.mask(bullish2 & ~engulf, "Bullish (L1<L2 & C1>L2)")
    reason = reason.mask(engulf_bear, "Bearish (Engulfing)")
    reason = reason.mask(bearish1 & ~engulf, "Bearish (L1<L2 & C1<L2)")
    reason = reason.mask(bearish2 & ~engulf, "Bearish (H1>H2 & C1<H2)")
    reason = reason.mask(engulf_neutre, "Neutral (Engulfing)")
    
    return bias, reason
 
def calculate_mtf_filter(b_h1, b_h4, b_d1):
    h1_h4, h4_d1 = (b_h1 == b_h4) & (b_h4 != 0), (b_h4 == b_d1) & (b_d1 != 0)
    auth = b_h4.copy()
    auth.values[:] = 0.0
    auth[h1_h4 | h4_d1] = b_h4[h1_h4 | h4_d1]
    return auth

# =========================================================
# 💧 MODULE 3 : STACKED LIQUIDITY (V8.3 - LEAK-PROOF & EXTREME)
# =========================================================
def get_stacked_liquidity(df, expiry_days=3, tf_minutes=15):
    expiry_bars = int((expiry_days * 24 * 60) / tf_minutes)
    h, l, o, c = df["high"], df["low"], df["open"], df["close"]
    bh = np.maximum(o, c)

    # Detection Patterns pour extraire l'EXTRÊME (Min/Max du pattern complet)
    bull_2 = (l < l.shift(1)) & (c > bh.shift(1))
    bull_3 = (l.shift(1) < l.shift(2)) & (c.shift(1) <= bh.shift(2)) & (c > bh.shift(1))
    bear_2 = (h > h.shift(1)) & (c < np.minimum(o, c).shift(1))
    bear_3 = (h.shift(1) > h.shift(2)) & (c.shift(1) >= np.minimum(o, c).shift(2)) & (c < np.minimum(o, c).shift(1))

    # Niveaux : Min Low ou Max High du pattern (2 ou 3 bougies)
    bull_src = np.minimum(l, l.shift(1)).where(bull_2, np.nan).fillna(np.minimum(l, np.minimum(l.shift(1), l.shift(2))).where(bull_3, np.nan))
    bear_src = np.maximum(h, h.shift(1)).where(bear_2, np.nan).fillna(np.maximum(h, np.maximum(h.shift(1), h.shift(2))).where(bear_3, np.nan))

    def process_pool(sources, is_bull=True):
        pool, history = [], []
        for i in range(len(df)):
            curr_h, curr_l = h.iloc[i], l.iloc[i]
            # 1. Disponibilité (On émet l'état du pool CONNU à l'ouverture de la bougie i)
            history.append([lvl[0] for lvl in pool])
            # 2. Sweep/Expiry par la bougie actuelle
            if is_bull: pool = [lvl for lvl in pool if i <= lvl[1] and curr_l > lvl[0]]
            else: pool = [lvl for lvl in pool if i <= lvl[1] and curr_h < lvl[0]]
            # 3. Naissance (Confirmé à la clôture de i, donc actif pour i+1)
            if not np.isnan(sources.iloc[i]): pool.append([sources.iloc[i], i + expiry_bars])
        return history

    return {"bull_pool": process_pool(bull_src, True), "bear_pool": process_pool(bear_src, False)}