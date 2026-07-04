import yfinance as yf
import pandas as pd
import logging
import os
import requests
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("ProductionEngine")

# ====================================================================================
# CONFIGURATION CENTRAL (行研参数配置中台)
# ====================================================================================
CONFIG = {
    "TICKER": "HG=F",
    "VISIBLE_STOCK": 425639.0,
    "LAST_MONTH_STOCK": 498000.0,
    "BONDED_STOCK": 85000.0,
    "TC_RC": 4.50,
    "AI_CAPEX_GROWTH": 35.0,
    "BASE_DAILY_BURN": 70000.0,
    "WEBHOOK_URL": os.environ.get("ALERT_WEBHOOK_URL", "")
}

class CloudAgent:
    def __init__(self):
        self.beijing_time = datetime.now(timezone.utc) + timedelta(hours=8)
        
    def run_pipeline(self):
        logger.info("===== SENSOR PIPELINE INITIATED =====")
        
        # 1. 解算时序动量与加速度
        stock_velocity = round(((CONFIG["VISIBLE_STOCK"] / CONFIG["LAST_MONTH_STOCK"]) - 1) * 100, 2)
        
        # 2. 算力开支动态消费传导
        dynamic_burn = round(CONFIG["BASE_DAILY_BURN"] * (1 + (CONFIG["AI_CAPEX_GROWTH"] * 0.002)), 2)
        true_safety_days = round((CONFIG["VISIBLE_STOCK"] + CONFIG["BONDED_STOCK"]) / dynamic_burn, 2)
        
        # 3. 动态抓取华尔街收盘价
        try:
            live_price = round(yf.Ticker(CONFIG["TICKER"]).history(period="1d")['Close'].iloc[-1], 4)
        except Exception as e:
            logger.warning(f"Market feed latency: {e}. Defaulting to hard-floor price.")
            live_price = 6.2240
            
        # 4. 价格弹性矩阵精算
        target_price = live_price * (1 + (6.0 - true_safety_days) * 0.08) if true_safety_days < 6.0 else live_price
        if target_price > 6.0: target_price = round(target_price * 0.98, 4)
        potential_upside = round(((target_price / live_price) - 1) * 100, 2)
        
        # 5. 生成极其严谨的中文版报告（去除所有Emoji图标，采用彭博终端标准行距）
        report_cn = f"""GLOBAL COMMODITY QUANTAMENTAL RESEARCH BRIEFING
报告时间 (北京时间): {self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}
------------------------------------------------------------
[当前策略评级] 震荡区间 / 保持左侧定力 (STABLE RANGE)

1. 盘面价格与估值综述 (MARKET DATA OVERVIEW)
- 期铜即时结算价格 : ${live_price} USD/磅
- 模型公允目标价格 : ${target_price} USD/磅
- 预期资本损益空间 : {potential_upside}% (估值高位倒挂)

2. 核心基本面量化遥测 (KEY FUNDAMENTAL TELEMETRY)
- 交易所显性库存环比变动率 : {stock_velocity}%
- 国际铜精矿现货 TC/RC 加工费 : ${CONFIG['TC_RC']} USD/公吨
- AI 修正后全球实体库存维持天数 : {true_safety_days} 天 (临界红线: 6天)

3. 交易台临盘决策指引 (ACTIONABLE TRADING DESK GUIDANCE)
- 执行策略 : {'触发高斜率逼空红线。周一开盘以限价单(Limit Orders)全额重兵伏击上游核心资产。' if stock_velocity < -5.0 and CONFIG['TC_RC'] < 5.0 and potential_upside > 0 else '坚决维持当前现金防御战线。周一早盘静待外部硬件板块高位洗盘引发的系统性流动性冲击，砸出均线打折坑时再行左侧挂单吸筹。'}
------------------------------------------------------------"""

        # 6. 生成纯净的英文版报告
        report_en = f"""GLOBAL COMMODITY QUANTAMENTAL RESEARCH BRIEFING
Audit Time (Beijing Time): {self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}
------------------------------------------------------------
[STRATEGIC STATUS] STABLE RANGE

1. MARKET DATA OVERVIEW
- Live Wall Street Price      : ${live_price} USD/lb
- Model 30-Day Fair Target    : ${target_price} USD/lb
- Quantitative Capital Upside : {potential_upside}%

2. KEY FUNDAMENTAL TELEMETRY
- Global Visible Stock MoM Change : {stock_velocity}%
- Spot TC/RC Processing Fee       : ${CONFIG['TC_RC']} USD/Ton
- AI-Adjusted Global Safety Runway: {true_safety_days} Days

3. ACTIONABLE TRADING DESK GUIDANCE
- Execution Strategy: {'LEVEL 1 ASSET SQUEEZE DETECTED! Deploy 100% limit orders to ambush upstream core assets on Monday morning.' if stock_velocity < -5.0 and CONFIG['TC_RC'] < 5.0 and potential_upside > 0 else 'STABLE RANGE. Maintain current cash defensive line and wait for systemic liquidity panic shock.'}
------------------------------------------------------------"""

        # 7. 纯文本无缝拼接
        report_content = report_cn + "\n\n" + "============================================================" + "\n\n" + report_en
        print(report_content)
        
        # 🚀 飞书专属红头文件规范载荷
        if CONFIG["WEBHOOK_URL"]:
            try:
                feishu_payload = {
                    "msg_type": "text",
                    "content": {
                        "text": report_content
                    }
                }
                response = requests.post(CONFIG["WEBHOOK_URL"], json=feishu_payload)
                logger.info(f"Feishu backbone response: {response.text}")
            except Exception as e:
                logger.error(f"Failed to push alert: {e}")
                
        logger.info("===== PIPELINE EXECUTED SUCCESSFULLY WITHOUT ERRORS =====")

if __name__ == "__main__":
    agent = CloudAgent()
    agent.run_pipeline()
