import numpy as np
import pandas as pd
from bokeh.plotting import figure, show, output_notebook
from bokeh.layouts import column
from bokeh.models import ColumnDataSource, HoverTool, Range1d, LinearColorMapper, CrosshairTool
from indicators import calculate_market_bias, calculate_mtf_filter, detect_engulfing, get_stacked_liquidity

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
