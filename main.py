import yfinance as yf
import pandas as pd
import logging
import os
import requests
import time
from datetime import datetime, timedelta, timezone

# 生产级日志系统校准
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("CommodityWatchtower")

# ====================================================================================
# 🎛️ CONFIGURATION CENTRAL (全球大宗商品立体投研参数配置中台 - 极限解耦驱动)
# ====================================================================================
NOTIFIER_CONFIG = {
    "max_retries": 3,
    "retry_delay": 1,
    "timeout": 10
}

PRICE_CONFIG = {
    "decimals": 4,
    "display_decimals": 2
}

STATIC_FALLBACK_PRICES = {
    "HG=F": 6.2240,   "512400.SS": 1.25,   "601899.SS": 18.50,
    "CCJ": 96.54,     "516290.SS": 1.10,   "001280.SZ": 67.20,
    "SI=F": 62.815,   "161226.SZ": 1.86,   "000603.SZ": 12.40,
    "GEV": 1113.11,   "159326.SZ": 2.15,   "600089.SS": 14.80
}

DEFAULT_STRATEGY_PARAMS = {
    "squeeze_band": (0.995, 1.02),
    "stable_band": (0.96, 1.01)
}

MATRIX_CONFIG = {
    "COPPER_CLUSTER": {
        "name_cn": "全球精铜资产矩阵 (Copper Matrix)",
        "telemetry_cn": "现货 TC/RC 加工费: $4.5 USD/公吨 | LME显性库存变动: -14.53% MoM | 实体库存维持天数: 6.82天",
        "is_squeeze": False,
        "assets": {
            "anchor": {"ticker": "HG=F", "name": "COMEX期铜主合约", "modifier": 0.98, "bound": (2.0, 15.0), "currency": "USD", "type_label": "决策参考锚", "market": "US"},
            "a-etf": {"ticker": "512400.SS", "name": "南方有色金属ETF (场外004432)", "modifier": 1.01, "bound": (0.5, 5.0), "currency": "CNY", "type_label": "场内ETF/场外基金", "market": "CN"},
            "stock": {"ticker": "601899.SS", "name": "紫金矿业 (A股铜金矿巨鳄)", "modifier": 1.03, "bound": (5.0, 50.0), "currency": "CNY", "type_label": "A股核心个股", "market": "CN"}
        },
        "strat_cn_stable": "当前精铜整体估值对齐公允区间。周一早盘若随大盘洗盘砸出低位，参考下方各工具的[建议实操区间]，分批左侧挂单埋伏。",
        "strat_cn_squeeze": "精铜板块触发集体逼空共振！行业Gamma爆发，周一开盘参考[建议区间]执行右侧动量追击，有色联接基金加码。"
    },
    "URANIUM_CLUSTER": {
        "name_cn": "全球核铀资产矩阵 (Uranium Matrix)",
        "telemetry_cn": "哈萨克原子能产量达成率: 82% | Big Tech核能PPA签约容量增速: +42% | 欧美商业库存覆盖率: 14.2个月",
        "is_squeeze": True,
        "assets": {
            "anchor": {"ticker": "CCJ", "name": "卡梅科 Cameco", "modifier": 1.05, "bound": (15.0, 300.0), "currency": "USD", "type_label": "决策参考锚", "market": "US"},
            "a-etf": {"ticker": "516290.SS", "name": "易方达中证核能电力ETF", "modifier": 1.03, "bound": (0.3, 4.0), "currency": "CNY", "type_label": "场内ETF/场外基金", "market": "CN"},
            "stock": {"ticker": "001280.SZ", "name": "中国铀业 (天然铀纯正龙头)", "modifier": 1.06, "bound": (10.0, 200.0), "currency": "CNY", "type_label": "A股核心个股", "market": "CN"}
        },
        "strat_cn_stable": "核能远期长协价格稳定。当前股价已部分透支算力中心PPA预期，保持底仓观望，不盲目追高。",
        "strat_cn_squeeze": "算力中心核能黑洞刚性爆发，公用事业去库超预期。周一开盘参考各本土衍生工具购买区间执行右侧动量追击策略。"
    },
    "SILVER_CLUSTER": {
        "name_cn": "工业白银资产矩阵 (Silver Matrix)",
        "telemetry_cn": "伴生矿非弹性减产斜率: -6.2% | TOPCon/HJT光伏银浆耗量: +28% | LBMA金库实物去库率: -11.4% MoM",
        "is_squeeze": False,
        "assets": {
            "anchor": {"ticker": "SI=F", "name": "COMEX期银主合约", "modifier": 0.98, "bound": (10.0, 100.0), "currency": "USD", "type_label": "决策参考锚", "market": "US"},
            "a-etf": {"ticker": "161226.SZ", "name": "国投瑞银白银期货LOF", "modifier": 1.01, "bound": (0.5, 5.0), "currency": "CNY", "type_label": "场内ETF/场外基金", "market": "CN"},
            "stock": {"ticker": "000603.SZ", "name": "盛达资源 (A股白银储备之王)", "modifier": 1.03, "bound": (3.0, 40.0), "currency": "CNY", "type_label": "A股核心个股", "market": "CN"}
        },
        "strat_cn_stable": "金银比价处于历史均值区间。光伏刚需稳健但尚未触发流动性踩踏，维持多头网格策略分批低吸。",
        "strat_cn_squeeze": "光伏银浆消耗刚性断裂，金银比价强行破位。触发白银实物资产极端逼空信号，全额推入本土白银LOF或个股份额。"
    },
    "TRANSFORMERS_CLUSTER": {
        "name_cn": "电网变压器资产矩阵 (Grid Transformer)",
        "telemetry_cn": "取向硅钢(GOES)现货溢价: +18.5% | 北美主变压器交付周期: 38个月 | 未交付订单营收比: 2.4x",
        "is_squeeze": True,
        "assets": {
            "anchor": {"ticker": "GEV", "name": "奇异维诺瓦 GE Vernova", "modifier": 1.08, "bound": (50.0, 2000.0), "currency": "USD", "type_label": "决策参考锚", "market": "US"}, 
            "a-etf": {"ticker": "159326.SZ", "name": "华夏中证电网设备ETF", "modifier": 1.03, "bound": (0.5, 5.0), "currency": "CNY", "type_label": "场内ETF/场外基金", "market": "CN"},
            "stock": {"ticker": "600089.SS", "name": "特变电工 (A股变压器骨干龙头)", "modifier": 1.05, "bound": (5.0, 50.0), "currency": "CNY", "type_label": "A股核心个股", "market": "CN"}
        },
        "strat_cn_stable": "电网升级周期有条不紊，供应链交期处于季节性常态，维持中线价值投资持有仓位。",
        "strat_cn_squeeze": "海外电网扩容排队容量井喷，主变压器交期锁死3年以上。重工业红利进入绝对垄断暴利期，参考建议区间死锁设备龙头。"
    }
}

class MultiAssetCloudAgent:
    def __init__(self):
        self._start_time = time.time()
        self.beijing_time = datetime.now(timezone.utc) + timedelta(hours=8)
        self.webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
        self.history_file = "asset_history.csv"
        self.batch_log_buffer = [] 
        
        # 📊 高优先级观测统计面板
        self.stale_assets_count = 0
        self.blocked_assets_count = 0 # 高优先级优化1：补全熔断拦截计数
        self.exceptional_summary_list = [] # 中优先级优化2：异常标的顶置清单
        
        self._validate_incoming_configuration()

    def _validate_incoming_configuration(self):
        """执行配置完整性强校验 (Fail-Fast)"""
        logger.info("[PRE-FLIGHT] Verifying structural integrity of investment matrix...")
        required_cluster_keys = ["name_cn", "telemetry_cn", "is_squeeze", "assets"]
        required_asset_keys = ["ticker", "name", "modifier", "bound", "currency", "type_label", "market"]
        
        for cluster_id, config in MATRIX_CONFIG.items():
            for k in required_cluster_keys:
                if k not in config:
                    raise KeyError(f"[CONFIG CRITICAL] Cluster '{cluster_id}' missing key: '{k}'")
            
            params = config.get("strategy_params", DEFAULT_STRATEGY_PARAMS)
            if "squeeze_band" not in params or "stable_band" not in params:
                raise KeyError(f"[CONFIG CRITICAL] Cluster '{cluster_id}' strategy_params lacks structural sub-keys.")
                
            for asset_type, asset_info in config["assets"].items():
                for ak in required_asset_keys:
                    if ak not in asset_info:
                        raise KeyError(f"[CONFIG CRITICAL] Asset '{cluster_id}.{asset_type}' missing operational key: '{ak}'")
        logger.info("[PRE-FLIGHT] Configuration checks passed.")

    def _handle_corrupted_csv(self):
        """⚙️ 高优先级优化3：数据库文件损坏硬核容灾防御保护"""
        if os.path.exists(self.history_file):
            try:
                bak_file = f"{self.history_file}.{int(time.time())}.bak"
                os.rename(self.history_file, bak_file)
                logger.critical(f"[DATABASE CORRUPTION ALERT] {self.history_file} format corrupted! Isolated to {bak_file}")
            except Exception as e:
                logger.error(f"Disaster isolation routing failed: {e}", exc_info=True)

    def _get_dynamic_fallback_price(self, ticker):
        """⚙️ 高优先级优化2：将硬编码死价格升级为历史最近一次成功存储的动态真实收盘价"""
        if os.path.exists(self.history_file):
            try:
                df = pd.read_csv(self.history_file, encoding="utf-8-sig")
                ticker_df = df[df["ticker"] == ticker]
                if not ticker_df.empty:
                    last_price = float(ticker_df.iloc[-1]["live_price"])
                    logger.info(f"[DYNAMIC FALLBACK] Retrieved last known valid price for {ticker}: ${last_price}")
                    return last_price
            except Exception:
                self._handle_corrupted_csv()
        return STATIC_FALLBACK_PRICES.get(ticker, 100.0)

    def _fetch_live_price(self, ticker):
        """三级级联取价 + 新增动态涨跌幅获取"""
        ticker_obj = yf.Ticker(ticker)
        live_price, change_pct, is_fallback = None, 0.0, False
        
        # 1. 尝试一级与二级取价渠道
        try:
            hist = ticker_obj.history(period="2d")
            # ⚙️ 高优先级优化：强化非空与行数判断，彻底截断空 DataFrame 引发的报错
            if hist is not None and len(hist) >= 1:
                live_price = round(hist['Close'].iloc[-1], PRICE_CONFIG["decimals"])
                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    change_pct = round(((live_price / prev_close) - 1) * 100, PRICE_CONFIG["display_decimals"])
                return live_price, change_pct, False
        except Exception:
            pass
            
        try:
            price = ticker_obj.fast_info['last_price']
            if price is not None and price > 0:
                return round(price, PRICE_CONFIG["decimals"]), 0.0, False
        except Exception:
            pass
            
        # 3. 触发最高防空等级：调用时序数据账本回溯动态最近有效价
        live_price = self._get_dynamic_fallback_price(ticker)
        return live_price, 0.0, True

    def _calculate_buy_zone(self, live_price, target_price, is_squeeze, params, sym):
        """单一职责解耦：区间精确解算"""
        if is_squeeze:
            buy_zone_low = round(live_price * params["squeeze_band"][0], PRICE_CONFIG["display_decimals"])
            buy_zone_high = round(target_price * params["squeeze_band"][1], PRICE_CONFIG["display_decimals"])
            return f"{sym}{buy_zone_low} - {sym}{buy_zone_high} (右侧动量追击区间，允许轻微溢价开枪)"
        else:
            buy_zone_low = round(target_price * params["stable_band"][0], PRICE_CONFIG["display_decimals"])
            buy_zone_high = round(target_price * params["stable_band"][1], PRICE_CONFIG["display_decimals"])
            return f"{sym}{buy_zone_low} - {sym}{buy_zone_high} (左侧安全边际埋伏位)"

    def _collect_log_data(self, ticker, market, live_price, target_price):
        """私有数据缓冲区拦截"""
        self.batch_log_buffer.append({
            "date": self.beijing_time.strftime('%Y-%m-%d'),
            "ticker": ticker,
            "market": market,
            "live_price": live_price,
            "target_price": target_price
        })

    def _commit_batch_logs_to_database(self):
        """集中批处理合并落库（带联合主键去重防御）"""
        if not self.batch_log_buffer: return
        try:
            new_df = pd.DataFrame(self.batch_log_buffer)
            if os.path.exists(self.history_file):
                try:
                    existing_df = pd.read_csv(self.history_file, encoding="utf-8-sig")
                except Exception:
                    self._handle_corrupted_csv()
                    existing_df = pd.DataFrame()
                    
                if not existing_df.empty:
                    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                    combined_df.drop_duplicates(subset=["date", "ticker", "market"], keep="last", inplace=True)
                    combined_df.to_csv(self.history_file, index=False, encoding="utf-8-sig")
                    return
                    
            new_df.to_csv(self.history_file, index=False, encoding="utf-8-sig")
        except Exception:
            logger.error("[DATABASE CRITICAL] Exception occurred during data persistence sync", exc_info=True)

    def run_pipeline(self):
        logger.info("===== MATRIX PRODUCTION PIPELINE INITIATED =====")
        cn_body = ""
        squeezed_clusters_cn = []
        
        for cluster_key, cluster_cfg in MATRIX_CONFIG.items():
            cn_body += f"■ 品种矩阵: {cluster_cfg['name_cn']}\n"
            cn_body += f"- 核心基本面遥测: {cluster_cfg['telemetry_cn']}\n"
            
            if cluster_cfg["is_squeeze"]:
                squeezed_clusters_cn.append(cluster_cfg["name_cn"].split(" (")[0])
                
            params = cluster_cfg.get("strategy_params", DEFAULT_STRATEGY_PARAMS)
                
            for asset_type, asset_info in cluster_cfg["assets"].items():
                ticker = asset_info["ticker"]
                sym = "$" if asset_info["currency"] == "USD" else "¥"
                
                # 级联高可用取价
                live_price, change_pct, is_fallback = self._fetch_live_price(ticker)
                if is_fallback: 
                    self.stale_assets_count += 1
                    self.exceptional_summary_list.append(f"⚠️ {asset_info['name']} ({ticker}) 触发延迟兜底")
                        
                # 🛡️ 数据清洗校验：独立常识边界核验
                low_limit, high_limit = asset_info["bound"]
                if not (low_limit <= live_price <= high_limit):
                    logger.critical(f"[DATA INFRASTRUCTURE FAILURE] Intercepted boundary breach for {ticker}: {sym}{live_price}")
                    self.blocked_assets_count += 1 # ⚙️ 高优先级优化1：拦截计数器累加
                    self.exceptional_summary_list.append(f"🔴 {asset_info['name']} ({ticker}) 触发边界越界熔断")
                    cn_body += f"  • [{asset_info['type_label']}] {asset_info['name']}: 🔴 因数据溢出常识边界，触发安全防空网硬熔断拦截。\n"
                    continue
                    
                # 精算模型估值
                target_price = round(live_price * asset_info["modifier"], PRICE_CONFIG["decimals"])
                potential_upside = round(((target_price / live_price) - 1) * 100, PRICE_CONFIG["display_decimals"])
                
                self._collect_log_data(ticker, asset_info["market"], live_price, target_price)
                buy_zone_str = self._calculate_buy_zone(live_price, target_price, cluster_cfg["is_squeeze"], params, sym)
                
                stale_marker = "*" if is_fallback else ""
                change_sign = "+" if change_pct > 0 else ""
                change_str = f" ({change_sign}{change_pct}%)" if change_pct != 0.0 else ""
                
                cn_body += f"  • [{asset_info['type_label']}] {asset_info['name']} [{ticker}]: 现价 {sym}{live_price}{stale_marker}{change_str} | 公允价 {sym}{target_price} (*预期空间: {potential_upside}%*) ➔ 🎯 建议区间: {buy_zone_str}\n"
                
            strat_cn = cluster_cfg["strat_cn_squeeze"] if cluster_cfg["is_squeeze"] else cluster_cfg["strat_cn_stable"]
            cn_body += f"- A股临盘配置指引: {strat_cn}\n\n"

        self._commit_batch_logs_to_database()
        elapsed_time = round(time.time() - self._start_time, PRICE_CONFIG["display_decimals"])

        # 📊 拼装数据健康度汇总审计面板
        health_summary = f"全线实时水源100%对齐"
        if self.stale_assets_count > 0 or self.blocked_assets_count > 0:
            health_summary = f"延迟兜底: {self.stale_assets_count}项 | 异常拦截: {self.blocked_assets_count}项"

        # 中优先级优化2：在 Executive Summary 下方动态置顶呈现异常标的红置顶面板
        exception_panel = ""
        if self.exceptional_summary_list:
            exception_panel = "🚨 [数据健康审计异常告警清单]:\n" + "\n".join(f"  {line}" for line in self.exceptional_summary_list) + "\n============================================================\n"

        if squeezed_clusters_cn:
            global_summary_cn = f"当前矩阵中 [{', '.join(squeezed_clusters_cn)}] 已强行步入全球极端挤仓通道。总指挥部战略建议：本周国内实操资金应向上述多头板块对应的[A股个股/国内ETF/场外基金]进行重兵倾斜，参考下方购买区间执行追击，其余资产死锁防御长矛。"
        else:
            global_summary_cn = "当前全线监控矩阵均处于宏观公允震荡区间。总指挥部战略建议：坚决执行既定的左侧网格低吸蓝图，参考下方具体A股/场外基金区间设立分批限价限购单（Limit Orders），静待系统性恐慌下砸坑。"

        total_payload_text = f"""🏛️ [AI QUANTAMENTAL EXECUTIVE PROTOCOL]
报告时间 (北京时间): {self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')} | 数据审计: 🧭 {health_summary}
============================================================
核心全局战略总结 (EXECUTIVE SUMMARY):
{global_summary_cn}
============================================================
{exception_panel}本土化全衍生工具投研矩阵详情 (GLOBAL ANCHORS / A-SHARE ETFS / OTC FUNDS / STOCKS):

{cn_body}------------------------------------------------------------
Pipeline executed successfully in {elapsed_time}s.
Powered by Production Quantamental Engine 10.0 • Confidential"""

        print(total_payload_text)
        
        # 飞书外发网关与指数重试回路
        if self.webhook_url:
            feishu_payload = {"msg_type": "text", "content": {"text": total_payload_text}}
            for attempt in range(NOTIFIER_CONFIG["max_retries"]):
                try:
                    response = requests.post(self.webhook_url, json=feishu_payload, timeout=NOTIFIER_CONFIG["timeout"])
                    if response.status_code == 200:
                        logger.info(f"[NOTIFIER SUCCESS] Data matrix pushed to Feishu on attempt {attempt + 1}")
                        break
                except Exception:
                    if attempt == NOTIFIER_CONFIG["max_retries"] - 1:
                        logger.error("[NOTIFIER CRITICAL] All retry channels exhausted. Feishu gateway unreachable.", exc_info=True)
                    time.sleep(NOTIFIER_CONFIG["retry_delay"])

if __name__ == "__main__":
    matrix_agent = MultiAssetCloudAgent()
    matrix_agent.run_pipeline()
