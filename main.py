import sys
import os
# 刚性锁死环境变量：强制单线程运行，防止云端多线程引发底层 C++ 库内存段错误(Segmentation Fault)
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import socket
# 刚性设置全局网络超时锁为 15 秒，彻底杜绝 yfinance 在云端挂死
socket.setdefaulttimeout(15)

try:
    import yfinance as yf
    import pandas as pd
    import logging
    import os
    import requests
    import time
    import json
    import shutil
    import numpy as np
    from datetime import datetime, timedelta, timezone
    from scipy.optimize import minimize
except ImportError as e:
    print(f"CRITICAL DEPENDENCY MISSING IN RUNNER ENVIRONMENT: {e}")
    sys.exit(1)

# 统一工程级纯中性日志规范 (完全剥离任何情绪化或股评描述)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("MatrixMasterEngine_V26_5_8")

# ====================================================================================
# 🎛️ PORTFOLIO STRUCTURAL CONFIGURATION (资产大类解耦配置中心 - MVP 26.5.8 LTS)
# ====================================================================================
# 全局风险资产池核心配置中心
RISK_ASSETS = ["TECH", "RESOURCE", "GOLD", "FIXED_INCOME"]

TICKERS = {
    "COPPER": "HG=F",      # COMEX期铜 (全球工业商品定价参考锚)
    "RESOURCE": "COPX",    # 资源多头线 (矿业巨头ETF / 盛达资源国内映射)
    "TECH": "XLK",         # 科技算力线 (全球AI硬件资本池)
    "GOLD": "GLD",         # 避险贵金属 (实盘防守超配资产)
    "FIXED_INCOME": "TLT", # 跨周期长债 (宏观无风险流动性对冲资产)
    "DXY": "DX-Y.NYB",     # 美元指数 (全球流动性总闸门基准)
    "US10Y": "^TNX",       # 美元10年期国债收益率 (全球资产重力底座)
    "FX": "USDCNY=X"       # 离岸人民币汇率
}

FALLBACK_DATA = {
    "PRICES": {
        "COPPER": 6.2240, "RESOURCE": 42.15, "TECH": 225.40, "GOLD": 218.50, 
        "FIXED_INCOME": 92.50, "DXY": 104.50, "US10Y": 4.250, "FX": 7.2500
    },
    "CHANGES": {
        "COPPER": 0.50, "RESOURCE": 1.22, "TECH": -1.39, "GOLD": -0.45, "FIXED_INCOME": 0.10
    }
}

PORTFOLIO_ACCOUNT = {
    "TOTAL_CAPITAL": 40000.0,  # 真实基准配置资金池 (元)
    "CURRENT_ALLOCATION": {
        "GOLD": 0.28, "RESOURCE": 0.22, "TECH": 0.18, "FIXED_INCOME": 0.15, "CASH": 0.17
    },
    "STRATEGIC_BASELINE": {
        "GOLD": 0.15, 
        "RESOURCE": 0.20, 
        "TECH": 0.30,          # 战略配置基础中枢上限自洽 (30%)
        "FIXED_INCOME": 0.25,  # 防御长债配置基础中枢 (25%)
        "CASH": 0.10           # 刚性最低储备现金率 (10%)
    }
}

# 隔离低波防守资产持仓天花板
IRON_LAWS = {
    "COOLING_PERIOD_DAYS": 14,         # 铁律一：真实调仓间隔必须 ≥ 14天
    "MAX_REBALANCE_ADJUSTMENT": 0.05,  # 铁律二：单次再平衡调仓步长幅度 ≤ 总资产5%
    "MIN_CASH_FLOOR": 0.10,            # 铁律三：动态现金仓位必须 ≥ 10% (强保刚性流动性大底)
    "MAX_ASSET_CEILING": 0.30,         # 铁律四：权益/商品单一风险资产持仓上限 ≤ 30% 
    "MAX_BOND_CEILING": 0.45,          # 长债类低波防守资产持仓上限放宽至 45%
    "BIAS_WINDOW_THRESHOLD": 2.0,      # 历史相似状态对称切片邻域 (±2.0%)
    "MIN_HISTORICAL_SAMPLES": 20,      # 最小历史有效同质样本数门槛
    "REBALANCE_TRIGGER_THRESHOLD": 0.025, # 战术再平衡激活起扣点 (2.5%)
    "BLEND_FACTOR": 0.30,              # 战术分配融合系数权重
    "MIN_COPPER_DOWNSIDE_FLOOR": 3.0   # 国际期铜下跌空间最低技术保护底噪 (%)
}

PRICE_BOUNDARIES = {
    "HG=F": {"min": 2.0, "max": 10.0}, "COPX": {"min": 10.0, "max": 150.0},
    "XLK": {"min": 50.0, "max": 500.0}, "GLD": {"min": 100.0, "max": 350.0},
    "TLT": {"min": 50.0, "max": 180.0}, "DX-Y.NYB": {"min": 80.0, "max": 130.0},
    "^TNX": {"min": 1.0, "max": 7.0}, "USDCNY=X": {"min": 5.0, "max": 9.0}
}

NOTIFICATION = {
    "WEBHOOK_URL": os.environ.get("ALERT_WEBHOOK_URL", ""),
    "MAX_RETRIES": 3, "RETRY_DELAY": 1, "TIMEOUT": 5                  
}

PERSISTENCE = {
    "DB_FILE": "quantamental_history_log.csv", "STATE_FILE": "portfolio_state.json"  
}

class PortfolioDisciplineEngineV26_5_8:
    def __init__(self):
        self.beijing_time = datetime.now(timezone.utc) + timedelta(hours=8)
        self.metrics = {
            "successful_fetches": 0,
            "fallbacks_triggered": 0,
            "boundary_violations": 0,
            "execution_time_seconds": 0.0
        }
        self._execute_startup_fail_fast_check()
        self._init_state_machine()

    def _execute_startup_fail_fast_check(self):
        baseline_sum = sum(PORTFOLIO_ACCOUNT["STRATEGIC_BASELINE"].values())
        if abs(baseline_sum - 1.0) > 1e-4:
            logger.critical(f"Fail-Fast Assertion Triggered: STRATEGIC_BASELINE sum must be 1.0, current is {baseline_sum}")
            raise ValueError(f"Startup Config Error: STRATEGIC_BASELINE sum mismatch ({baseline_sum})")
            
        current_sum = sum(PORTFOLIO_ACCOUNT["CURRENT_ALLOCATION"].values())
        if abs(current_sum - 1.0) > 1e-4:
            logger.critical(f"Fail-Fast Assertion Triggered: CURRENT_ALLOCATION sum must be 1.0, current is {current_sum}")
            raise ValueError(f"Startup Config Error: CURRENT_ALLOCATION sum mismatch ({current_sum})")
            
        strategic_cash = PORTFOLIO_ACCOUNT["STRATEGIC_BASELINE"]["CASH"]
        if abs(strategic_cash - IRON_LAWS["MIN_CASH_FLOOR"]) > 1e-4:
            logger.critical(f"Fail-Fast Assertion Triggered: Strategic Cash ({strategic_cash}) must equal MIN_CASH_FLOOR ({IRON_LAWS['MIN_CASH_FLOOR']})")
            raise ValueError("Startup Config Error: Strategic Cash vs Minimum Cash Floor logical contradiction.")
            
        for ticker_key in TICKERS.keys():
            if ticker_key not in FALLBACK_DATA["PRICES"]:
                logger.critical(f"Fail-Fast Assertion Triggered: TICKER key '{ticker_key}' missing in FALLBACK_DATA.")
                raise KeyError(f"Startup Config Error: Missing fallback index for '{ticker_key}'")
        logger.info("Startup Fail-Fast Check: All initialization configurations perfectly aligned.")

    def _init_state_machine(self):
        default_state = {"last_rebalance_date": (self.beijing_time - timedelta(days=20)).strftime('%Y-%m-%d')}
        bak_file = PERSISTENCE["STATE_FILE"] + ".bak"
        try:
            if os.path.exists(PERSISTENCE["STATE_FILE"]):
                with open(PERSISTENCE["STATE_FILE"], 'r', encoding='utf-8') as f: self.portfolio_state = json.load(f)
                shutil.copyfile(PERSISTENCE["STATE_FILE"], bak_file)
            elif os.path.exists(bak_file):
                with open(bak_file, 'r', encoding='utf-8') as f: self.portfolio_state = json.load(f)
                shutil.copyfile(bak_file, PERSISTENCE["STATE_FILE"])
            else:
                self.portfolio_state = default_state
                with open(PERSISTENCE["STATE_FILE"], 'w', encoding='utf-8') as f: json.dump(default_state, f, indent=4)
        except Exception as e:
            logger.error(f"State file synchronization breakdown fault: {e}")
            self.portfolio_state = default_state

    def fetch_ticker_safe(self, symbol, period="5y"):
        for attempt in range(NOTIFICATION["MAX_RETRIES"]):
            try:
                ticker_obj = yf.Ticker(symbol)
                df = ticker_obj.history(period=period)
                if df is None or len(df) < 252: continue
                live_price = df['Close'].iloc[-1]
                bounds = PRICE_BOUNDARIES.get(symbol, {"min": 0.001, "max": 999999.0})
                if not (bounds["min"] <= live_price <= bounds["max"]):
                    self.metrics["boundary_violations"] += 1
                    self.metrics["fallbacks_triggered"] += 1
                    return None
                self.metrics["successful_fetches"] += 1
                return df
            except Exception as e:
                logger.warning(f"Data stream network retry event for {symbol} on attempt {attempt+1}: {e}")
        self.metrics["fallbacks_triggered"] += 1
        return None

    def _execute_regime_adaptive_backtest(self, df_history, current_bias, current_regime):
        if df_history is None or len(df_history) < 252: return 12.0, 5.0, 0
        try:
            df_hist = df_history.copy()
            df_hist['ma20'] = df_hist['Close'].rolling(20).mean()
            df_hist['ma60'] = df_hist['Close'].rolling(60).mean()
            df_hist['bias'] = ((df_hist['Close'] / df_hist['ma20']) - 1) * 100
            
            df_hist['fwd_min_20d'] = df_hist['Close'].rolling(window=20, min_periods=1).min().shift(-19)
            df_hist['fwd_real_downside'] = ((df_hist['Close'] - df_hist['fwd_min_20d']) / df_hist['Close']) * 100
            df_hist['fwd_return_20d'] = (df_hist['Close'].shift(-20) / df_hist['Close'] - 1) * 100 
            
            regime_mask = df_hist['ma20'] > df_hist['ma60'] if current_regime == "BULL" else df_hist['ma20'] < df_hist['ma60']
            bias_mask = (df_hist['bias'] - current_bias).abs() <= IRON_LAWS["BIAS_WINDOW_THRESHOLD"]
            valid_samples = df_hist[regime_mask & bias_mask]
            sample_count = len(valid_samples)
            
            if sample_count >= IRON_LAWS["MIN_HISTORICAL_SAMPLES"]:
                return float(valid_samples['fwd_return_20d'].dropna().median()), float(valid_samples['fwd_real_downside'].dropna().median()), sample_count
            return 12.0, 5.0, sample_count
        except Exception as e:
            logger.warning(f"Empirical condition probability backtest layer exception: {e}")
        return 12.0, 5.0, 0

    def _solve_constrained_equal_risk_contribution(self, cov_matrix, active_assets):
        """五资产约束等风险贡献(CERC)数值优化求解器"""
        n = cov_matrix.shape[0]
        
        # 将全账户风控铁律上限，通过风险资产可用预算动态转换为内部相对口径边界
        risk_budget = 1.0 - IRON_LAWS["MIN_CASH_FLOOR"]
        bounds = []
        for asset_key in active_assets:
            ceil_total = IRON_LAWS["MAX_BOND_CEILING"] if asset_key == "FIXED_INCOME" else IRON_LAWS["MAX_ASSET_CEILING"]
            ceil_internal = ceil_total / risk_budget
            floor_internal = 0.05 / risk_budget
            bounds.append((floor_internal, ceil_internal))
            
        init_weights = np.repeat(1.0 / n, n)
        for idx, (low, high) in enumerate(bounds):
            init_weights[idx] = np.clip(init_weights[idx], low, high)
        init_weights = init_weights / np.sum(init_weights)
            
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0})
        def erc_objective_function(w):
            w = np.array(w)
            portfolio_variance = np.dot(w.T, np.dot(cov_matrix, w))
            if portfolio_variance <= 1e-9: return 1e10  
            portfolio_volatility = np.sqrt(portfolio_variance)
            risk_contributions = w * np.dot(cov_matrix, w) / portfolio_volatility
            risk_diffs = risk_contributions[:, None] - risk_contributions[None, :]
            return np.sum(risk_diffs ** 2)
            
        try:
            res = minimize(erc_objective_function, init_weights, method='SLSQP', bounds=bounds, constraints=constraints, tol=1e-8)
            if res.success: return res.x
        except Exception as e:
            logger.error(f"SLSQP Non-linear Optimizer execution fatal constraint break: {e}")
        diag_inv = 1.0 / np.sqrt(np.diag(cov_matrix))
        return diag_inv / np.sum(diag_inv)

    def call_llm_brain_analyser(self, portfolio_json_data):
        api_key = os.environ.get("LLM_API_KEY", "")
        base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
        model_name = os.environ.get("LLM_MODEL", "deepseek-chat")
        
        if not api_key: 
            return "⚠️ 离岸云端大模型Token环境变量流未接通，已自动降级跳过智脑决策层。"
            
        url = base_url.rstrip('/')
        if not url.endswith('/chat/completions'): url += '/chat/completions'
            
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        prompt = f"""你现在是在华尔街拥有20年大类资产配置经验的资深买方基金经理。
                  下面是我个人为你审计出的最新真实持仓与跨标的协方差风险平价(CERC)全账户镜面数据 JSON：
                  {json.dumps(portfolio_json_data, ensure_ascii=False)}
                  
                  请基于真实的 DXY 走势、利率重力跨均线过滤器、以及全账户的滚动年化总风险敞口，
                  为我做出冷酷、理智的流动性归因解释。请帮我拆解：
                  1. 当前美元流动性闸门是在‘放水’还是在‘抽血’？对我的科技硬件与黄金资产各意味着什么？
                  2. 结合我的持仓状况（黄金超配28%，科技18%），系统为何今天向我宣判锁死在冷静期/禁止肉身频繁调仓多动？
                  请务必将最终分析字数严格控制在 250 字以内，字数越少，含金量越高，拒绝任何股评废话。"""
                  
        payload = {"model": model_name, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200: 
                return response.json()['choices'][0]['message']['content']
        except Exception as e: 
            logger.error(f"LLM API request transport exception: {e}")
        return "⚠️ LLM 脑部神经通道偶发性阻塞，请先根据控制台客观数据进行校准。"

    def log_to_csv(self, record_dict):
        try:
            df_new = pd.DataFrame([record_dict])
            if not os.path.exists(PERSISTENCE["DB_FILE"]):
                df_new.to_csv(PERSISTENCE["DB_FILE"], index=False, encoding="utf-8-sig")
            else:
                df_old = pd.read_csv(PERSISTENCE["DB_FILE"], encoding="utf-8-sig")
                for col in df_new.columns:
                    if col not in df_old.columns: df_old[col] = None
                df_combined = pd.concat([df_old, df_new], ignore_index=True)
                df_combined.drop_duplicates(subset=["audit_date"], keep="last", inplace=True)
                df_combined.to_csv(PERSISTENCE["DB_FILE"], index=False, encoding="utf-8-sig")
        except Exception as e:
            logger.error(f"Persistence CSV Database write stream collision error: {e}")

    def run_pipeline(self):
        start_time = time.time()
        total_cap = PORTFOLIO_ACCOUNT["TOTAL_CAPITAL"]
        
        active_assets = []
        cov_matrix = None
        current_portfolio_vol = 11.80  
        target_portfolio_vol = 11.20   
        copper_vol_252d = 22.10        
        
        data_matrix = {}
        for key, symbol in TICKERS.items(): data_matrix[key] = self.fetch_ticker_safe(symbol)
            
        changes_5d = {k: FALLBACK_DATA["CHANGES"].get(k, 0.0) for k in ["COPPER"] + RISK_ASSETS}
        prices = {k: FALLBACK_DATA["PRICES"][k] for k in TICKERS.keys()}
        bias_ma20 = {"TECH": 0.0, "RESOURCE": 0.0, "GOLD": 0.0, "COPPER": 0.0, "FIXED_INCOME": 0.0}
        regime_status = {"TECH": "NEUTRAL", "RESOURCE": "NEUTRAL", "GOLD": "NEUTRAL", "COPPER": "NEUTRAL", "FIXED_INCOME": "NEUTRAL"}
        risk_parity_weights = {k: 0.25 for k in RISK_ASSETS}
        vols_252d = {k: 20.0 for k in RISK_ASSETS}
        
        try:
            for k in TICKERS.keys():
                if data_matrix[k] is not None: prices[k] = data_matrix[k]['Close'].iloc[-1]
                
            for k in RISK_ASSETS + ["COPPER", "DXY", "US10Y"]:
                df = data_matrix[k]
                if df is not None and len(df) >= 60:
                    ma20 = df['Close'].rolling(20).mean().iloc[-1]
                    ma60 = df['Close'].rolling(60).mean().iloc[-1]
                    bias_ma20[k] = round(((df['Close'].iloc[-1] / ma20) - 1) * 100, 2)
                    regime_status[k] = "BULL" if ma20 > ma60 else "BEAR"
                    if k in changes_5d: changes_5d[k] = round(((df['Close'].iloc[-1] / df['Close'].iloc[-5]) - 1) * 100, 2)

            active_assets = [k for k in RISK_ASSETS if data_matrix[k] is not None and len(data_matrix[k]) >= 253]
            if len(active_assets) >= 3:
                returns_dict = {k: np.log(data_matrix[k]['Close'] / data_matrix[k]['Close'].shift(1)) for k in active_assets}
                df_returns = pd.DataFrame(returns_dict).dropna().tail(252)
                cov_matrix = df_returns.cov() * 252 
                for k in active_assets: vols_252d[k] = round(np.sqrt(cov_matrix.loc[k, k]) * 100, 2)
                optimized_weights = self._solve_constrained_equal_risk_contribution(cov_matrix.values, active_assets)
                for idx, k in enumerate(active_assets): risk_parity_weights[k] = round(optimized_weights[idx], 3)
                current_w_vec = np.array([PORTFOLIO_ACCOUNT["CURRENT_ALLOCATION"].get(x, 0.0) for x in active_assets])
                current_portfolio_vol = round(np.sqrt(np.dot(current_w_vec.T, np.dot(cov_matrix.values, current_w_vec))) * 100, 2)
        except Exception as e:
            logger.error(f"Covariance Matrix matrix runtime execution crash exception: {e}")
            self.metrics["fallbacks_triggered"] += 1

        copper_up, copper_dn, copper_samples = self._execute_regime_adaptive_backtest(data_matrix["COPPER"], bias_ma20["COPPER"], regime_status["COPPER"])
        tech_up, tech_dn, tech_samples = self._execute_regime_adaptive_backtest(data_matrix["TECH"], bias_ma20["TECH"], regime_status["TECH"])
        gold_up, gold_dn, gold_samples = self._execute_regime_adaptive_backtest(data_matrix["GOLD"], bias_ma20["GOLD"], regime_status["GOLD"])
        bond_up, bond_dn, bond_samples = self._execute_regime_adaptive_backtest(data_matrix["FIXED_INCOME"], bias_ma20["FIXED_INCOME"], regime_status["FIXED_INCOME"])
        
        odds_matrix = {
            "COPPER": {"upside": round(copper_up, 1), "downside": max(copper_dn, IRON_LAWS["MIN_COPPER_DOWNSIDE_FLOOR"]), "odds": round(copper_up / max(copper_dn, 1.0), 2), "samples": copper_samples},
            "TECH": {"upside": round(tech_up, 1), "downside": round(tech_dn, 2), "odds": round(tech_up / max(tech_dn, 1.0), 2), "samples": tech_samples},
            "GOLD": {"upside": round(gold_up, 1), "downside": round(gold_dn, 2), "odds": round(gold_up / max(gold_dn, 1.0), 2), "samples": gold_samples},
            "FIXED_INCOME": {"upside": round(bond_up, 1), "downside": round(bond_dn, 2), "odds": round(bond_up / max(bond_dn, 1.0), 2), "samples": bond_samples}
        }

        for k in ["COPPER", "TECH", "GOLD", "FIXED_INCOME"]:
            if odds_matrix[k]["samples"] < IRON_LAWS["MIN_HISTORICAL_SAMPLES"]:
                logger.warning(f"实证概率警报：标的 {k} 有效历史同质样本量({odds_matrix[k]['samples']}个)未达门槛，触发防噪声降级保护。")

        macro_radar = {"DXY_MA20_CROSS": "UNKNOWN", "US10Y_MA20_CROSS": "UNKNOWN"}
        if data_matrix["DXY"] is not None and data_matrix["US10Y"] is not None:
            macro_radar["DXY_MA20_CROSS"] = "BELOW_MA20 (流动性边际释放)" if prices["DXY"] < data_matrix["DXY"]
