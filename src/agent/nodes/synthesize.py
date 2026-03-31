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
        results_context = ""
        seen_tools = set()
        
        for msg in state["messages"]:
            if isinstance(msg, ToolMessage):
                tool_name = msg.name or "tool"
                out_raw = str(msg.content)
                
                # Deduplicate
                tool_key = f"{tool_name}:{out_raw[:50]}"
                if tool_key in seen_tools: continue
                seen_tools.add(tool_key)
                
                # 🟢 Parse JSON and flatten for LLM comprehension
                try:
                    data = json.loads(out_raw)
                    if isinstance(data, dict) and "status" in data:
                         payload = data.get('data')
                         msg_str = data.get('message', '')
                         
                         if isinstance(payload, list):
                             # Flatten list of records and pre-format dates for better LLM matching
                             formatted_items = []
                             for item in payload:
                                 item_str = str(item)
                                 # Smart substitution: 2026-04 -> Tháng 04/2026
                                 import re
                                 item_str = re.sub(r"(\d{4})-(\d{2})", r"Tháng \2/\1", item_str)
                                 formatted_items.append(item_str)
                             
                             payload_str = "\n".join(formatted_items)
                             out = f"{msg_str}\n{payload_str}"
                         else:
                             out = f"{msg_str} {json.dumps(payload, ensure_ascii=False) if payload else ''}"
                    else:
                         out = out_raw
                except:
                    out = out_raw

                if len(out) > 3000: out = out[:3000] + "... [Dữ liệu quá dài]"
                results_context += f"\n--- KẾT QUẢ TỪ {tool_name.upper()} ---\n{out}\n"

        # ... (Security check logic stays same)
        is_dangerous = "drop" in str(state["messages"][0].content).lower() or "[SECURITY_BLOCKED]" in results_context

        # 4. Prompt for LLM synthesis (100% Vietnamese)
        has_chart = "CÓ" if "chart_json" in chart_update or "plot_url" in chart_update else "KHÔNG"
        
        system_prompt = f"""Bạn là Chuyên gia Vận hành hệ thống nước Hà Nội (Hanoi Water AI).
Hãy tổng hợp dữ liệu dưới đây để trả lời người dùng một cách chuyên nghiệp và chính xác.

**QUY TẮC PHẢN HỒI:**
1. CHỈ sử dụng dữ liệu được cung cấp phía dưới. Nếu không thấy, hãy nói "Tôi không tìm thấy dữ liệu".
2. KHÔNG tự bịa ra con số hoặc tên vùng.
3. Nếu có biểu đồ ({has_chart}), hãy nhắc người dùng xem biểu đồ phía trên.
4. Ngôn ngữ: Tiếng Việt trang trọng, ngắn gọn.
5. Đơn vị: Luôn dùng m³ cho sản lượng nước.

**DỮ LIỆU TỪ HỆ THỐNG:**
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
