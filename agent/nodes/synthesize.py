import json
import logging
from langchain_core.messages import AIMessage, ToolMessage
from ..state import AgentState

logger = logging.getLogger(__name__)

def get_synthesize_node(llm):
    async def synthesize(state: AgentState) -> dict:
        # 1. Extract chart_json and plot_url from any ToolMessage in the conversation
        chart_update = {}
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage):
                # Detect URL
                if "file://" in str(msg.content):
                    import re
                    match = re.search(r"file://\S+\.png", str(msg.content))
                    if match:
                        chart_update["plot_url"] = match.group(0)
                        break
                try:
                    data = json.loads(msg.content)
                    if isinstance(data, dict) and "chart_json" in data:
                        chart_update["chart_json"] = data["chart_json"]
                        chart_update["chart_type"] = data.get("chart_type", "vegalite")
                        break
                except: continue

        # 2. Extract ALL tool results from the entire conversation
        # (Not just trailing ToolMessages — handles multi-round reflect→retry)
        results_context = ""
        seen_tools = set()
        
        for msg in state["messages"]:
            if isinstance(msg, ToolMessage):
                tool_name = msg.name or "tool"
                out = str(msg.content)
                
                # Deduplicate: if same tool returned data before, keep the latest
                tool_key = f"{tool_name}:{out[:50]}"
                if tool_key in seen_tools:
                    continue
                seen_tools.add(tool_key)
                
                if len(out) > 3000:
                    out = out[:3000] + "... [Dữ liệu quá dài]"
                results_context += f"\n- {tool_name}: {out}"

        # Fallback to state tool_results
        if not results_context and state.get("tool_results"):
            for r in state["tool_results"][-5:]:
                out = str(r.get("output", ""))
                if len(out) > 3000: out = out[:3000] + "..."
                results_context += f"\n- {r.get('tool')}: {out}"
        
        logger.info(f"SYNTHESIZE: results_context_len={len(results_context)}, has_chart={'chart_json' in chart_update}")
        
        # 3. Security check
        dangerous_keywords = ["drop", "delete", "truncate", "update", "insert", "alter", "create"]
        first_msg = str(state["messages"][0].content).lower()
        
        is_dangerous = any(kw in first_msg for kw in dangerous_keywords) or \
                       "[SECURITY_BLOCKED]" in results_context or \
                       "guardrail" in results_context.lower()

        if is_dangerous:
            rejection_msg = "Tôi không có quyền thực hiện các lệnh thay đổi dữ liệu. Tôi chỉ được phép truy vấn SELECT."
            return {"messages": [AIMessage(content=rejection_msg)]}

        # 4. Prompt for LLM synthesis
        has_chart = "YES" if "chart_json" in chart_update or "plot_url" in chart_update else "NO"
        plot_info = f"\nBiểu đồ đã được tạo tại: {chart_update.get('plot_url')}" if "plot_url" in chart_update else ""
        
        system_prompt = f"""Bạn là trợ lý vận hành hệ thống nước Hà Nội.
Sử dụng DỮ LIỆU bên dưới để trả lời. KHÔNG bịa thêm.

**QUY TẮC:**
1. CHỈ dùng dữ liệu bên dưới. Không có → "Tôi không tìm thấy dữ liệu".
2. KHÔNG liệt kê DMA nếu chỉ có con số tổng.
3. Nếu có biểu đồ ({has_chart}), kết thúc bằng: "Mời bạn xem biểu đồ chi tiết phía trên."
4. Trả lời NGẮN GỌN, CHUYÊN NGHIỆP, bằng Tiếng Việt.
5. Khi nói về sản lượng, luôn kèm đơn vị m³.
{plot_info}

**DỮ LIỆU TỪ CÔNG CỤ:**
{results_context}
"""
        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state["messages"][0].content}
        ])
        
        res_dict = {"messages": [AIMessage(content=response.content)]}
        res_dict.update(chart_update)
        return res_dict
        
    return synthesize
