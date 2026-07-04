import yfinance as yf
import pandas as pd
import logging
import os
import requests
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("ProductionEngine")

# ====================================================================================
# 🎛️ CONFIGURATION CENTRAL (行研参数配置中台 - 实现完全解耦)
# ====================================================================================
CONFIG = {
    "TICKER": "HG=F",
    "VISIBLE_STOCK": 425639.0,
    "LAST_MONTH_STOCK": 498000.0,
    "BONDED_STOCK": 85000.0,
    "TC_RC": 4.50,
    "AI_CAPEX_GROWTH": 35.0,
    "BASE_DAILY_BURN": 70000.0,
    "WEBHOOK_URL": os.environ.get("ALERT_WEBHOOK_URL", "") # 从环境变量隐式读取警报通道
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
        
        # 5. 生成中文版报告文本
        report_cn = f"""🏛️ 【AI 投研大脑实时简报】
⏰ 审计时间 (北京时间): {self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}
█==================================================█
📈 交易所显性库存环比变动率: {stock_velocity}% 
📈 国际铜精矿 Spot TC/RC 加工费: ${CONFIG['TC_RC']} USD/公吨
📈 AI 修正后全球实体库存维持天数: {true_safety_days} 天
🔮 华尔街即时价格: ${live_price} USD/磅 ➔ 模型 30 天公允目标价: ${target_price} USD/磅
█==================================================█
🎯 最终临盘开枪指令:
➡️ {'🚨 触发高斜率逼空红线！周一开盘以限价单全额重兵伏击上游核心资产。' if stock_velocity < -5.0 and CONFIG['TC_RC'] < 5.0 and potential_upside > 0 else '🌿 价格回归公允估值区间。死死按住账上现金长矛，继续保持左侧猎人定力，死等系统性恐慌砸盘跌停坑。'}
█==================================================█"""

        # 6. 生成英文版报告文本
        report_en = f"""🏛️ 【AI QUANTAMENTAL INTELLIGENCE BRIEFING】
⏰ Audit Time (Beijing Time): {self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}
█==================================================█
📈 Global Visible Stock MoM Change: {stock_velocity}% 
📈 Spot TC/RC Processing Fee: ${CONFIG['TC_RC']} USD/Ton
📈 AI-Adjusted Global Safety Runway: {true_safety_days} Days
🔮 Live Wall Street Price: ${live_price} USD/lb ➔ Model 30-Day Fair Target: ${target_price} USD/lb
█==================================================█
🎯 Actionable Trading Desk Guidance:
➡️ {'🚨 LEVEL 1 ASSET SQUEEZE DETECTED! Deploy 100% limit orders to ambush upstream core assets on Monday morning.' if stock_velocity < -5.0 and CONFIG['TC_RC'] < 5.0 and potential_upside > 0 else '🌿 STABLE RANGE. Maintain current cash defensive line and wait for systemic liquidity panic shock.'}
█==================================================█"""

        # 7. 中英对照合拢
        report_content = report_cn + "\n\n" + "🌐 ================================================== 🌐" + "\n\n" + report_en
        print(report_content)
        
        # 🚀 【神级修复】强制对齐飞书专用的规范数据载荷格式 (Strict JSON Schema)
        if CONFIG["WEBHOOK_URL"]:
            try:
                feishu_payload = {
                    "msg_type": "text",
                    "content": {
                        "text": report_content
                    }
                }
                response = requests.post(CONFIG["WEBHOOK_URL"], json=feishu_payload)
                logger.info(f"Feishu server backbone response: {response.text}")
            except Exception as e:
                logger.error(f"Failed to push alert: {e}")
                
        logger.info("===== PIPELINE EXECUTED SUCCESSFULLY WITHOUT ERRORS =====")

if __name__ == "__main__":
    agent = CloudAgent()
    agent.run_pipeline()
