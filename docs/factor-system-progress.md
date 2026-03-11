# Factor System - Development Progress

> Track file for factor system development.
> Read `docs/factor-system-spec.md` for full design specification.

## Current Phase: Phase 3 COMPLETE — Signal Pool Integration

## Development Rules

- Factor system is an independent module — do NOT modify existing signal
  detection, attribution analysis, or any core trading logic (Phase 1-2)
- Each Phase must be confirmed with user before moving to next Phase
- New background services must have an on/off switch via env variable
  (`FACTOR_ENGINE_ENABLED=true/false`)
- Database changes follow existing ORM + migration conventions
  (models.py first, migration script if needed, register in migration_manager)
- All code and comments in English, UI text uses i18n (en.json + zh.json)
- No temporary test scripts committed to git
- Frontend Loading animation must use PacmanLoader (`@/components/ui/pacman-loader.tsx`)

## Completed

### Phase 1: Factor Computation Engine + Effectiveness Dashboard ✅

**Database (models.py)**
- [x] `FactorValue` table — symbol/period/factor_name/value/timestamp, unique constraint on (exchange, symbol, period, factor_name, timestamp)
- [x] `FactorEffectiveness` table — IC/ICIR/win_rate/decay per factor×symbol×period×forward_period×calc_date
- [x] Migration: `create_factor_system_tables.py`, `add_exchange_to_factor_effectiveness.py`

**Backend Services**
- [x] `factor_registry.py` — 22 factors across 5 categories (Momentum, Trend, Volatility, Volume, Microstructure)
- [x] `factor_computation_service.py` — scheduled every 1h, computes all registered factors from K-line data, supports technical/microstructure/derived types, progress tracking
- [x] `factor_effectiveness_service.py` — daily batch at UTC 01:00, 500-bar lookback, IC/ICIR/win_rate across 4 forward windows (1h/4h/12h/24h), progress tracking
- [x] Env switch: `FACTOR_ENGINE_ENABLED=true` in docker-compose.yml, startup.py conditional start

**Backend API (factor_routes.py)**
- [x] `GET /api/factors/library` — full factor registry
- [x] `GET /api/factors/values` — latest factor values per symbol/period/exchange
- [x] `GET /api/factors/effectiveness` — effectiveness ranking with sort_by support
- [x] `GET /api/factors/effectiveness/{name}/history` — IC trend over time
- [x] `GET /api/factors/status` — engine status, last compute time from DB
- [x] `POST /api/factors/compute` — async background thread, non-blocking
- [x] `GET /api/factors/compute/estimate` — pre-compute symbol list + time estimate
- [x] `GET /api/factors/compute/progress` — real-time progress (phase/symbol/completed/total)

**Frontend (FactorLibrary.tsx)**
- [x] Factor Library page with sidebar navigation (Flask icon)
- [x] Exchange selector (Hyperliquid/Binance) + Symbol selector from watchlist
- [x] Prediction Window selector (1h/4h/12h/24h) with tooltip explaining it's not K-line period
- [x] Category filter badges (All/Momentum/Trend/Volatility/Volume/Microstructure)
- [x] Data table: Factor Name (with description tooltip), Category, Value (1h K-line), IC, ICIR, Win Rate, Samples
- [x] IC/ICIR/Win Rate sortable columns (click to sort by |value|) with tooltip explanations
- [x] IC color coding: green (|IC|≥0.05), yellow (|IC|≥0.02), grey (weak)
- [x] Manual Compute: confirm dialog with symbol badges + estimate → PacmanLoader progress bar → result summary
- [x] Last Update from DB (persists across restarts), Next Compute countdown
- [x] Full i18n (en.json + zh.json)

**Known Issues / Tech Debt**
- Factor computation uses `calculate_indicators()` from technical_indicators.py — not pandas-ta directly as spec planned. Works fine, but if we need 130+ indicators later, may need pandas-ta integration.
- Effectiveness `_compute_symbol` iterates all 500 bars × 22 factors with sub-slicing — O(n²) for indicators. Acceptable for current scale (~2 symbols), may need optimization if watchlist grows large.
- `decay_half_life` field always NULL — decay curve calculation not yet implemented.

### Phase 2: Custom Factor Engine + AI Factor Mining + Web Search ✅

**2A: Custom Factor Expression Engine**
- [x] `factor_expression_engine.py` — asteval + pandas-ta based safe expression evaluator
- [x] FUNCTION_REGISTRY: 69 functions across 9 categories (Moving Average, Momentum, Trend, Volatility, Volume, Time Series, Cross-Section, Math, Conditional)
- [x] `_safe_float()` helper for bool/object dtype → float conversion (fixes ufunc errors)
- [x] `get_registry_grouped()` method for API consumption
- [x] `validate()` — syntax check without execution
- [x] `execute()` — full execution against K-line data, returns pandas Series
- [x] `evaluate_ic()` — compute IC/ICIR/win_rate across forward periods
- [x] Dependencies: `asteval`, `pandas-ta` added to pyproject.toml

**Database**
- [x] `CustomFactor` table — id, name, expression, description, category, source (manual/ai), is_active, created_at
- [x] `HyperAiProfile.tool_configs` field — stores encrypted external tool API keys

**Backend API**
- [x] `GET /api/factors/expression-functions` — returns flat + grouped function registry with metadata
- [x] `POST /api/factors/validate-expression` — syntax validation
- [x] Custom factors saved via AI `save_factor` tool, listed in `/api/factors/library`
- [x] Custom factors computed via AI `compute_factor` tool + scheduled computation
- [x] `GET /api/hyper-ai/tools` — list external tools with config status
- [x] `PUT /api/hyper-ai/tools/{tool_name}/config` — save tool config with validation
- [x] `DELETE /api/hyper-ai/tools/{tool_name}/config` — remove tool config

**Hyper AI Tools**
- [x] `get_factor_functions` — on-demand function reference (token-efficient, replaces static listing in system prompt)
- [x] `evaluate_factor` — test expression against real data, returns IC/ICIR/win_rate
- [x] `save_factor` — save validated expression to factor library
- [x] `edit_factor` — edit existing custom factor
- [x] `compute_factor` — run factor across all watchlist symbols
- [x] `query_factors` — query factor library + effectiveness (serves as recommend_factors too)
- [x] `web_search` — Tavily API integration with graceful no-key fallback
- [x] `load_skill` — factor-mining skill workflow guide

**External Tool Registry (`hyper_ai_tool_registry.py`)**
- [x] Generic `EXTERNAL_TOOL_REGISTRY` — extensible tool metadata + config schema
- [x] Encrypted API key storage via `utils.encryption`
- [x] Tavily validation function
- [x] Config CRUD helpers: get/set/remove tool configs

**Frontend**
- [x] `ToolConfigModal.tsx` — generic tool config dialog (dynamic fields from registry)
- [x] HyperAiPage.tsx Tools section in right panel
- [x] Custom factors displayed in Factor Library alongside built-in factors
- [x] i18n for tools and factor-mining skill

**AI Prompt & Skills**
- [x] System prompt updated: `get_factor_functions` as first step in factor workflow
- [x] `factor-mining` skill (SKILL.md): 4-phase workflow with CHECKPOINTs
- [x] Factor mining memory via existing `save_memory` tool (AI guided to save hypotheses/results in skill)

**Design Decisions**
- `recommend_factors` tool NOT needed — `query_factors` with symbol param returns effectiveness ranking, AI interprets contextually
- Phase 1's 22 factors keep `calculate_indicators()` path (stable); new factors use expression engine
- Function list NOT in system prompt — AI calls `get_factor_functions` on demand (saves tokens)

## Completed

### Phase 3: Signal Pool Integration + Built-in Factor Library Expansion ✅

**Goal**: Factor signals become usable as signal pool triggers. Built-in factor library
expanded from 22 to 86 using expression engine.

#### 3A: Built-in Factor Library Expansion (22 → 86) ✅

- [x] Migration `insert_builtin_expression_factors.py`: 64 factors, idempotent, registered
- [x] Factor Library UI shows builtin_expression factors with distinct badge
- [x] All 64 expressions verified passing via expression engine

#### 3B: Factor Signal Detection (Real-time + Backtest) ✅

- [x] `signal_detection_service.py`: `_get_metric_value()` routes `factor:` prefix to `_get_factor_metric_value()`
- [x] `_get_factor_metric_value()`: loads CustomFactor expression → K-lines → expression engine → last value
- [x] Factor metrics follow standard single-value path (operator + threshold), no downstream changes
- [x] `signal_backtest_service.py`: `_find_triggers_in_range()` routes `factor:` to `_find_factor_triggers_in_range()`
- [x] `_find_factor_triggers_in_range()`: loads K-lines with 200-bar warm-up → expression engine once → edge detection at K-line close timestamps
- [x] Works for both Signal Backtest UI and Program Backtest via `backtest_pool()`

#### 3C: Frontend — Signal Creation UI ✅

- [x] `SignalManager.tsx`: loads factor library from `/api/factors/library` on mount
- [x] Metric selector: split into "Market Flow" + "Factor Library" sections with category filter
- [x] Factor selection: shows expression code block, FlaskConical icon, `factor:<name>` metric format
- [x] Statistical analysis: factor metrics use `/api/factors/evaluate` API → shows IC/ICIR across 4 windows + current value
- [x] `formatCondition`: factor metrics display as `⚗ FACTOR_NAME`
- [x] i18n: 5 new keys in en.json + zh.json

#### 3D: AI Integration ✅

**Signal AI:**
- [x] `SIGNAL_SYSTEM_PROMPT`: added "Factor Indicators" section with format, categories, timing
- [x] Added "Option 4: Factor Signal" output format example
- [x] `get_indicators_batch`: accepts `factor:<name>` → loads K-lines → expression engine → percentiles + latest value
- [x] `predict_signal_combination`: factor signals use `_find_factor_signal_triggers()` with K-line edge detection

**Hyper AI:**
- [x] `save_signal_pool` tool: metric description updated to include `factor:<name>` format
- [x] `hyper_ai_system_prompt.md`: Signal Pool section updated with factor signal note
- [x] `run_signal_backtest`: NO changes needed (backtest_pool already factor-aware)

### Phase 4: AI Trader & Program Trader Integration
- [ ] AI Trader: factor context injection into prompts
- [ ] Program Trader: data_provider factor API
- [ ] Theory vs Reality dashboard (factor IC vs actual signal win rate)

## Decisions Log

- 2026-03-07: Factor values update follows K-line period, not fixed interval
- 2026-03-07: Factor effectiveness computed once per day (batch)
- 2026-03-07: Hyper AI on-demand validation is separate from scheduled tasks
- 2026-03-07: Web search uses Tavily, user-provided key, config in AI panel
- 2026-03-07: Factor effectiveness and signal threshold are decoupled concepts
- 2026-03-09: Manual compute runs in background thread to avoid blocking uvicorn event loop
- 2026-03-09: Symbol service imports fixed (module-level functions, not class instances)
- 2026-03-09: Last compute time persisted via DB MAX(created_at), not just in-memory
- 2026-03-09: IC/ICIR sort by absolute value (both positive and negative IC are useful)
- 2026-03-09: Phase 2 core = custom factor expression engine (user/AI submit arbitrary formulas for evaluation)
- 2026-03-09: Expression syntax uses TA-style naming (EMA/RSI/MACD), not WorldQuant-style (ts_mean/cs_rank)
- 2026-03-09: Factor name is just a display label (any language OK), expression is the computation formula
- 2026-03-09: Custom factors are global (not per-user), AI and manual share same infrastructure
- 2026-03-09: Expression safety via Python ast module (whitelist safe nodes, reject imports/exec/file ops)
- 2026-03-10: Use open-source libs instead of reinventing: asteval (safe eval) + pandas-ta (130+ TA indicators)
- 2026-03-10: Phase 1's 22 factors keep calculate_indicators() path; pandas-ta only for custom expression engine
- 2026-03-10: Expanding built-in library (130+) is a config task after expression engine is done (insert pre-defined expressions)
- 2026-03-10: recommend_factors tool dropped — query_factors suffices for AI to recommend contextually
- 2026-03-10: FUNCTION_REGISTRY as single source of truth (69 functions, 9 categories), exposed via API + AI tool
- 2026-03-11: Phase 3 scope confirmed: signal pool integration + built-in library expansion (22→86)
- 2026-03-11: New 64 factors stored as CustomFactor with source="builtin_expression", expression engine computes
- 2026-03-11: Factor signal metric format: `factor:<factor_name>`, standard dict output, no downstream changes
- 2026-03-11: Factor detection uses closed K-lines only, trigger points at K-line close boundaries
- 2026-03-11: Signal backtest for factors: load K-lines → expression engine → iterate closes → edge detect
- 2026-03-11: backtest_pool() is unified entry — factor backtest works for both signal UI and program backtest
- 2026-03-11: Price-level indicators converted to deviation factors (e.g. Ichimoku → close deviation ratio)
- 2026-03-11: Candlestick patterns converted to continuous ratios (body/shadow percentages, not binary)
- 2026-03-11: Signal AI tools (get_indicators_batch, predict_signal_combination) must support factor metrics
- 2026-03-11: Hyper AI save_signal_pool tool must document factor:<name> metric format
- 2026-03-11: AI integration is critical — both Signal AI and Hyper AI must know factors can be signal triggers
- 2026-03-11: Signal AI get_indicators_batch: enum removed, accepts free-form strings including factor:<name>
- 2026-03-11: Factor backtest in predict_signal_combination: uses _find_factor_signal_triggers() with K-line data
- 2026-03-11: Frontend factor selector: two-section dropdown (Market Flow + Factor Library) with category filter
- 2026-03-11: Factor analysis in signal dialog: uses /api/factors/evaluate for IC/ICIR display instead of metric analyze API
