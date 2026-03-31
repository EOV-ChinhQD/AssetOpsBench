import pandas as pd
import json
import logging
import os
from sqlalchemy import text
from src.hanoi_water_db import get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hanoi_benchmark")

CSV_PATH = "/home/chinh303/AssetOpsBench/DataHN2.xlsx - Sheet1(2).csv"

def load_ground_truth():
    df = pd.read_csv(CSV_PATH)
    # Mapping based on CSV structure: thang, nam, maDMA, tongSL, soKHCoSD
    df['year_month'] = df.apply(lambda r: f"{int(r['nam'])}-{int(r['thang']):02d}", axis=1)
    df['maDMA'] = df['maDMA'].fillna("GLOBAL").astype(str).str.upper()
    return df

def verify_db_integrity():
    engine = get_engine()
    if not engine:
        logger.error("Database not connected.")
        return
    
    df_gt = load_ground_truth()
    
    # Test cases: (DMA, Month)
    test_cases = [
        ("17-TL", "2025-12"),
        ("01-BĐ", "2025-01"),
        ("05-BĐ", "2024-06"),
        ("10-PL", "2025-12"),
    ]
    
    for dma, ym in test_cases:
        gt_row = df_gt[(df_gt['maDMA'] == dma) & (df_gt['year_month'] == ym)]
        if gt_row.empty:
            logger.warning(f"No ground truth for {dma} at {ym}")
            continue

        gt_val = gt_row['tongSL'].values[0]
        gt_kh = gt_row['soKHCoSD'].values[0]

        try:
            with engine.connect() as conn:
                sql = text("SELECT tongsl, sokhcosd FROM silver.stg_water_demand WHERE madma = :dma AND year_month = :ym")
                res = conn.execute(sql, {"dma": dma, "ym": ym}).fetchone()
                
                db_val = res[0] if res else None
                db_kh = res[1] if res else None
                
                logger.info(f"Check {dma} @ {ym}:")
                logger.info(f"  GT: tongSL={gt_val}, soKH={gt_kh}")
                logger.info(f"  DB: tongSL={db_val}, soKH={db_kh}")
                
                if db_val == gt_val and db_kh == gt_kh:
                     logger.info("  RESULT: MATCH")
                else:
                     logger.warning("  RESULT: MISMATCH")
        except Exception as e:
            logger.error(f"Integrity check failed for {dma}: {e}")

async def run_agent_test():
    # Placeholder for running an orchestration session and checking the final answer
    # This will be expanded once the LLM API is stable
    logger.info("Agent test simulation starting...")
    pass

if __name__ == "__main__":
    verify_db_integrity()
