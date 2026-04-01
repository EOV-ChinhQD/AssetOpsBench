import asyncio
import os
import json
from src.servers.hanoi_water.main import _get_dma_info_logic

async def debug():
    print("Testing _get_dma_info_logic with 'DMA 03-LB'...")
    res = await _get_dma_info_logic("DMA 03-LB")
    print(f"Result: {res}")
    
    print("\nTesting _get_dma_info_logic with '03-LB'...")
    res = await _get_dma_info_logic("03-LB")
    print(f"Result: {res}")

if __name__ == "__main__":
    asyncio.run(debug())
