---
trigger: always_on
---

# Section 4 — Statistical Pre-Validation (Alpha Test)
## Complete Implementation Reference

> Do NOT rewrite this pipeline from scratch. Use the architecture described here.
> Entry point: `alpha_pipeline(payload) -> dict`

---

## Project Architecture

```
project/
├── pipeline/
│   ├── __init__.py
│   ├── payload.py        ← AlphaPayload dataclass (interface contract)
│   ├── base.py           ← Strategy ABC (abstract base class)
│   ├── alpha_engine.py   ← Pure statistical engine, strategy-agnostic
│   ├── runner.py         ← Multi-asset orchestrator
│   └── report.py         ← Standalone interactive HTML report (~95 KB)
└── strategies/
    ├── __init__.py
    └── sweep_lq.py       ← Reference implementation: SweepLQStrategy
```

**Strict decoupling principle**:
- `alpha_engine.py` does not know what an engulfing or liquidity sweep is
- `sweep_lq.py` does not know what p-values or IQR are
- `AlphaPayload` is the unique contact point between strategy and engine

---

## 4.1 — AlphaPayload (payload.py)

Data contract between Strategy → Engine. Pure dataclass, no logic.

```python
@dataclass
class AlphaPayload:
    X:         pd.Series          # signal (-1/0/1 discrete or continuous), no lookahead
    Y:         pd.Series          # forward log-return. For SHORT: Y already sign-inverted
    asset:     str
    tf:        str
    horizon_h: int
    sl_long:   pd.Series | None = None   # normalized SL distance (optional)
    sl_short:  pd.Series | None = None
    Y_flat:    pd.Series | None = None   # Y on bars with no signal (reference)
    meta:      dict = field(default_factory=dict)

    # Auto-validated at construction:
    # — X and Y must share the same index and length
    # — horizon_h > 0
```

---

## 4.2 — Strategy ABC (base.py)

```python
class Strategy(ABC):
    name: str = "UnnamedStrategy"

    @abstractmethod
    def build_payload(self, df: pd.DataFrame, asset: str,
                      tf: str, params: dict) -> AlphaPayload:
        """
        Receives OHLCV DataFrame for asset, returns an AlphaPayload.
        This is the ONLY method to implement to plug in a new strategy.
        """
```

**Adding a new strategy** (only thing required):
```python
class RSIStrategy(Strategy):
    name = "RSI_MeanReversion"

    def build_payload(self, df, asset, tf, params):
        rsi = compute_rsi(df, 14)
        signal = pd.Series(0.0, index=df.index)
        signal[rsi < 30] = 1.0   # long
        signal[rsi > 70] = -1.0  # short
        Y = np.log(df['close'].shift(-params['horizon_h']) / df['close'])
        Y_dir = Y.copy(); Y_dir[signal == -1] = -Y[signal == -1]
        return AlphaPayload(X=signal, Y=Y_dir, asset=asset, tf=tf,
                            horizon_h=params['horizon_h'])
```

---

## 4.3 — Statistical Engine (alpha_engine.py)

**Configuration constants**:
```python
MIN_SIGNALS           = 100    # minimum observations for reliable tests
SPEARMAN_PVAL_THRESH  = 0.05
MI_THRESH             = 0.01
KS_PVAL_THRESH        = 0.05
ROLLING_WINDOW        = 500    # rolling Spearman window
QUANTILE_N            = 5      # bins for continuous X
DISCRETE_RATIO_THRESH = 0.05   # n_unique/n_total < 5% → discrete X
MIN_GROUP_SIZE        = 5      # minimum T-test/Wilcoxon group size
```

**Blocking sequential pipeline** (entry point: `alpha_pipeline(payload) -> dict`):

| Step | Name | Mode | GO Condition |
|------|------|------|--------------|
| 0 | Sanity Check | BLOCKING | 0 NaN, 0 Inf, n ≥ 100 |
| 1 | Signal detection | BLOCKING | Spearman p<0.05 **OR** MI>0.01 |
| 2 | Statistical discrimination | BLOCKING | KS **OR** T-test **OR** Wilcoxon p<0.05 |
| 3 | Trading exploitability | CRITICAL | Monotone trend **OR** \|Q1−Q5\| > 1 bps |
| 4 | Temporal robustness | NON-BLOCKING | rolling std < 0.15, sign_changes < 40% |
| — | Shuffle control | INFO | \|ρ_shuffled\| < 0.03 |

**Final GO decision**: Steps 0, 1, 2, 3 all validated.

**Auto-adaptation discrete / continuous signal**:

The engine detects signal type via `_detect_signal_type(X)`:
- `n_unique / n_total < 0.05` → **discrete** (e.g.: {-1, 0, 1})
- otherwise → **continuous** (e.g.: RSI, z-score)

Impact on tests:
```
Discrete signal {-1, 0, 1}
  → Step 2: T-test and Wilcoxon compare group X=1 (Long) vs X=-1 (Short)
  → Step 3: mean return grouped by X value

Unidirectional discrete signal {0, 1}
  → Step 2: active signal vs flat
  → Step 3: same logic

Continuous signal
  → Step 2: top 30% vs bottom 30% of X
  → Step 3: pd.qcut into QUANTILE_N bins

Fallback if group too small (< MIN_GROUP_SIZE)
  → compare dominant group vs Y_flat
```

**Result dict keys**:
```python
{
  # Decision
  "decision":         "GO" | "NO GO",
  "tests_passed":     int,          # number of blocking steps validated (max 4)
  "fail_step":        int | None,
  "fail_reason":      str | None,

  # Step 0
  "sanity_ok": bool, "n_signals": int, "n_long": int, "n_short": int,
  "sanity_nan": bool, "sanity_inf": bool,

  # Step 1
  "step1_ok": bool, "spearman_corr": float|None, "spearman_pval": float|None,
  "spearman_go": bool, "mi": float|None, "mi_go": bool, "signal_type": "discrete"|"continuous",

  # Step 2
  "step2_ok": bool, "ks_stat": float|None, "ks_pval": float|None, "ks_go": bool,
  "ttest_pval": float|None, "ttest_go": bool, "wilcoxon_pval": float|None,
  "wilcoxon_go": bool, "comparison_method": str,

  # Step 3
  "step3_ok": bool, "q_mono": bool, "q1_vs_q5_diff": float|None,
  "q1_vs_q5_ok": bool, "quantile_method": str,

  # Step 4
  "robustness_flag": "stable"|"fragile"|None, "rolling_std": float|None,
  "rolling_median": float|None, "rolling_sign_ch": int|None,
  "rolling_idx": list[int], "rolling_corr": list[float],

  # Shuffle
  "shuffle_corr": float|None, "shuffle_ok": bool,

  # Performance
  "win_rate_long": float|None, "win_rate_short": float|None,
  "avg_y_long": float|None, "avg_y_short": float|None,
  "avg_sl_dist_long": float|None, "avg_sl_dist_short": float|None,

  # Chart data (injected into HTML report)
  "hist_signal": {"labels": [...], "values": [...]},  # bps
  "hist_flat": {"labels": [...], "values": [...]},
  "box_long": {"q1", "median", "q3", "whisker_lo", "whisker_hi", "n"},
  "box_short": {...}, "box_flat": {...},
}
```

---

## 4.4 — Multi-Asset Runner (runner.py)

**Notebook entry point**:
```python
from pipeline.runner import run_section4_all_assets
from strategies.sweep_lq import SweepLQStrategy

df_summary = run_section4_all_assets(
    aligned_data,
    strategy = SweepLQStrategy(),
    tf       = "15min",
    params   = {
        "horizon_h":  8,
        "expiry_days": 3,
        "tf_minutes":  15,
        "use_mtf":    True,
    },
    generate_report = True,
    open_browser    = True,
    output_dir      = "Reports",
)
```

**aligned_data structure**:
```python
aligned_data = {
    "15min": {
        "assets": ["EURUSD", "NASDAQ", ...],
        "open":   pd.DataFrame(index=ts_15min),  # columns = assets
        "high":   pd.DataFrame(...),
        "low":    pd.DataFrame(...),
        "close":  pd.DataFrame(...),
    },
    "4h": { ... },   # optional if use_mtf=True
    "1D": { ... },
}
```

**Console output** (compact — full detail in HTML report):
```
Section 4  |  SweepLQ_Engulfing_MTF  |  15min  H=8
  ✅ GO (1)    : NASDAQ
  ❌ NO GO (7) : EURUSD, GBPUSD, XAUUSD, SP500, USDJPY, USDCAD, AUDUSD
  → Reports/Section4_Report_15min.html
```

**Returned DataFrame columns**:
`Asset, Strategy, Signals, Long, Short, Tests_OK, WR_Long, WR_Short, SL_Long_%, Robustness, Fail_Step, Decision`

---

## 4.5 — Interactive HTML Report (report.py)

Standalone HTML file (~95 KB), dark mode, Chart.js 4.4.1 from CDN.

**Report structure**:
```
Header: Title, TF, Horizon, Strategy, GO/NO GO pills

Overview strip (KPIs): assets scanned, GO list, NO GO list, total signals, bars/asset

Test heatmap — all assets
  Columns with ⓘ tooltips: Asset, Decision, Steps, Signals,
  E0 Sanity, E1 Spearman p, MI, E2 KS p, T-test p, Wilcoxon p,
  E3 Quantile, E4 Rob., Shuffle p, WR Long, WR Short, SL Long%

Per-asset detailed analysis (tabs)
  For each asset:
    GO/NO GO banner + reason + key metrics
    Funnel strip: E0 ✅ › E1 ✅ › E2 ✅ › E3 ❌ › E4 ⚠️ · Shuffle ρ=x
    4 Chart.js charts + inline dynamic interpretation:
      V2. Y Signal vs Flat distribution (overlapping histogram)
      V3. Rolling Spearman ρ (time series)
      V4. Boxplot Y Long / Short / Flat (bps × 10⁴)
      V5. Radar 4 blocking steps
    Detailed analysis (4 cards): KS, Rolling, Boxplot, Radar
      → each card: real metrics + verdict vs threshold + actionable insight
    Summary & recommendations (actionable bullet points)
```

**13 tooltips** (3-section structure each): Definition · Thresholds · How to act

**Verdict color rules**:
- Red badge (NO GO) only if the asset's global decision is NO GO
- If asset is globally GO → partial negative verdicts display in orange, never red

**Generation**:
```python
from pipeline.report import generate_html_report
generate_html_report(all_results, tf="15min", horizon_h=8,
                     output_dir="Reports", open_browser=True)
```

---

## 4.6 — Real Results (SweepLQ strategy, 2020-2023, 93,192 bars/asset)

| Asset  | Signals | Tests OK | WR Long | WR Short | SL Long% | Decision |
|--------|---------|----------|---------|----------|----------|----------|
| NASDAQ | 1,152   | 4/4      | 52.6%   | 48.5%    | 0.367%   | ✅ GO    |
| GBPUSD | 1,052   | 3/4      | 48.5%   | 47.8%    | 0.122%   | ❌ NO GO |
| EURUSD | 1,069   | 3/4      | 52.5%   | 50.8%    | 0.099%   | ❌ NO GO |
| USDJPY | 1,088   | 3/4      | 52.1%   | 47.0%    | 0.123%   | ❌ NO GO |
| XAUUSD | 994     | 2/4      | 45.8%   | 53.2%    | 0.227%   | ❌ NO GO |
| SP500  | 1,113   | 2/4      | 54.3%   | 53.6%    | 0.279%   | ❌ NO GO |

**NASDAQ GO diagnostic** (only validated asset):
- Spearman ρ=0.021 p=0.021, MI=0.013, KS p=0.042 → E1+E2 ✅
- Monotone quantile ✅, net Long alpha = +1.67 bps
- Rolling std=0.042, 78% positive windows → Stable ✅
- Shuffle ρ=−0.048 → ⚠️ monitor (possible bias in build_payload)
- Weak but present Long edge — IQR Long 40% > Flat → strict SL required
- Short signal to filter: Short median (−0.43 bps) < Flat (+1.62 bps)

---

## 4.7 — Known Bugs & Applied Fixes

**Walrus operator bug in compute_market_bias**:
```python
# ❌ WRONG — walrus in condition causes bias=0 everywhere
if (bull := condition1) | (bear := condition2): ...

# ✅ CORRECT — explicit variables
c1 = c.shift(1)
bull = condition1_using_c1
bear = condition2_using_c1
bias = pd.Series(0.0, index=df.index)
bias[bull] = 1.0
bias[bear] = -1.0
```

**French apostrophes in JS**: strings delimited by `'...'` containing `l'edge`, `d'entrée` break the parser. Replace with Unicode typographic apostrophe `'` (U+2019) which has no syntactic role in JS.

**Double synthesis in report**: never generate synthesis in both `renderPanel()` AND `buildInterpSection()` — keep only `interpSynthese(d)` called from `buildInterpSection`.

---

## 4.8 — GO / NO GO Gates Summary

| Test | GO Threshold | Note |
|------|-------------|------|
| n_signals | ≥ 100 | BLOCKING |
| Spearman p-value | < 0.05 | OR with MI |
| Mutual Information | > 0.01 | OR with Spearman |
| KS p-value | < 0.05 | OR with T-test or Wilcoxon |
| T-test p-value | < 0.05 | OR with KS or Wilcoxon |
| Wilcoxon p-value | < 0.05 | OR with KS or T-test |
| Quantile trend | Monotone OR diff > 1 bps | CRITICAL (blocking) |
| Rolling std | < 0.15 | NON-BLOCKING — flag only |
| Shuffle \|ρ\| | < 0.03 | INFO — alert if exceeded |