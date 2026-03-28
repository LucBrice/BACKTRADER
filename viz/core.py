import numpy as np
import pandas as pd
from bokeh.plotting import figure, show, output_notebook
from bokeh.layouts import column
from bokeh.models import ColumnDataSource, HoverTool, Range1d, LinearColorMapper, CrosshairTool
from features.core import calculate_market_bias, calculate_mtf_filter, detect_engulfing, get_stacked_liquidity

# ==========================================================================================
# 🕒 GRAPHIQUE DE DEBUG 1 : SYNC MTF BREAKDOWN (H1, H4, D1, et LTF MTF AUTH)
# Focus : Analyse détaillée du Price Action multi-timeframe synchronisé sans gaps
# ==========================================================================================
def run_mtf_candlestick_visualizer(data_lake, asset, base_tf='15min', view_tfs=['15min', '1h', '4h', '1D'], window=300):
    """
    Renders stacked synchronized candlestick charts for detailed MTF price action analysis.
    Uses unified integer indexing to eliminate weekend gaps.
    Includes a 15min chart showing the MTF AUTH filter status.
    """
    # 1. Master Timeline (Gap-free index based on base_tf)
    master_df = pd.DataFrame({
        'open': data_lake[base_tf]['open'][asset], 'high': data_lake[base_tf]['high'][asset],
        'low': data_lake[base_tf]['low'][asset], 'close': data_lake[base_tf]['close'][asset]
    }).tail(window).copy()
    
    idx_master = master_df.index
    master_df['idx'] = np.arange(window)
    master_df['ts_str'] = idx_master.strftime('%Y-%m-%d %H:%M')
    
    # Pre-calculate mapping for each TF
    def get_tf_data(tf_key):
        # Full data for bias calculation
        df_full = pd.DataFrame({
            'open': data_lake[tf_key]['open'][asset], 'high': data_lake[tf_key]['high'][asset],
            'low': data_lake[tf_key]['low'][asset], 'close': data_lake[tf_key]['close'][asset]
        })
        # Subset that overlaps with master timeline
        start_ts, end_ts = idx_master[0], idx_master[-1]
        df_view = df_full.loc[df_full.index <= end_ts].tail(int(window * 2)) # Safety margin
        df_view = df_view.loc[df_view.index >= (start_ts - pd.Timedelta(days=2))] # Catch D1
        
        # Calculate Signals
        bias_res, reason_res = calculate_market_bias(data_lake[tf_key], return_details=True)
        bias = bias_res[[asset]].reindex(df_view.index)[asset]
        reason = reason_res[[asset]].reindex(df_view.index)[asset]
        sigs = detect_engulfing(df_view)
        
        # Map timestamps to Master Integer Indices
        df_view['idx_master'] = np.nan
        for ts in df_view.index:
            try:
                # Find nearest previous master index
                mask = idx_master <= ts
                if mask.any():
                    df_view.at[ts, 'idx_master'] = master_df['idx'][mask].iloc[-1]
            except Exception: pass
            
        # Filter only bars present in master view
        df_view = df_view.dropna(subset=['idx_master'])
        
        # Width calculation
        if len(df_view) > 1:
            avg_width = np.diff(df_view['idx_master']).mean()
            if np.isnan(avg_width) or avg_width < 1: avg_width = 1.0
        else: avg_width = 1.0
        
        return {
            'df': df_view, 'bias': bias, 'reason': reason, 'sigs': sigs, 'width': avg_width, 
            'bias_aligned': bias.reindex(idx_master, method='ffill')
        }

    tf_results = {tf: get_tf_data(tf) for tf in view_tfs}
    
    # === COMPUTE AUTH AND OVERWRITE LTF BIAS (15min) ===
    if '15min' in tf_results and '1h' in tf_results and '4h' in tf_results and '1D' in tf_results:
        b_h1 = tf_results['1h']['bias_aligned']
        b_h4 = tf_results['4h']['bias_aligned']
        b_d1 = tf_results['1D']['bias_aligned']
        
        # Compute MTF Auth using the master aligned index
        auth = calculate_mtf_filter(b_h1, b_h4, b_d1)
        
        # Update point-in-time tooltip bias matching df_view
        df_v_15m = tf_results['15min']['df']
        tf_results['15min']['bias'] = auth.reindex(df_v_15m.index)
        tf_results['15min']['bias_aligned'] = auth
        
        # Build descriptive reasoning for MTF
        def sig2txt(s):
            return s.map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"}).fillna("NaN")
            
        s_h1_txt = sig2txt(b_h1.reindex(df_v_15m.index))
        s_h4_txt = sig2txt(b_h4.reindex(df_v_15m.index))
        s_d1_txt = sig2txt(b_d1.reindex(df_v_15m.index))
        
        reason_series = pd.Series("NO AUTH (H1=" + s_h1_txt + " / H4=" + s_h4_txt + " / D1=" + s_d1_txt + ")", index=df_v_15m.index)
        
        # Create condition masks for valid AUTH
        h1_h4 = (b_h1 == b_h4) & (b_h4 != 0)
        h4_d1 = (b_h4 == b_d1) & (b_d1 != 0)
        
        auth_bull_h1h4 = h1_h4 & (b_h4 == 1.0)
        auth_bear_h1h4 = h1_h4 & (b_h4 == -1.0)
        auth_bull_h4d1 = h4_d1 & (b_d1 == 1.0)
        auth_bear_h4d1 = h4_d1 & (b_d1 == -1.0)
        
        reason_series = reason_series.mask(auth_bull_h1h4.reindex(df_v_15m.index).fillna(False), "AUTH BULL (+1) via [H1=BULL & H4=BULL]")
        reason_series = reason_series.mask(auth_bear_h1h4.reindex(df_v_15m.index).fillna(False), "AUTH BEAR (-1) via [H1=BEAR & H4=BEAR]")
        reason_series = reason_series.mask(auth_bull_h4d1.reindex(df_v_15m.index).fillna(False), "AUTH BULL (+1) via [H4=BULL & D1=BULL]")
        reason_series = reason_series.mask(auth_bear_h4d1.reindex(df_v_15m.index).fillna(False), "AUTH BEAR (-1) via [H4=BEAR & D1=BEAR]")
        
        tf_results['15min']['reason'] = reason_series
    
    # Couleurs
    C_BULL, C_BEAR = '#26a69a', '#ef5350'
    C_BG_BULL, C_BG_BEAR = '#4caf50', '#f44336'
    C_WHITE, C_BLACK = '#ffffff', '#333333'

    plots = []
    master_x_range = Range1d(-0.5, window - 0.5)

    for i, tf in enumerate(view_tfs):
        res = tf_results[tf]
        df_v = res['df']
        sigs = res['sigs']
        
        # Color candles
        is_bull_sigs = ~sigs["engulf_bull"].isna()
        is_bear_sigs = ~sigs["engulf_bear"].isna()
        candle_colors = []
        for idx_v, row in enumerate(df_v.iloc):
            ts = df_v.index[idx_v]
            if ts in is_bull_sigs.index and is_bull_sigs.loc[ts]: color = C_BULL
            elif ts in is_bear_sigs.index and is_bear_sigs.loc[ts]: color = C_BEAR
            else: color = C_WHITE if row['close'] >= row['open'] else C_BLACK
            candle_colors.append(color)
        df_v['color'] = candle_colors
        
        # Map bias values and reasons for tooltips
        df_v['bias_val'] = res['bias']
        df_v['bias_reason'] = res['reason']
        df_v['ts_str'] = df_v.index.strftime('%Y-%m-%d %H:%M')
        
        # Create Plot
        title_text = f"🕒 {tf.upper()} (AUTH MTF) BREAKDOWN : {asset}" if tf == '15min' else f"🕒 {tf.upper()} BREAKDOWN : {asset}"
        p = figure(title=title_text, 
                   width=1200, height=350, tools="pan,wheel_zoom,reset,save",
                   active_scroll="wheel_zoom", x_range=master_x_range)
        
        p.background_fill_color = "#fdfdfd"
        p.add_tools(CrosshairTool(line_alpha=0.3, line_color="gray"))
        
        # Bias Background
        df_bias = pd.DataFrame({
            'idx': master_df['idx'], 
            'val': res['bias_aligned'].values,
            'ts_str': master_df['ts_str']
        })
        df_bias['color'] = df_bias['val'].map({1: C_BG_BULL, -1: C_BG_BEAR, 0: 'transparent'})
        
        y_min, y_max = df_v['low'].min(), df_v['high'].max()
        p.rect(x='idx', y=(y_min+y_max)/2, width=1, height=(y_max-y_min)*2, 
               fill_color='color', fill_alpha=0.08, line_color=None, source=ColumnDataSource(df_bias), level='underlay')

        # Candles
        w = res['width'] * 0.8
        src_v = ColumnDataSource(df_v)
        p.segment(x0='idx_master', y0='low', x1='idx_master', y1='high', color='black', source=src_v)
        vbar = p.vbar(x='idx_master', width=w, top='open', bottom='close', 
                      fill_color='color', line_color='black', source=src_v)

        p.add_tools(HoverTool(renderers=[vbar], tooltips=[
            ("Time", "@ts_str"), 
            ("Bias", "@bias_val"),
            ("Reason", "@bias_reason")
        ]))
        
        plots.append(p)

    # Shared Axis Labeling (Bottom chart only)
    tick_indices = np.arange(0, window, max(1, window // 10))
    plots[-1].xaxis.ticker = tick_indices
    plots[-1].xaxis.major_label_overrides = {int(i): master_df['ts_str'].iloc[int(i)] for i in tick_indices}
    for p in plots[:-1]: p.xaxis.visible = False

    layout = column(*plots, sizing_mode="stretch_width")
    output_notebook()
    show(layout)

# ==========================================================================================
# 📊 GRAPHIQUE DE DEBUG 2 : TOTAL QUANT COCKPIT (V8.3)
# Focus : Visualisation unifiée, Liquidité Stackée, et Rubans de Biais MTF
# ==========================================================================================
def run_synchronized_debug_bokeh(data_lake, asset, tf, n_bars, expiry):
    """
    Renders an interactive Bokeh dashboard for trading strategy debugging.
    Minimalist tooltips (Time only) and full X/Y zoom capability.
    """
    # 1. Data Setup
    buffer = int((expiry * 24 * 60) / 15) + 50
    df_full = pd.DataFrame({
        'open': data_lake[tf]['open'][asset], 'high': data_lake[tf]['high'][asset],
        'low': data_lake[tf]['low'][asset], 'close': data_lake[tf]['close'][asset]
    }).tail(n_bars + buffer)
    
    df_view = df_full.tail(n_bars).copy()
    idx_view = df_view.index
    
    # 2. CALCULS MTF & LIQUIDITY
    def get_aligned(target_tf):
        b = calculate_market_bias(data_lake[target_tf])[[asset]]
        return b.reindex(idx_view, method='ffill')[asset]

    b_h1, b_h4, b_d1 = get_aligned("1h"), get_aligned("4h"), get_aligned("1D")
    mtf_auth = calculate_mtf_filter(b_h1, b_h4, b_d1)
    
    sigs = detect_engulfing(df_view)
    pools = get_stacked_liquidity(df_full, expiry_days=expiry, tf_minutes=15)
    
    bull_pool_view = pools["bull_pool"][-n_bars:]
    bear_pool_view = pools["bear_pool"][-n_bars:]

    # --- PRÉPARATION DES DONNÉES BOKEH ---
    df_view['idx'] = np.arange(n_bars)
    df_view['ts_str'] = df_view.index.strftime('%Y-%m-%d %H:%M')
    df_view['mtf_auth'] = mtf_auth.values
    df_view['b_h1'], df_view['b_h4'], df_view['b_d1'] = b_h1.values, b_h4.values, b_d1.values

    # Couleurs du cockpit
    C_BULL, C_BEAR = '#26a69a', '#ef5350'
    C_BG_BULL, C_BG_BEAR = '#4caf50', '#f44336'
    
    is_bull_sigs = ~sigs["engulf_bull"].isna()
    is_bear_sigs = ~sigs["engulf_bear"].isna()
    
    def get_candle_color(row, i):
        if is_bull_sigs.iloc[i]: return C_BULL
        if is_bear_sigs.iloc[i]: return C_BEAR
        return 'white' if row['close'] >= row['open'] else '#333333'
    
    df_view['candle_color'] = [get_candle_color(row, i) for i, row in enumerate(df_view.iloc)]
    df_view['bg_color'] = df_view['mtf_auth'].map({1: C_BG_BULL, -1: C_BG_BEAR, 0: 'transparent'})

    # Liquidité (MultiLine pour performance)
    l_bull_xs, l_bull_ys = [], []
    l_bear_xs, l_bear_ys = [], []
    for i in range(n_bars):
        for lvl in bull_pool_view[i]:
            l_bull_xs.append([i - 0.5, i + 0.5]); l_bull_ys.append([lvl, lvl])
        for lvl in bear_pool_view[i]:
            l_bear_xs.append([i - 0.5, i + 0.5]); l_bear_ys.append([lvl, lvl])

    source = ColumnDataSource(df_view)

    # --- 3. CONFIGURATION DU GRAPHIQUE PRINCIPAL ---
    tools = "pan,wheel_zoom,box_zoom,reset,save"
    p_main = figure(title=f"🛡️ TOTAL QUANT COCKPIT V8.3 : {asset} [{tf}]", 
                    width=1200, height=550, tools=tools, active_scroll="wheel_zoom",
                    x_range=Range1d(-0.5, n_bars - 0.5))
    
    p_main.background_fill_color = "#fdfdfd"
    p_main.add_tools(CrosshairTool(line_alpha=0.4, line_color="gray"))

    # Fond MTF
    p_main.vbar(x='idx', width=1, top=df_view['high'].max()*1.1, bottom=df_view['low'].min()*0.9,
                fill_color='bg_color', fill_alpha=0.1, line_color=None, source=source, level='underlay')

    # Bougies
    p_main.segment(x0='idx', y0='low', x1='idx', y1='high', color='black', line_width=1, source=source)
    vbar = p_main.vbar(x='idx', width=0.7, top='open', bottom='close', 
                       fill_color='candle_color', line_color='black', source=source)

    # Liquidité
    p_main.multi_line(xs=l_bull_xs, ys=l_bull_ys, color='#2ecc71', alpha=0.7, line_width=2)
    p_main.multi_line(xs=l_bear_xs, ys=l_bear_ys, color='#e74c3c', alpha=0.7, line_width=2)

    # Tooltip MINIMALISTE
    p_main.add_tools(HoverTool(renderers=[vbar], tooltips=[("Date", "@ts_str")]))

    # --- 4. RUBANS (HEATMAPS) ---
    mapper = LinearColorMapper(palette=[C_BEAR, "#e0e0e0", C_BULL], low=-1.1, high=1.1)

    def create_ribbon(df_col, label, height=50, show_xaxis=False):
        p = figure(width=1200, height=height, x_range=p_main.x_range, 
                   tools="xwheel_zoom,xpan,reset", toolbar_location=None)
        p.rect(x='idx', y=0.5, width=1, height=1, source=source,
               fill_color={'field': df_col, 'transform': mapper}, line_color=None, alpha=0.8)
        p.yaxis.axis_label = label
        p.yaxis.major_label_text_font_size = '0pt'
        p.yaxis.major_tick_line_color = p.yaxis.minor_tick_line_color = None
        p.xaxis.visible = show_xaxis
        p.outline_line_color = None
        p.add_tools(HoverTool(tooltips=[("Date", "@ts_str")]))
        return p

    p_auth = create_ribbon('mtf_auth', 'AUTH')
    p_h1 = create_ribbon('b_h1', 'H1')
    p_h4 = create_ribbon('b_h4', 'H4')
    p_d1 = create_ribbon('b_d1', 'D1', height=80, show_xaxis=True)

    # Formatting X-Axis
    tick_indices = np.arange(0, n_bars, 30)
    p_d1.xaxis.ticker = tick_indices
    p_d1.xaxis.major_label_overrides = {int(i): df_view['ts_str'].iloc[int(i)] for i in tick_indices}

    # Compilation
    layout = column(p_main, p_auth, p_h1, p_h4, p_d1, sizing_mode="stretch_width")
    output_notebook()
    show(layout)
