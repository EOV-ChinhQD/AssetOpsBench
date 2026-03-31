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
    # --- PART 2: Forecast Integrity (Gold Table) ---
    logger.info("--- PART 2: Forecast Integrity (Gold Table) ---")
    forecast_cases = [
        ("18-SS", "2026-02"),
        ("10-PT", "2026-02"),
        ("05-VH", "2026-02"),
    ]
    
    for dma, ym in forecast_cases:
        try:
            with engine.connect() as conn:
                sql = text("SELECT predicted_demand FROM gold.fct_predictions_unified WHERE madma = :dma AND year_month = :ym")
                db_val = conn.execute(sql, {"dma": dma, "ym": ym}).scalar()
                
                if db_val:
                    logger.info(f"Check Forecast {dma} @ {ym}: predicted_demand={db_val} m³ [OK]")
                else:
                    logger.warning(f"Check Forecast {dma} @ {ym}: NO DATA FOUND in Gold table.")
        except Exception as e:
            logger.error(f"Gold table check failed: {e}")

async def run_agent_test():
    """
    Perform real End-to-End agent evaluation.
    Invokes the graph for each scenario and compares output against ground truth.
    """
    from src.agent.graph import build_graph
    from src.llm.langchain_adapter import LangchainLiteLLM
    
    logger.info("\n--- PART 3: Agent E2E Evaluation ---")
    
    model_id = os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3-8B")
    llm = LangchainLiteLLM(model_id=model_id)
    graph = await build_graph(llm)
    
    scenarios = [
        {"q": "Tổng sản lượng DMA 17-TL tháng 12/2025?", "expected_val": 411589},
        {"q": "Dự báo sản lượng DMA 18-SS tháng 02/2026?", "expected_val": 4202},
    ]
    
    for s in scenarios:
        logger.info(f"Question: {s['q']}")
        inputs = {"messages": [("human", s['q'])], "user_id": "bench_001"}
        config = {"configurable": {"thread_id": f"bench_{s['expected_val']}"}}
        
        try:
            # Run the agent
            result = await graph.ainvoke(inputs, config=config)
            answer = result["messages"][-1].content
            
            logger.info(f"  Agent Answer: {answer[:100]}...")
            
            # Simple numeric check
            expected = str(s['expected_val'])
            if expected in answer.replace(",", "").replace(".", ""):
                logger.info(f"  RESULT: PASS (Found {expected})")
            else:
                logger.warning(f"  RESULT: FAIL (Expected {expected} not found in answer)")
        except Exception as e:
            logger.error(f"  Execution Error: {e}")

if __name__ == "__main__":
    verify_db_integrity()
    import asyncio
    asyncio.run(run_agent_test())
