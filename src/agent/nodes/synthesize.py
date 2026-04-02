import logging
import re
from langchain_core.messages import AIMessage, ToolMessage
from src.agent.state import AgentState
from src.agent.transcript import log_transcript
from src.agent.prompts.prompts import SYNTHESIZE_PROMPT
from src.agent.utils import format_tool_results

logger = logging.getLogger(__name__)

def get_synthesize_node(llm):
    """
    ENGINEER (Synthesizer): Consolidates all data into a professional response.
    """
    async def synthesize(state: AgentState) -> dict:
        print("✍️  SYNTHESIZING: Generating final response based on tool results...")
        logger.info("SYNTHESIZE: Starting final synthesis.")
        
        # 1. Extract visualization metadata
        chart_update = _extract_visualization(state["messages"])
        
        # 2. Format Tool Context
        results_context = format_tool_results(state["messages"])
        
        # 3. Prompting
        plot_url = chart_update.get("plot_url", "")
        has_chart_status = f"CÓ BIỂU ĐỒ (Link: {plot_url})" if plot_url else "KHÔNG CÓ BIỂU ĐỒ"
        
        prompt = SYNTHESIZE_PROMPT.format(
            has_chart=has_chart_status,
            results_context=results_context
        )
        
        try:
            response = await llm.ainvoke([
                {"role": "system", "content": prompt},
                {"role": "user", "content": state["messages"][0].content}
            ])
            
            res_dict = {"messages": [AIMessage(content=response.content)]}
            res_dict.update(chart_update)
            
            await log_transcript({**state, **res_dict}, "synthesize")
            return res_dict
            
        except Exception as e:
            logger.error(f"SYNTHESIZE_ERROR: {e}")
            return {"messages": [AIMessage(content=f"Lỗi tổng hợp: {e}")]}

    return synthesize

def _extract_visualization(messages: list) -> dict:
    import json
    update = {}
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage): continue
        
        content = str(msg.content)
        # Check for direct file paths
        if "file://" in content:
            match = re.search(r"file://\S+\.png", content)
            if match:
                update["plot_url"] = match.group(0)
                break
        
        # Check for JSON payloads
        try:
            data = json.loads(content)
            payload = data.get("data", {})
            if isinstance(payload, dict):
                if "chart_json" in payload:
                    update["chart_json"] = payload["chart_json"]
                    update["chart_type"] = payload.get("chart_type", "vegalite")
                if "url" in payload:
                    update["plot_url"] = payload["url"]
                if "chart_json" in update or "plot_url" in update:
                    break
        except: continue
    return update
