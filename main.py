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
# 🎛️ CONFIGURATION CENTRAL (全球大宗商品多衍生工具参数配置中台 - 配置驱动架构)
# ====================================================================================
HTTP_CONFIG = {
    "timeout_market": 8,       
    "timeout_notify": 10,      
    "timeout_llm": 15,         
    "max_retries": 3,          
    "retry_delay": 1,          
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

PRICE_CONFIG = {
    "decimals": 4,             
    "display_decimals": 2      
}

TENCENT_FIELDS = {
    "PRICE": 3,
    "CHANGE_PCT": 32
}

# 大模型接口路由配置中台
LLM_CONFIG = {
    "enable_llm": os.environ.get("ENABLE_LLM", "true").lower() == "true", 
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "base_url": os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    "model": os.environ.get("LLM_MODEL", "deepseek-chat")
}

# 全球宏观核心定价动能因子雷达字典
MACRO_TICKERS = {
    "DXY": {"ticker": "DX-Y.NYB", "name": "美元指数 (DXY)"},
    "OIL": {"ticker": "CL=F", "name": "WTI原油 (工业能源成本)"},
    "VIX": {"ticker": "^VIX", "name": "美股恐慌指数 (VIX风险情绪)"}
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
        "telemetry_cn": "加工费: $4.5 | LME库存变动: -14.53% MoM | 库存维持: 6.82天 (行业静态参谋数据)",
        "is_squeeze": False,
        "assets": {
            "anchor": {"ticker": "HG=F", "name": "COMEX期铜主合约", "modifier": 0.98, "bound": (2.0, 15.0), "currency": "USD", "type_label": "参考锚", "market": "US"},
            "a-etf": {"ticker": "512400.SS", "name": "南方有色金属ETF ", "modifier": 1.01, "bound": (0.5, 5.0), "currency": "CNY", "type_label": "基 金", "market": "CN"},
            "stock": {"ticker": "601899.SS", "name": "紫金矿业(铜金巨鳄)", "modifier": 1.03, "bound": (5.0, 50.0), "currency": "CNY", "type_label": "个 股", "market": "CN"}
        },
        "strat_cn_stable": "整体估值对齐公允区间。周一早盘若随大盘洗盘砸出低位，参考实操区间分批左侧限价埋伏。",
        "strat_cn_squeeze": "板块触发集体逼空共振！行业Gamma爆发，开盘参考建议区间右侧动量追击，有色基金加码。"
    },
    "URANIUM_CLUSTER": {
        "name_cn": "全球核铀资产矩阵 (Uranium Matrix)",
        "telemetry_cn": "铀产量达成率: 82% | Big Tech核能PPA增速: +42% | 商业库存覆盖: 14.2个月 (行业静态参谋数据)",
        "is_squeeze": True,
        "assets": {
            "anchor": {"ticker": "CCJ", "name": "卡梅科 Cameco    ", "modifier": 1.05, "bound": (15.0, 300.0), "currency": "USD", "type_label": "参考锚", "market": "US"},
            "a-etf": {"ticker": "516290.SS", "name": "易方达中证核能电力ETF", "modifier": 1.03, "bound": (0.3, 4.0), "currency": "CNY", "type_label": "基 金", "market": "CN"},
            "stock": {"ticker": "001280.SZ", "name": "中国铀业(特许龙头)", "modifier": 1.06, "bound": (10.0, 200.0), "currency": "CNY", "type_label": "个 股", "market": "CN"}
        },
        "strat_cn_stable": "远期长协价格稳定。当前股价已部分透支算力中心PPA预期，保持底仓观望，不盲目追高。",
        "strat_cn_squeeze": "算力中心核能黑洞爆发，公用事业去库超预期。开盘参考各衍生工具区间执行右侧动量追击。"
    },
    "SILVER_CLUSTER": {
        "name_cn": "工业白银资产矩阵 (Silver Matrix)",
        "telemetry_cn": "伴生矿减产: -6.2% | 光伏银浆耗量动量: +28% | LBMA金库去库率: -11.4% MoM (行业静态参谋数据)",
        "is_squeeze": False,
        "assets": {
            "anchor": {"ticker": "SI=F", "name": "COMEX期银主合约 ", "modifier": 0.98, "bound": (10.0, 100.0), "currency": "USD", "type_label": "参考锚", "market": "US"},
            "a-etf": {"ticker": "161226.SZ", "name": "国投瑞银白银期货 ", "modifier": 0.99, "bound": (0.5, 5.0), "currency": "CNY", "type_label": "基 金", "market": "CN"},
            "stock": {"ticker": "000603.SZ", "name": "盛达资源(储量之王)", "modifier": 1.03, "bound": (3.0, 40.0), "currency": "CNY", "type_label": "个 股", "market": "CN"}
        },
        "strat_cn_stable": "金银比价处于历史均值区间。光伏刚需稳健但尚未触发流动性踩踏，维持网格策略分批低吸。",
        "strat_cn_squeeze": "光伏银浆消耗断裂，金银比价强行破位。触发白银极端逼空信号，全额推入本土LOF或个股份额。"
    },
    "TRANSFORMERS_CLUSTER": {
        "name_cn": "电网变压器资产矩阵 (Grid Transformer)",
        "telemetry_cn": "硅钢溢价: +18.5% | 北美变压器交期: 38个月 | 未交付订单比: 2.4x (行业静态参谋数据)",
        "is_squeeze": True,
        "assets": {
            "anchor": {"ticker": "GEV", "name": "奇异维诺瓦 GEV    ", "modifier": 1.08, "bound": (50.0, 2000.0), "currency": "USD", "type_label": "参考锚", "market": "US"}, 
            "a-etf": {"ticker": "159326.SZ", "name": "华夏中证电网设备 ", "modifier": 1.03, "bound": (0.5, 5.0), "currency": "CNY", "type_label": "基 金", "market": "CN"},
            "stock": {"ticker": "600089.SS", "name": "特变电工(骨干龙头)", "modifier": 1.05, "bound": (5.0, 50.0), "currency": "CNY", "type_label": "个 股", "market": "CN"}
        },
        "strat_cn_stable": "电网升级周期有条不紊，供应链交期处于季节性常态，维持中线价值投资持有仓位。",
        "strat_cn_squeeze": "海外电网扩容排队喷发，变压器交期锁死3年以上。重工红利步入垄断暴利期，坚决锁死龙头。"
    }
}

class MultiAssetCloudAgent:
    def __init__(self):
        self._start_time = time.time()
        self.beijing_time = datetime.now(timezone.utc) + timedelta(hours=8)
        self.webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
        self.history_file = "asset_history.csv"
        self.batch_log_buffer = [] 
        
        self.stale_assets_count = 0              
        self.blocked_assets_count = 0            
        self.cn_yfinance_fallback_count = 0      
        self.exceptional_summary_list = []      
        
        self._cn_batch_pool = {}
        self._macro_live_factors_text = "未激活/暂无数据"  
        
        self._cached_history_df = pd.DataFrame()
        self._load_and_cache_ledger()
        self._validate_incoming_configuration()
        self._pre_fetch_cn_market_batch()

    def _load_and_cache_ledger(self):
        if os.path.exists(self.history_file):
            try:
                self._cached_history_df = pd.read_csv(self.history_file, encoding="utf-8-sig")
            except Exception:
                logger.error("[DATABASE EXCEPTION] CSV storage structure corrupted. Activating rolling backup strategy...", exc_info=True)
                try:
                    bak_file = f"{self.history_file}.{int(time.time())}.bak"
                    os.rename(self.history_file, bak_file)
                except Exception as ex:
                    logger.error(f"[DISASTER RECOVERY FAIL] Failed to rename broken file node: {ex}", exc_info=True)
                self._cached_history_df = pd.DataFrame()

    def _validate_incoming_configuration(self):
        required_cluster_keys = ["name_cn", "telemetry_cn", "is_squeeze", "assets"]
        required_asset_keys = ["ticker", "name", "modifier", "bound", "currency", "type_label", "market"]
        
        for cluster_id, config in MATRIX_CONFIG.items():
            for k in required_cluster_keys:
                if k not in config: raise KeyError(f"[CONFIG CRITICAL] Cluster '{cluster_id}' missing key: '{k}'")
            
            params = config.get("strategy_params", DEFAULT_STRATEGY_PARAMS)
            if "squeeze_band" not in params or "stable_band" not in params:
                raise KeyError(f"[CONFIG CRITICAL] Cluster '{cluster_id}' strategy_params lacks required sub-keys.")
                
            for asset_type, asset_info in config["assets"].items():
                for ak in required_asset_keys:
                    if ak not in asset_info: raise KeyError(f"[CONFIG CRITICAL] Asset '{cluster_id}.{asset_type}' missing key: '{ak}'")

    def _pre_fetch_cn_market_batch(self):
        cn_tickers = []
        for cluster in MATRIX_CONFIG.values():
            for asset in cluster["assets"].values():
                if asset["market"] == "CN": cn_tickers.append(asset["ticker"])
        if not cn_tickers: return

        mapped_symbols = []
        symbol_map = {}
        for tk in cn_tickers:
            sym = f"sh{tk[:-3]}" if tk.endswith(".SS") else f"sz{tk[:-3]}"
            mapped_symbols.append(sym)
            symbol_map[sym] = tk

        url = f"https://qt.gtimg.cn/q={','.join(mapped_symbols)}"
        headers = {"User-Agent": HTTP_CONFIG["user_agent"]}
        
        try:
            resp = requests.get(url, headers=headers, timeout=HTTP_CONFIG["timeout_market"])
            text = resp.content.decode('gbk', errors='ignore')

            for line in text.split('\n'):
                if not line.strip(): continue
                if "none_match" in line:
                    logger.warning(f"[MARKET ENGINE] Partial none_match detected in segment: {line.strip()}")
                    continue
                if '=' in line and '~' in line:
                    sym_part = line.split('=')[0].replace("v_", "").strip()
                    raw_data = line.split('"')[1]
                    parts = raw_data.split('~')
                    if len(parts) > max(TENCENT_FIELDS.values()):
                        orig_ticker = symbol_map.get(sym_part)
                        if orig_ticker:
                            live_price = round(float(parts[TENCENT_FIELDS["PRICE"]]), PRICE_CONFIG["decimals"])
                            change_pct = round(float(parts[TENCENT_FIELDS["CHANGE_PCT"]]), PRICE_CONFIG["display_decimals"])
                            self._cn_batch_pool[orig_ticker] = (live_price, change_pct)
            logger.info(f"[MARKET ENGINE] Microsecond batch pipeline mapped {len(self._cn_batch_pool)} domestic assets.")
        except Exception:
            logger.error("[MARKET ENGINE] Tencent HTTP backbone pool connection timeout.", exc_info=True)

    def _get_dynamic_fallback_price(self, ticker):
        if not self._cached_history_df.empty:
            try:
                ticker_df = self._cached_history_df[self._cached_history_df["ticker"] == ticker]
                if not ticker_df.empty: return float(ticker_df.iloc[-1]["live_price"])
            except Exception:
                logger.error(f"[CACHE FAILURE] Memory tracking block index missed for {ticker}", exc_info=True)
        return STATIC_FALLBACK_PRICES.get(ticker, 100.0)

    def _fetch_yfinance_price(self, ticker):
        ticker_obj = yf.Ticker(ticker)
        try:
            hist = ticker_obj.history(period="2d")
            if hist is not None and not hist.empty and len(hist) >= 1:
                live_price = round(hist['Close'].iloc[-1], PRICE_CONFIG["decimals"])
                change_pct = None
                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    change_pct = round(((live_price / prev_close) - 1) * 100, PRICE_CONFIG["display_decimals"])
                return live_price, change_pct, False
        except Exception:
            pass
        return self._get_dynamic_fallback_price(ticker), None, True

    def _fetch_live_price(self, ticker, market):
        if market == "US": return self._fetch_yfinance_price(ticker)
        if market == "CN":
            if ticker in self._cn_batch_pool: return self._cn_batch_pool[ticker][0], self._cn_batch_pool[ticker][1], False
            self.cn_yfinance_fallback_count += 1
            return self._fetch_yfinance_price(ticker)

    def _execute_dynamic_macro_radar(self):
        logger.info("[MACRO RADAR] Initiating global live macro factors scanning...")
        factor_lines = []
        for key, info in MACRO_TICKERS.items():
            price, change, _ = self._fetch_yfinance_price(info["ticker"])
            change_str = f"({'+' if change and change > 0 else ''}{change}%)" if change is not None else "(--%)"
            factor_lines.append(f"  • {info['name']}: {price} {change_str}")
        self._macro_live_factors_text = "\n".join(factor_lines)

    def _execute_llm_brain_attribution(self, raw_payload_for_ai):
        if not LLM_CONFIG["enable_llm"] or not LLM_CONFIG["api_key"]:
            logger.warning("[LLM ENGINE] LLM module deactivated or API token missing. Bypassed to template engine.")
            return None

        for attempt in range(2):
            try:
                url = f"{LLM_CONFIG['base_url'].rstrip('/')}/chat/completions"
                prompt = f"""你是一位在全球顶级对冲基金服役的资深大宗商品与有色金属量化策略总监。
下面是今天从全球行情网关以及宏观因子雷达中聚合而来的原始快照：

[宏观核心定价动能因子]:
{self._macro_live_factors_text}

[各衍生工具盘面精算明细]:
{raw_payload_for_ai}

请严格基于上述客观数据流，为投资决策层撰写一份宏观透视归因报告。

要求：
1. 结合最新的美元指数、原油以及VIX风险情绪，深入剖析其对精铜/核铀/白银/变压器资产的估值抑制或动能传导，撰写一份150字内冷酷利落的【EXECUTIVE SUMMARY (核心全局战略总结)】。
2. 为精铜、核铀、白银、电网变压器这四个板块，结合现价与模型公允区间的级差，分别重新撰写一段具有绝对实战指导意义的【交易台决策指引】。
3. 保持客观、严谨的行研黑话风格。输出格式必须完全对齐以下文本结构，不要夹带任何Markdown语法标记（如```或**）：

核心全局战略总结 (EXECUTIVE SUMMARY):
[动态撰写内容]

各板块临盘交易台决策指引:
■ 全球精铜资产指引: [针对性内容]
■ 全球核铀资产指引: [针对性内容]
■ 全球工业白银指引: [针对性内容]
■ 电网变压器设备指引: [针对性内容]
"""
                headers = {"Authorization": f"Bearer {LLM_CONFIG['api_key']}", "Content-Type": "application/json"}
                payload = {"model": LLM_CONFIG["model"], "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
                
                resp = requests.post(url, headers=headers, json=payload, timeout=HTTP_CONFIG["timeout_llm"])
                if resp.status_code == 200:
                    ai_text = resp.json()["choices"][0]["message"]["content"].strip()
                    ai_text = ai_text.replace("```text", "").replace("```", "").strip()
                    logger.info("[LLM ENGINE] Dynamic report cognitive attribution complete.")
                    return ai_text
                logger.warning(f"[LLM ENGINE] Gateway returned status {resp.status_code} on attempt {attempt + 1}")
            except Exception as e:
                logger.error(f"[LLM ENGINE] Request gate break ({e}) on attempt {attempt + 1}", exc_info=True)
            time.sleep(1)
        return None

    def _calculate_buy_zone(self, live_price, target_price, is_squeeze, params, sym):
        if is_squeeze:
            buy_zone_low = round(live_price * params["squeeze_band"][0], PRICE_CONFIG["display_decimals"])
            buy_zone_high = round(target_price * params["squeeze_band"][1], PRICE_CONFIG["display_decimals"])
            return f"{sym}{buy_zone_low} - {sym}{buy_zone_high} (右侧动量追击位)"
        else:
            buy_zone_low = round(target_price * params["stable_band"][0], PRICE_CONFIG["display_decimals"])
            buy_zone_high = round(target_price * params["stable_band"][1], PRICE_CONFIG["display_decimals"])
            return f"{sym}{buy_zone_low} - {sym}{buy_zone_high} (左侧边际挂单位)"

    def _collect_log_data(self, ticker, market, live_price, target_price):
        self.batch_log_buffer.append({
            "date": self.beijing_time.strftime('%Y-%m-%d'),
            "ticker": ticker,
            "market": market,
            "live_price": round(live_price, PRICE_CONFIG["decimals"]),
            "target_price": round(target_price, PRICE_CONFIG["decimals"])
        })

    def _commit_batch_logs_to_database(self):
        if not self.batch_log_buffer: return
        try:
            new_df = pd.DataFrame(self.batch_log_buffer)
            if os.path.exists(self.history_file) and not self._cached_history_df.empty:
                combined_df = pd.concat([self._cached_history_df, new_df], ignore_index=True)
                combined_df.drop_duplicates(subset=["date", "ticker", "market"], keep="last", inplace=True)
                combined_df.to_csv(self.history_file, index=False, encoding="utf-8-sig")
                self._cached_history_df = combined_df
                logger.info(f"[DATABASE SUCCESS] Decoupled records synchronized. Ledger total records: {len(combined_df)}")
                return
            new_df.to_csv(self.history_file, index=False, encoding="utf-8-sig")
            self._cached_history_df = new_df
            logger.info("[DATABASE SUCCESS] Established new time-series data storage node.")
        except Exception:
            logger.error("[DATABASE EXCEPTION] Batch atomic operation crashed during database disk mapping", exc_info=True)

    def run_pipeline(self):
        logger.info("===== MATRIX PRODUCTION PIPELINE INITIATED =====")
        
        self._execute_dynamic_macro_radar()
        
        cn_body = ""
        raw_payload_for_ai = "" 
        squeezed_clusters_cn = []
        
        for cluster_key, cluster_cfg in MATRIX_CONFIG.items():
            cn_body += f"■ 品种矩阵: {cluster_cfg['name_cn']}\n"
            
            if cluster_cfg["is_squeeze"]:
                squeezed_clusters_cn.append(cluster_cfg["name_cn"].split(" (")[0])
                
            params = cluster_cfg.get("strategy_params", DEFAULT_STRATEGY_PARAMS)
                
            for asset_type, asset_info in cluster_cfg["assets"].items():
                ticker = asset_info["ticker"]
                sym = "$" if asset_info["currency"] == "USD" else "¥"
                
                live_price, change_pct, is_fallback = self._fetch_live_price(ticker, asset_info["market"])
                
                low_limit, high_limit = asset_info["bound"]
                if not (low_limit <= live_price <= high_limit):
                    logger.critical(f"[DATA PROTECTION BLOCKED] Defending boundary breach for {ticker}: {sym}{live_price}")
                    self.blocked_assets_count += 1 
                    self.exceptional_summary_list.append(f"  🔴 统计边界熔断: {asset_info['name']} ({ticker})")
                    cn_body += f"  • [{asset_info['type_label']}] {asset_info['name']}: 🔴 价格溢出常识边界限制，防空网触发硬熔断拦截保护。\n"
                    continue
                    
                if is_fallback:
                    self.stale_assets_count += 1
                    self.exceptional_summary_list.append(f"  ⚠️ 临盘数据延迟: {asset_info['name']} ({ticker})")
                    
                target_price = round(live_price * asset_info["modifier"], PRICE_CONFIG["decimals"])
                potential_upside = round(((target_price / live_price) - 1) * 100, PRICE_CONFIG["display_decimals"])
                
                self._collect_log_data(ticker, asset_info["market"], live_price, target_price)
                buy_zone_str = self._calculate_buy_zone(live_price, target_price, cluster_cfg["is_squeeze"], params, sym)
                
                stale_marker = "*" if is_fallback else ""
                change_str = f"({'+' if change_pct > 0 else ''}{change_pct}%)" if change_pct is not None else "(--%)"
                
                upside_sign = "+" if potential_upside >= 0 else "-"
                space_label = "相对公允溢价(上涨空间)" if potential_upside >= 0 else "相对公允溢价(回调空间)"
                abs_upside = abs(potential_upside)
                
                cn_body += f"  • [{asset_type.upper() if asset_info['market']=='US' else asset_info['type_label']}] {asset_info['name']}\n" \
                           f"    现价: {sym}{live_price}{stale_marker} {change_str} | 公允: {sym}{target_price}\n" \
                           f"    {space_label}: {upside_sign}{abs_upside}%\n" \
                           f"    🎯 建议实操区间: {buy_zone_str}\n"
                raw_payload_for_ai += f"矩阵:{cluster_cfg['name_cn']} | 标的:{asset_info['name']}({ticker}) | 现价:{sym}{live_price} | 涨跌幅:{change_str} | 公允价:{sym}{target_price} | 实操区间:{buy_zone_str}\n"
                
            strat_cn = cluster_cfg["strat_cn_squeeze"] if cluster_cfg["is_squeeze"] else cluster_cfg["strat_cn_stable"]
            cn_body += f"- 静态参考指引: {strat_cn}\n\n"

        self._commit_batch_logs_to_database()
        elapsed_time = round(time.time() - self._start_time, PRICE_CONFIG["display_decimals"])

        ai_brain_report = self._execute_llm_brain_attribution(raw_payload_for_ai)
        
        deduped_exceptions = list(dict.fromkeys(self.exceptional_summary_list))
        exception_panel = ""
        if deduped_exceptions:
            exception_panel = "🚨 [数据健康度审计异常置顶警报清单]:\n" + "\n".join(deduped_exceptions) + "\n=========================================\n"

        if ai_brain_report and len(ai_brain_report) > 50:
            strategy_panel = f"=========================================\n" \
                             f"{ai_brain_report}\n"
        else:
            if squeezed_clusters_cn:
                global_summary_cn = f"当前矩阵中 [{', '.join(squeezed_clusters_cn)}] 进入全球挤仓通道。建议核心实体资金向对应[A股个股/国内ETF/场外基金]进行重兵倾斜。"
            else:
                global_summary_cn = "当前全线监控矩阵均处于宏观公允震荡区间。坚决执行既定的左侧网格低吸蓝图，以限价单静待系统性恐慌下砸坑。"
            strategy_panel = f"=========================================\n" \
                             f"核心全局战略总结 (EXECUTIVE SUMMARY):\n{global_summary_cn}\n"

        is_weekend = self.beijing_time.weekday() >= 5
        health_summary = f"最新有效收盘价" if is_weekend else f"全线实时水源100%净水对齐"
        if self.stale_assets_count > 0 or self.blocked_assets_count > 0:
            health_summary = f"延迟兜底: {self.stale_assets_count}项 | 熔断拦截: {self.blocked_assets_count}项"

        total_payload_text = f"""🏛️ [AI QUANTAMENTAL EXECUTIVE PROTOCOL]
报告时间 (北京时间): {self.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}
数据审计: 🧭 {health_summary} (内容由AI生成，仅供模型归因参考)
=========================================
[📈 全球宏观因子雷达实时扫描]:
{self._macro_live_factors_text}
{strategy_panel}=========================================
本土化全衍生工具投研矩阵详情 (GLOBAL ANCHORS / A-SHARE ETFS / OTC FUNDS / STOCKS):

{cn_body}-----------------------------------------
[SYSTEM LOG] Pipeline processed successfully. Total assets audited: {sum(len(c['assets']) for c in MATRIX_CONFIG.values())} | Tencent-to-YF Fallbacks: {self.cn_yfinance_fallback_count} | Ledger Fallbacks: {self.stale_assets_count} | Blocked: {self.blocked_assets_count} | Latency: {elapsed_time}s.
Powered by Production Quantamental Engine 10.0"""

        print(total_payload_text)
        
        if self.webhook_url:
            feishu_payload = {"msg_type": "text", "content": {"text": total_payload_text}}
            for attempt in range(HTTP_CONFIG["max_retries"]):
                try:
                    response = requests.post(self.webhook_url, json=feishu_payload, timeout=HTTP_CONFIG["timeout_notify"])
                    if response.status_code == 200:
                        logger.info(f"[NOTIFIER SUCCESS] Data matrix pushed to Feishu on attempt {attempt + 1}")
                        break
                except Exception:
                    if attempt == HTTP_CONFIG["max_retries"] - 1:
                        logger.error("[NOTIFIER CRITICAL] Feishu gateway unreachable.", exc_info=True)
                    time.sleep(HTTP_CONFIG["retry_delay"])

if __name__ == "__main__":
    matrix_agent = MultiAssetCloudAgent()
    matrix_agent.run_pipeline()
