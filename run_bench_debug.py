import asyncio
import traceback
import sys
import os

# Ensure local modules can be loaded
sys.path.append(os.getcwd())

from src.agent.evaluation.benchmark_runner import run_benchmark

async def main():
    try:
        await run_benchmark()
    except Exception:
        print("\n" + "="*50)
        print("CRITICAL GRAPH ERROR DETECTED")
        print("="*50)
        traceback.print_exc()
        print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
