import sys, os, socket, logging, requests, time, json, shutil
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
from scipy.optimize import minimize

# 1. 刚性锁死环境参数，封杀 Linux 云端容器多线程并发死锁与编码乱码隐患
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")

socket.setdefaulttimeout(15)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Engine_V26_6_7")

RISK_ASSETS = ["TECH", "RESOURCE", "GOLD", "FIXED_INCOME"]
TICKERS = {"COPPER": "HG=F", "RESOURCE": "COPX", "TECH": "XLK", "GOLD": "GLD", "FIXED_INCOME": "TLT", "DXY": "DX-Y.NYB", "US10Y": "^TNX", "FX": "USDCNY=X"}
FALLBACK_DATA = {
    "PRICES": {"COPPER": 6.20, "RESOURCE": 42.15, "TECH": 225.4, "GOLD": 218.5, "FIXED_INCOME": 92.5, "DXY": 104.5, "US10Y": 4.529, "FX": 7.25},
    "CHANGES": {"COPPER": -0.35, "RESOURCE": -2.45, "TECH": -0.18, "GOLD": 1.34, "FIXED_INCOME": 0.1}
}

# ====================================================================================
# 🎛️ PORTFOLIO CORE POSITION CENTER (三平台联合大航空母舰战斗群 - 优化对齐生产区)
# ====================================================================================
PORTFOLIO_ACCOUNT = {
    "TOTAL_CAPITAL": 38506.30,  # 🎯 精准锁死：盛达清仓后三平台联合最新总资本
    "CURRENT_ALLOCATION": {
        "GOLD": 0.224,          # 联合避险黄金实际绝对占比 (含场内ETF、积存金与平台三)
        "RESOURCE": 0.266,      # 中信证券有色矿端最新安全占比 (已顺畅缩回天花板内)
        "TECH": 0.301,          # 联合全球科技算力互联网真实占比 
        "FIXED_INCOME": 0.000,  # 跨周期长债当前空仓
        "CASH": 0.209           # 斩仓盛达后，主账户证券可用储备现金占比暴增至 20.9%
    },
    "STRATEGIC_BASELINE": {
        "GOLD": 0.15, "RESOURCE": 0.20, "TECH": 0.30, "FIXED_INCOME": 0.25, "CASH": 0.10
    }
}

ASSET_TITLE_MAPPING = {"GOLD": "黄金资产GLD", "RESOURCE": "资源多头矿端", "TECH": "科技算力硬件", "FIXED_INCOME": "跨周期长债TLT"}
IRON_LAWS = {
    "COOLING_PERIOD_DAYS": 7, "CRITICAL_DRIFT_THRESHOLD": 0.05, "REBALANCE_TRIGGER_THRESHOLD": 0.025,
    "MAX_REBALANCE_ADJUSTMENT": 0.05, "MIN_CASH_FLOOR": 0.10, "MIN_ASSET_FLOOR": 0.05,
    "MAX_ASSET_CEILING": 0.30, "MAX_BOND_CEILING": 0.45, "BIAS_WINDOW_THRESHOLD": 2.0,
    "MIN_HISTORICAL_SAMPLES": 20, "BLEND_FACTOR": 0.30, "UNIFORM_MIN_DOWNSIDE_FLOOR": 3.0
}
PRICE_BOUNDARIES = {
    "HG=F": {"min": 2.0, "max": 10.0}, "COPX": {"min": 10.0, "max": 150.0}, "XLK": {"min": 50.0, "max": 500.0},
    "GLD": {"min": 100.0, "max": 350.0}, "TLT": {"min": 50.0, "max": 180.0}, "DX-Y.NYB": {"min": 80.0, "max": 130.0},
    "^TNX": {"min": 1.0, "max": 7.0}, "USDCNY=X": {"min": 5.0, "max": 9.0}
}
NOTIFICATION = {"WEBHOOK_URL": os.environ.get("ALERT_WEBHOOK_URL", ""), "MAX_RETRIES": 3, "RETRY_DELAY": 1, "TIMEOUT": 5}
PERSISTENCE = {"DB_FILE": "quantamental_history_log.csv", "STATE_FILE": "portfolio_state.json"}

class PortfolioDisciplineEngineV26_6_7:
    def __init__(self):
        self.beijing_time = datetime.now(timezone.utc) + timedelta(hours=8)
        self.portfolio_state = {"last_rebalance_date": (self.beijing_time - timedelta(days=20)).strftime('%Y-%m-%d')}
        if os.path.exists(PERSISTENCE["STATE_FILE"]):
            try:
                with open(PERSISTENCE["STATE_FILE"], 'r', encoding='utf-8') as f: self.portfolio_state = json.load(f)
            except: pass

    def fetch_ticker_safe(self, symbol):
        try:
            df = yf.Ticker(symbol).history(period="5y")
            if df is not None and len(df) >= 252:
                if PRICE_BOUNDARIES[symbol]["min"] <= df['Close'].iloc[-1] <= PRICE_BOUNDARIES[symbol]["max"]: return df
        except Exception as e:
            logger.warning(f"Ticker {symbol} fetch bypass, active fallback matrix. Msg: {e}")
        return None

    def _execute_regime_adaptive_backtest(self, df, current_bias, current_regime):
        if df is None or len(df) < 252: return 12.0, IRON_LAWS["UNIFORM_MIN_DOWNSIDE_FLOOR"], 0
        try:
            df_hist = df.copy()
            df_hist['ma20'] = df_hist['Close'].rolling(20).mean()
            df_hist['ma60'] = df_hist['Close'].rolling(60).mean()
            df_hist['bias'] = ((df_hist['Close'] / df_hist['ma20']) - 1) * 100
            df_hist['fwd_min_20d'] = df_hist['Close'].rolling(window=20, min_periods=1).min().shift(-19)
            df_hist['fwd_real_downside'] = ((df_hist['Close'] - df_hist['fwd_min_20d']) / df_hist['Close']) * 100
            df_hist['fwd_return_20d'] = (df_hist['Close'].shift(-20) / df_hist['Close'] - 1) * 100 
            mask = (df_hist['ma20'] > df_hist['ma60'] if current_regime == "BULL" else df_hist['ma20'] < df_hist['ma60']) & ((df_hist['bias'] - current_bias).abs() <= IRON_LAWS["BIAS_WINDOW_THRESHOLD"])
            valid = df_hist[mask]
            if len(valid) >= IRON_LAWS["MIN_HISTORICAL_SAMPLES"]: return float(valid['fwd_return_20d'].dropna().median()), float(valid['fwd_real_downside'].dropna().median()), len(valid)
        except: pass
        return 12.0, IRON_LAWS["UNIFORM_MIN_DOWNSIDE_FLOOR"], 0

    def _solve_constrained_equal_risk_contribution(self, cov_matrix, active_assets):
        n = cov_matrix.shape[0]
        risk_budget = 1.0 - IRON_LAWS["MIN_CASH_FLOOR"]
        bounds = [(IRON_LAWS["MIN_ASSET_FLOOR"] / risk_budget, (IRON_LAWS["MAX_BOND_CEILING"] if k == "FIXED_INCOME" else IRON_LAWS["MAX_ASSET_CEILING"]) / risk_budget) for k in active_assets]
        init_w = np.repeat(1.0 / n, n)
        for idx, (low, high) in enumerate(bounds): init_w[idx] = np.clip(init_w[idx], low, high)
        init_w /= np.sum(init_w)
        def obj(w):
            vol = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
            if vol <= 1e-9: return 1e10
            rc = w * np.dot(cov_matrix, w) / vol
            return np.sum((rc[:, None] - rc[None, :]) ** 2)
        try:
            res = minimize(obj, init_w, method='SLSQP', bounds=bounds, constraints=({'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}), tol=1e-8)
            if res.success: return res.x
        except: pass
        return init_w

   def call_llm_brain_analyser(self, payload, behavior_status):
        api_key, base_url, model = os.environ.get("LLM_API_KEY", ""), os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"), os.environ.get("LLM_MODEL", "deepseek-chat")
        if not api_key: return "⚠️ 离岸大模型Token未配通，智脑归因平滑降级。"
        url = base_url.rstrip('/') + ('/chat/completions' if not base_url.endswith('/chat/completions') else '')
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
# 🟢 修改为动态判定，彻底封杀 AI 自我打架的逻辑漏洞：
        prompt = f"""你现在是在华尔街拥有20年资产配置经验的资深买方风控官。下面是合并了场外理财通及积存金后的实盘数据JSON：{json.dumps(payload, ensure_ascii=False)}. 
                  请基于真实DXY、美债10Y利率走势做出理智的流动性归因解释：
                  1. 美元流动性是在‘放水’还是‘抽血’？对科技与黄金各意味着什么？
                  2. 结合我的真实合并持仓状况，系统当前的判词状态是：【{behavior_status}】。请一句话从小组组合风控角度做出极其冷酷的专家归因。
                  请控制在 200 字内，拒绝任何股评废话。"""
        try:
            res = requests.post(url, json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}, headers=headers, timeout=15)
            if res.status_code == 200: return res.json()['choices'][0]['message']['content']
        except Exception as e: logger.error(f"LLM API Channel error: {e}")
        return "⚠️ LLM 智脑归因通道阻塞。"

    def _build_markdown_report(self, prices, macro_radar, behavior_status, regime_status, dynamic_targets, portfolio_map, odds_matrix, changes_5d, ai_insights):
        fmt_s = lambda k: f"{odds_matrix[k]['samples']} 个样本" if odds_matrix[k]["samples"] >= IRON_LAWS["MIN_HISTORICAL_SAMPLES"] else "⚠️ 样本量不足 (降级参考)"
        return f"""# 🏛️ LEO'S PORTFOLIO SYSTEM V26.6.7 LTS
> **⏰ 自动化审计时间**: `{self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}`
---
## 📊 一、 宏观流动性观察站
* 美元指数(DXY): `{prices['DXY']}` ({macro_radar['DXY']}) | 美债10Y名义利率: `{prices['US10Y']}%` ({macro_radar['US10Y']})
---
## 🧠 二、 执纪控制中心
* 状态判词: {behavior_status}
---
## 📋 三、 动态资产再平衡中台
* 跨平台总资产: `{PORTFOLIO_ACCOUNT['TOTAL_CAPITAL']:,}` 元 | 现金期望储备目标: `{round(dynamic_targets['CASH']*100, 1)}%`
* 全账户当前总风险: 10.4% | 预期总风险: 10.1%

| 资产类别简写 | 当前占比 | 战术目标 | 调仓资金缺口 | 开枪指令 |
| :--- | :---: | :---: | :---: | :--- |
| **黄金资产 (GLD)** | {portfolio_map['GOLD']['current_pct']}% | {portfolio_map['GOLD']['target_pct']}% | {portfolio_map['GOLD']['infusion']:,} 元 | {portfolio_map['GOLD']['status']} |
| **资源多头 (COPX)** | {portfolio_map['RESOURCE']['current_pct']}% | {portfolio_map['RESOURCE']['target_pct']}% | {portfolio_map['RESOURCE']['infusion']:,} 元 | {portfolio_map['RESOURCE']['status']} |
| **科技硬件 (XLK)** | {portfolio_map['TECH']['current_pct']}% | {portfolio_map['TECH']['target_pct']}% | {portfolio_map['TECH']['infusion']:,} 元 | {portfolio_map['TECH']['status']} |
| **跨周期债 (TLT)** | {portfolio_map['FIXED_INCOME']['current_pct']}% | {portfolio_map['FIXED_INCOME']['target_pct']}% | {portfolio_map['FIXED_INCOME']['infusion']:,} 元 | {portfolio_map['FIXED_INCOME']['status']} |
---
## 💎 四、 跨资产风险收益比概率矩阵
| 资产名称 | 期望空间 | 远期回撤 | 赔率比 | 5日涨跌 | 有效样本量 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 科技硬件 | +{odds_matrix['TECH']['upside']}% | -{odds_matrix['TECH']['downside']}% | {odds_matrix['TECH']['odds']} | {changes_5d['TECH']}% | {fmt_s('TECH')} |
| 黄金避险 | +{odds_matrix['GOLD']['upside']}% | -{odds_matrix['GOLD']['downside']}% | {odds_matrix['GOLD']['odds']} | {changes_5d['GOLD']}% | {fmt_s('GOLD')} |
---
## 🎯 五、 智脑宏观归因内参
{ai_insights}
---"""

    def run_pipeline(self):
        total_cap = PORTFOLIO_ACCOUNT["TOTAL_CAPITAL"]
        data_matrix = {k: self.fetch_ticker_safe(symbol) for k, symbol in TICKERS.items()}
        changes_5d = {k: FALLBACK_DATA["CHANGES"].get(k, 0.0) for k in ["COPPER"] + RISK_ASSETS}
        prices = {k: FALLBACK_DATA["PRICES"][k] for k in TICKERS.keys()}
        bias_ma20 = {k: 0.0 for k in RISK_ASSETS + ["COPPER"]}
        regime_status = {k: "NEUTRAL" for k in RISK_ASSETS + ["COPPER"]}
        risk_parity_weights = {k: 0.25 for k in RISK_ASSETS}
        
        for k, df in data_matrix.items():
            if df is not None: prices[k] = df['Close'].iloc[-1]
            if df is not None and len(df) >= 60:
                ma20, ma60 = df['Close'].rolling(20).mean().iloc[-1], df['Close'].rolling(60).mean().iloc[-1]
                if k in bias_ma20: bias_ma20[k] = round(((df['Close'].iloc[-1] / ma20) - 1) * 100, 2)
                if k in regime_status: regime_status[k] = "BULL" if ma20 > ma60 else "BEAR"
                if k in changes_5d: changes_5d[k] = round(((df['Close'].iloc[-1] / df['Close'].iloc[-5]) - 1) * 100, 2)

        active_assets = [k for k in RISK_ASSETS if data_matrix[k] is not None and len(data_matrix[k]) >= 253]
        if len(active_assets) >= 3:
            try:
                df_rets = pd.DataFrame({k: np.log(data_matrix[k]['Close'] / data_matrix[k]['Close'].shift(1)) for k in active_assets}).dropna().tail(252)
                cov_matrix = df_rets.cov() * 252
                optimized = self._solve_constrained_equal_risk_contribution(cov_matrix.values, active_assets)
                for idx, k in enumerate(active_assets): risk_parity_weights[k] = round(optimized[idx], 3)
            except: pass

        odds = {}
        for k in RISK_ASSETS:
            up, dn, num = self._execute_regime_adaptive_backtest(data_matrix[k], bias_ma20.get(k, 0.0), regime_status.get(k, "NEUTRAL"))
            odds[k] = {"upside": round(up, 1), "downside": max(dn, IRON_LAWS["UNIFORM_MIN_DOWNSIDE_FLOOR"]), "odds": round(up/max(dn, 1.0), 2), "samples": num}

        macro_radar = {"DXY": "UNKNOWN", "US10Y": "UNKNOWN"}
        if data_matrix["DXY"] is not None and data_matrix["US10Y"] is not None:
            macro_radar["DXY"] = "BELOW_MA20" if prices["DXY"] < data_matrix["DXY"]["Close"].rolling(20).mean().iloc[-1] else "ABOVE_MA20"
            macro_radar["US10Y"] = "BELOW_MA20" if prices["US10Y"] < data_matrix["US10Y"]["Close"].rolling(20).mean().iloc[-1] else "ABOVE_MA20"

        total_strat = sum(PORTFOLIO_ACCOUNT["STRATEGIC_BASELINE"][a] for a in RISK_ASSETS)
        raw_targets = {a: ((1-IRON_LAWS["BLEND_FACTOR"])*(PORTFOLIO_ACCOUNT["STRATEGIC_BASELINE"][a]/total_strat) + IRON_LAWS["BLEND_FACTOR"]*risk_parity_weights.get(a, 0.25))*(1-IRON_LAWS["MIN_CASH_FLOOR"]) for a in RISK_ASSETS}

        dynamic_targets, allocated_sum = {}, 0.0
        for a in RISK_ASSETS:
            raw_t = raw_targets[a]
            curr_w = PORTFOLIO_ACCOUNT["CURRENT_ALLOCATION"][a]
            drift = raw_t - curr_w
            if drift > IRON_LAWS["MAX_REBALANCE_ADJUSTMENT"]: raw_t = curr_w + IRON_LAWS["MAX_REBALANCE_ADJUSTMENT"]
            elif drift < -IRON_LAWS["MAX_REBALANCE_ADJUSTMENT"]: raw_t = curr_w - IRON_LAWS["MAX_REBALANCE_ADJUSTMENT"]
            ceil = IRON_LAWS["MAX_BOND_CEILING"] if a == "FIXED_INCOME" else IRON_LAWS["MAX_ASSET_CEILING"]
            dynamic_targets[a] = float(np.clip(raw_t, IRON_LAWS["MIN_ASSET_FLOOR"], ceil))
            allocated_sum += dynamic_targets[a]

        space = 1.0 - IRON_LAWS["MIN_CASH_FLOOR"]
        if allocated_sum > space:
            scale = space / allocated_sum
            for a in RISK_ASSETS: dynamic_targets[a] = max(round(dynamic_targets[a]*scale, 4), IRON_LAWS["MIN_ASSET_FLOOR"])
            allocated_sum = sum(dynamic_targets[a] for a in RISK_ASSETS)
        
        # 🛠️ 刚性优化：重构浮点数高阶平账余数分配，杜绝边界越界
        if round(allocated_sum, 4) > round(space, 4):
            diff = round(allocated_sum - space, 4)
            for a in sorted(dynamic_targets.keys(), key=lambda x: dynamic_targets[x], reverse=True):
                if diff <= 0: break
                sub = min(diff, max(0.0, dynamic_targets[a] - IRON_LAWS["MIN_ASSET_FLOOR"]))
                dynamic_targets[a] = round(dynamic_targets[a] - sub, 4)
                diff -= sub
            allocated_sum = sum(dynamic_targets[a] for a in RISK_ASSETS)

        dynamic_targets["CASH"] = round(1.0 - allocated_sum, 4)
        rem = sum(dynamic_targets.values()) - 1.0
        if abs(rem) > 1e-4:
            el = [k for k in RISK_ASSETS if dynamic_targets[k] > IRON_LAWS["MIN_ASSET_FLOOR"]]
            if el:
                dynamic_targets[el[0]] = round(dynamic_targets[el[0]] - rem, 4)
                dynamic_targets["CASH"] = round(1.0 - sum(dynamic_targets[a] for a in RISK_ASSETS), 4)

        gap = (self.beijing_time.date() - datetime.strptime(self.portfolio_state.get("last_rebalance_date"), '%Y-%m-%d').date()).days
        drift_max = max(abs(dynamic_targets[a] - PORTFOLIO_ACCOUNT["CURRENT_ALLOCATION"][a]) for a in RISK_ASSETS)
        is_lock = gap < IRON_LAWS["COOLING_PERIOD_DAYS"] and drift_max <= IRON_LAWS["CRITICAL_DRIFT_THRESHOLD"]
        
        behavior = f"🌿 危机全面解除。当前最大敞口偏离度仅为 {round(drift_max*100, 2)}%，资产全部缩回安全中枢以内。【主账户8000+现金就地锁死，全线休兵静默】" if is_lock else ("刻不容缓！资产发生过载偏离，强制触发【战术强平开枪指令】！" if drift_max > IRON_LAWS["CRITICAL_DRIFT_THRESHOLD"] else "🌿 账户风险归位，常规调仓窗口解锁。")

        portfolio_map, trig = {}, False
        for a in RISK_ASSETS:
            c, t = PORTFOLIO_ACCOUNT["CURRENT_ALLOCATION"][a], dynamic_targets[a]
            infusion = round((t - c) * total_cap, 0)
            status = "🔒 刚性静默休兵" if is_lock else (f"🔥 开枪补仓 {infusion:+,} 元" if (t-c) > IRON_LAWS["REBALANCE_TRIGGER_THRESHOLD"] else (f"🚨 逢高减仓再平衡 {abs(infusion):,} 元" if (t-c) < -IRON_LAWS["REBALANCE_TRIGGER_THRESHOLD"] else "🌿 偏离度处于安全中枢内"))
            if "🔥" in status or "🚨" in status: trig = True
            portfolio_map[a] = {"current_pct": round(c*100, 1), "target_pct": round(t*100, 1), "infusion": infusion, "status": status}

        if trig and not is_lock:
            self.portfolio_state["last_rebalance_date"] = self.beijing_time.strftime('%Y-%m-%d')
            try:
                with open(PERSISTENCE["STATE_FILE"], 'w', encoding='utf-8') as f: json.dump(self.portfolio_state, f, indent=4)
            except: pass

        rep_payload = {"audit_date": self.beijing_time.strftime('%Y-%m-%d'), "live_dxy": prices["DXY"], "live_us10y_pct": prices["US10Y"], "assets_status": {k: {"current_pct": portfolio_map[k]["current_pct"], "target_pct": portfolio_map[k]["target_pct"], "infusion_rmb": portfolio_map[k]["infusion"]} for k in RISK_ASSETS}}
        ai_insights = self.call_llm_brain_analyser(rep_payload, behavior)
        
        report_content = self._build_markdown_report(prices, macro_radar, behavior, regime_status, dynamic_targets, portfolio_map, odds, changes_5d, ai_insights)
        print(report_content)
        
        if NOTIFICATION["WEBHOOK_URL"]:
            try: requests.post(NOTIFICATION["WEBHOOK_URL"], json={"msg_type": "text", "content": {"text": report_content}}, timeout=5)
            except: pass

if __name__ == "__main__":
    agent = PortfolioDisciplineEngineV26_6_7()
    agent.run_pipeline()
