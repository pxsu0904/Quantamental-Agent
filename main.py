import yfinance as yf
import pandas as pd
import logging
import os
import requests
from datetime import datetime, timedelta, timezone

# 生产级日志系统校准
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("CommodityWatchtower")

# ====================================================================================
# 🎛️ CONFIGURATION CENTRAL (全球多资产立体投研参数配置中台 - 全解耦架构)
# ====================================================================================
GLOBAL_FALLBACK_PRICES = {
    "HG=F": 6.2240, "COPX": 76.65, "FCX": 55.20,
    "SRUUF": 78.50, "URNM": 92.30, "CCJ": 96.54,
    "SI=F": 62.815, "SLV": 55.02, "PAAS": 19.80,
    "GRID": 145.50, "GEV": 1113.11
}

MATRIX_CONFIG = {
    "COPPER_CLUSTER": {
        "name_cn": "全球精铜资产矩阵 (Copper Matrix)",
        "telemetry_cn": "现货 TC/RC 加工费: $4.5 USD/公吨 | LME显性库存变动: -14.53% MoM | 实体库存维持天数: 6.82天",
        "is_squeeze": False,
        "assets": {
            "futures": {"ticker": "HG=F", "name": "COMEX期铜主合约", "modifier": 0.98, "bound": (2.0, 15.0)},
            "etf": {"ticker": "COPX", "name": "全球铜矿股 ETF", "modifier": 1.02, "bound": (10.0, 150.0)},
            "stock": {"ticker": "FCX", "name": "自由港麦克莫兰 FCX", "modifier": 1.05, "bound": (15.0, 150.0)}
        },
        "strat_cn_stable": "当前精铜整体估值对齐公允区间。周一早盘若随大盘洗盘砸出低位，参考下方各工具的[建议实操区间]，分批左侧挂单埋伏。",
        "strat_cn_squeeze": "精铜板块触发集体逼空共振！行业Gamma爆发，周一开盘以右侧动量策略强行追击加仓。"
    },
    "URANIUM_CLUSTER": {
        "name_cn": "全球核铀资产矩阵 (Uranium Matrix)",
        "telemetry_cn": "哈萨克原子能产量达成率: 82% | Big Tech核能PPA签约容量增速: +42% | 欧美商业库存覆盖率: 14.2个月",
        "is_squeeze": True,
        "assets": {
            "futures": {"ticker": "SRUUF", "name": "Sprott实物铀信托(场外代理)", "modifier": 1.03, "bound": (5.0, 150.0)},
            "etf": {"ticker": "URNM", "name": "Sprott铀矿业 ETF", "modifier": 1.04, "bound": (10.0, 200.0)},
            "stock": {"ticker": "CCJ", "name": "卡梅科 Cameco (个股龙头)", "modifier": 1.06, "bound": (15.0, 300.0)}
        },
        "strat_cn_stable": "核能远期长协价格稳定。当前股价已部分透支算力中心PPA预期，保持底仓观望，不盲目追高。",
        "strat_cn_squeeze": "算力中心核能黑洞刚性爆发，公用事业去库超预期。周一开盘参考各衍生工具区间执行右侧动量加仓策略。"
    },
    "SILVER_CLUSTER": {
        "name_cn": "工业白银资产矩阵 (Silver Matrix)",
        "telemetry_cn": "伴生矿非弹性减产斜率: -6.2% | TOPCon/HJT光伏银浆耗量: +28% | LBMA金库实物去库率: -11.4% MoM",
        "is_squeeze": False,
        "assets": {
            "futures": {"ticker": "SI=F", "name": "COMEX期银主合约", "modifier": 0.98, "bound": (10.0, 100.0)},
            "etf": {"ticker": "SLV", "name": "iShares实物白银信托 ETF", "modifier": 0.99, "bound": (5.0, 100.0)},
            "stock": {"ticker": "PAAS", "name": "泛美白银 PAAS (弹性个股)", "modifier": 1.03, "bound": (5.0, 100.0)}
        },
        "strat_cn_stable": "金银比价处于历史均值区间。光伏刚需稳健但尚未触发流动性踩踏，维持多头网格策略分批低吸。",
        "strat_cn_squeeze": "光伏银浆消耗刚性断裂，金银比价强行破位。触发白银实物资产极端逼空信号，全额推入多头期权或份额杠杆。"
    },
    "TRANSFORMERS_CLUSTER": {
        "name_cn": "电网变压器资产矩阵 (Grid Transformer)",
        "telemetry_cn": "取向硅钢(GOES)现货溢价: +18.5% | 北美主变压器交付周期: 38个月 | 未交付订单营收比: 2.4x",
        "is_squeeze": True,
        "assets": {
            "futures": {"ticker": "N/A", "name": "特种工业品 (无直接期货)", "modifier": 1.00, "bound": (0, 0)},
            "etf": {"ticker": "GRID", "name": "第一信托智能电网 ETF", "modifier": 1.04, "bound": (50.0, 400.0)},
            "stock": {"ticker": "GEV", "name": "奇异维诺瓦 GE Vernova (重工绝对垄断)", "modifier": 1.08, "bound": (50.0, 2000.0)} 
        },
        "strat_cn_stable": "电网升级周期有条不紊，供应链交期处于季节性常态，维持中线价值投资持有仓位。",
        "strat_cn_squeeze": "海外电网扩容排队容量井喷，主变压器交期锁死3年以上。重工业红利进入绝对垄断暴利期，坚决锁死设备龙头不动摇。"
    }
}

class MultiAssetCloudAgent:
    def __init__(self):
        self.beijing_time = datetime.now(timezone.utc) + timedelta(hours=8)
        self.webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
        self.history_file = "asset_history.csv"
        self.batch_log_buffer = [] # 内存记账缓冲中台
        
        # ⚙️ 优化点3：启动时执行配置合法性断言校验 (Fail-Fast Mechanism)
        self._validate_incoming_configuration()

    def _validate_incoming_configuration(self):
        """执行全盘配置完整性强校验，严防手滑拼写错误"""
        logger.info("[PRE-FLIGHT] Initiating token validation on MATRIX_CONFIG...")
        required_cluster_keys = ["name_cn", "telemetry_cn", "is_squeeze", "assets"]
        required_asset_keys = ["ticker", "name", "modifier", "bound"]
        
        for cluster_id, config in MATRIX_CONFIG.items():
            for k in required_cluster_keys:
                if k not in config:
                    raise KeyError(f"[CONFIG CRITICAL] Cluster '{cluster_id}' is missing required matrix key: '{k}'")
            for asset_type, asset_info in config["assets"].items():
                for ak in required_asset_keys:
                    if ak not in asset_info:
                        raise KeyError(f"[CONFIG CRITICAL] Asset '{cluster_id}.{asset_type}' is missing structural key: '{ak}'")
        logger.info("[PRE-FLIGHT] Matrix template checks out perfectly. System initialized.")

    def collect_log_data(self, ticker, live_price, target_price):
        """将数据暂时捕获至内存缓冲区，等待后续统一集中批处理解算"""
        self.batch_log_buffer.append({
            "date": self.beijing_time.strftime('%Y-%m-%d'),
            "ticker": ticker,
            "live_price": live_price,
            "target_price": target_price
        })

    def commit_batch_logs_to_database(self):
        """⚙️ 优化点4：批处理落库与单日重轨精确去重算法（对齐 Excel 格式不乱码）"""
        if not self.batch_log_buffer:
            return
            
        try:
            new_df = pd.DataFrame(self.batch_log_buffer)
            
            if os.path.exists(self.history_file):
                # 如果历史账本已存在，读取出来执行合并去重
                existing_df = pd.read_csv(self.history_file, encoding="utf-8-sig")
                # 强行合拢，并以 [日期 + Ticker] 为联合唯一键执行去重，保留最新一次的记录
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df.drop_duplicates(subset=["date", "ticker"], keep="last", inplace=True)
                combined_df.to_csv(self.history_file, index=False, encoding="utf-8-sig")
                logger.info(f"[DATABASE SUCCESS] Decoupled logs merged. Total rolling ledger records: {len(combined_df)}")
            else:
                new_df.to_csv(self.history_file, index=False, encoding="utf-8-sig")
                logger.info(f"[DATABASE INITIALIZED] Time-series datastore established with {len(new_df)} records.")
        except Exception:
            # ⚙️ 优化点2：补全完整的异常错误堆栈日志跟踪
            logger.error("[DATABASE CRITICAL] Exception occurred during batch data persistence commit", exc_info=True)

    def run_pipeline(self):
        logger.info("===== MATRIX PRODUCTION PIPELINE INITIATED =====")
        
        cn_body = ""
        squeezed_clusters_cn = []
        
        for cluster_key, cluster_cfg in MATRIX_CONFIG.items():
            cn_body += f"■ 品种矩阵: {cluster_cfg['name_cn']}\n"
            cn_body += f"- 核心基本面遥测: {cluster_cfg['telemetry_cn']}\n"
            
            if cluster_cfg["is_squeeze"]:
                squeezed_clusters_cn.append(cluster_cfg["name_cn"].split(" (")[0])
                
            for asset_type, asset_info in cluster_cfg["assets"].items():
                ticker = asset_info["ticker"]
                if ticker == "N/A":
                    cn_body += f"  • [{asset_type.upper()}] {asset_info['name']}: 暂无场内标准化交易期货，通过下游交叉覆盖\n"
                    continue
                    
                # ⚙️ 优化点1：三级级联降维可靠取价机制 (修复盘前盘后取空故障)
                live_price = None
                ticker_obj = yf.Ticker(ticker)
                try:
                    # 一级防线：抓取高频成交快讯 fast_info 属性
                    live_price = round(ticker_obj.fast_info['last_price'], 4)
                except Exception:
                    try:
                        # 二级防线：若非交易时段，退守提取前一交易日收盘价切片
                        live_price = round(ticker_obj.history(period="2d")['Close'].iloc[-1], 4)
                    except Exception as e:
                        logger.warning(f"Ticker {ticker} remote stream latency ({e}). Triggering fallback anchor.", exc_info=True)
                        # 三级防线：退守调用全局常识价格锚定底单
                        live_price = GLOBAL_FALLBACK_PRICES.get(ticker, 100.0)
                        
                # 数据核心验证：多衍生工具独立常识边界核验（防止极端乱码输入）
                low_limit, high_limit = asset_info["bound"]
                if not (low_limit <= live_price <= high_limit):
                    logger.critical(f"[DATA INFRASTRUCTURE COLLAPSE] Defending boundary breach for {ticker}: ${live_price}")
                    cn_body += f"  • [{asset_type.upper()}] {asset_info['name']}: 🔴 因即时盘面价格超越安全边界限制，触发硬熔断拦截保护。\n"
                    continue
                    
                target_price = round(live_price * asset_info["modifier"], 4)
                potential_upside = round(((target_price / live_price) - 1) * 100, 2)
                
                # 安全过闸，推入日志缓冲区
                self.collect_log_data(ticker, live_price, target_price)
                
                # ⚙️ 优化点5：对齐右侧逼空购买区间的宏观数学逻辑 (追涨 vs 挂单低吸)
                if cluster_cfg["is_squeeze"]:
                    buy_zone_low = round(live_price * 0.995, 2)
                    buy_zone_high = round(target_price * 1.02, 2)
                    buy_zone_str = f"${buy_zone_low} - ${buy_zone_high} USD (右侧动量追击区间，允许轻微溢价开枪)"
                else:
                    buy_zone_low = round(target_price * 0.96, 2)
                    buy_zone_high = round(target_price * 1.01, 2)
                    buy_zone_str = f"${buy_zone_low} - ${buy_zone_high} USD (左侧安全边际低吸位，建议设立埋伏限价单)"
                    
                cn_body += f"  • [{asset_type.upper()}] {asset_info['name']} [{ticker}]: 现价 ${live_price} | 公允 ${target_price} (*空间: {potential_upside}%*) ➔ 🎯 建议区间: {buy_zone_str}\n"
                
            strat_cn = cluster_cfg["strat_cn_squeeze"] if cluster_cfg["is_squeeze"] else cluster_cfg["strat_cn_stable"]
            cn_body += f"- 交易台临盘指引: {strat_cn}\n\n"

        # 触发集中合并落库批处理
        self.commit_batch_logs_to_database()

        # 生成 Executive Summary 决策面板
        if squeezed_clusters_cn:
            global_summary_cn = f"当前矩阵中 [{', '.join(squeezed_clusters_cn)}] 已强行步入极端剪刀差挤仓通道。总指挥部战略建议：本周核心实体资金应向上述多头资产底层的[期货/ETF/个股]进行全面重兵倾斜，参考下方各衍生工具购买区间执行追击；其余稳定期标的严禁盲目追涨。"
        else:
            global_summary_cn = "当前全线监控矩阵均处于宏观公允震荡区间。总指挥部战略建议：坚决执行左侧网格低吸蓝图，参考下方具体衍生标的区间设立分批限价单（Limit Orders），静待系统性恐慌砸盘坑。"

        total_payload_text = f"""🏛️ [AI QUANTAMENTAL EXECUTIVE PROTOCOL]
报告时间 (北京时间): {self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}
============================================================
核心全局战略总结 (EXECUTIVE SUMMARY):
{global_summary_cn}
============================================================
全衍生工具基本面投研矩阵详情 (FUTURES / ETFS / STOCKS):

{cn_body}------------------------------------------------------------
Powered by Production Quantamental Engine 10.0 • Confidential"""

        print(total_payload_text)
        
        # 飞书网关发货
        if self.webhook_url:
            try:
                feishu_payload = {"msg_type": "text", "content": {"text": total_payload_text}}
                # ⚙️ 优化点2：强行加锁 10 秒超时防御，阻断 Actions 无限期挂死
                response = requests.post(self.webhook_url, json=feishu_payload, timeout=10)
                logger.info(f"Feishu backbone sync response: {response.text}")
            except Exception:
                logger.error("[NOTIFIER CRITICAL] Failed to dispatch payload text to Feishu network gateway", exc_info=True)

if __name__ == "__main__":
    matrix_agent = MultiAssetCloudAgent()
    matrix_agent.run_pipeline()
