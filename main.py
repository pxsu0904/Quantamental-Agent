import socket
# 🛠️ 核心突破：刚性设置全局底层网络超时锁为 15 秒，强制封杀 yfinance 在云端被 Yahoo 屏蔽时产生的无尽挂起死锁
socket.setdefaulttimeout(15)

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

# 統一工程級純中性日誌規範 (完全剝離任何情緒化或股評描述)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("MatrixMasterEngine_V26_5_4")

# ====================================================================================
# 🎛️ PORTFOLIO STRUCTURAL CONFIGURATION (資產大類解耦配置中心 - MVP 26.5.4 LTS)
# ====================================================================================
TICKERS = {
    "COPPER": "HG=F",      # COMEX期銅 (全球工業商品定價參考錨)
    "RESOURCE": "COPX",    # 資源多頭線 (礦業巨頭ETF / 盛達資源等國內有色映射)
    "TECH": "XLK",         # 科技算力線 (全球AI硬件資本池 / 納指核心拉動源)
    "GOLD": "GLD",         # 避險貴金屬 (實盤防守超配資產)
    "FIXED_INCOME": "TLT", # 跨周期長債 (宏觀無風險流動性對沖資產)
    "DXY": "DX-Y.NYB",     # 美元指數 (全球流動性總閘門基準)
    "US10Y": "^TNX",       # 美元10年期國債收益率 (全球資產重力底座)
    "FX": "USDCNY=X"       # 離岸人民幣匯率
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
    "TOTAL_CAPITAL": 40000.0,  # 真實基準留學配置資金池 (元)
    "CURRENT_ALLOCATION": {
        "GOLD": 0.28, "RESOURCE": 0.22, "TECH": 0.18, "FIXED_INCOME": 0.15, "CASH": 0.17
    },
    "STRATEGIC_BASELINE": {
        "GOLD": 0.15, 
        "RESOURCE": 0.20, 
        "TECH": 0.30,          # 戰術配置基礎中樞上限自洽 (30%)
        "FIXED_INCOME": 0.25,  # 防御長債配置基礎中樞 (25%)
        "CASH": 0.10           # 剛性最低儲備現金率 (10%)
    }
}

# 隔離低波防守資產天花板，釋放數理優化空間
IRON_LAWS = {
    "COOLING_PERIOD_DAYS": 14,         # 鐵律一：真實調倉間隔必須 ≥ 14天
    "MAX_REBALANCE_ADJUSTMENT": 0.05,  # 鐵律二：單次再平衡調倉步長幅度 ≤ 總資產5%
    "MIN_CASH_FLOOR": 0.10,            # 鐵律三：動態現金倉位必須 ≥ 10% (強保剛性流動性大底)
    "MAX_ASSET_CEILING": 0.30,         # 鐵律四：權益/商品單一風險資產持倉上限 ≤ 30% 
    "MAX_BOND_CEILING": 0.45,          # 長債類低波防守資產持倉上限放寬至 45%
    "BIAS_WINDOW_THRESHOLD": 2.0,      # 歷史相似狀態對稱切片鄰域 (±2.0%)
    "MIN_HISTORICAL_SAMPLES": 20,      # 最小歷史有效同質樣本數門檻
    "REBALANCE_TRIGGER_THRESHOLD": 0.025, # 戰術再平衡激活起扣點 (2.5%)
    "BLEND_FACTOR": 0.30,              # 風格權重加權融合比例
    "MIN_COPPER_DOWNSIDE_FLOOR": 3.0   # 國際期銅下跌空間最低技術保護底噪 (%)
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

class PortfolioDisciplineEngineV26_5_4:
    def __init__(self):
        self.beijing_time = datetime.now(timezone.utc) + timedelta(hours=8)
        self.metrics =
