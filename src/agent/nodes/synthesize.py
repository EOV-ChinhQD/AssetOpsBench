import json
import logging
import re
from langchain_core.messages import AIMessage, ToolMessage
from ..state import AgentState
from ..transcript import log_transcript

logger = logging.getLogger(__name__)

def get_synthesize_node(llm):
    async def synthesize(state: AgentState) -> dict:
        # 1. Extract chart_json and plot_url
        chart_update = {}
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage):
                if "file://" in str(msg.content):
                    match = re.search(r"file://\S+\.png", str(msg.content))
                    if match:
                        chart_update["plot_url"] = match.group(0)
                        break
                try:
                    data = json.loads(str(msg.content))
                    if isinstance(data, dict):
                         payload = data.get("data", {})
                         if isinstance(payload, dict):
                              if "chart_json" in payload:
                                  chart_update["chart_json"] = payload["chart_json"]
                                  chart_update["chart_type"] = payload.get("chart_type", "vegalite")
                              if "url" in payload:
                                  chart_update["plot_url"] = payload["url"]
                              if "chart_json" in chart_update or "plot_url" in chart_update:
                                  break
                except: continue

        # 2. Extract tool results
        results_context = ""
        seen_tools = set()
        for msg in state["messages"]:
            if isinstance(msg, ToolMessage):
                tool_name = msg.name or "tool"
                out_raw = str(msg.content)
                tool_key = f"{tool_name}:{out_raw[:50]}"
                if tool_key in seen_tools: continue
                seen_tools.add(tool_key)
                
                try:
                    data = json.loads(out_raw)
                    if isinstance(data, dict) and "status" in data:
                         payload = data.get('data')
                         msg_str = data.get('message', '')
                         if isinstance(payload, list):
                              formatted_items = []
                              for item in payload:
                                  item_str = str(item)
                                  item_str = re.sub(r"(\d{4})-(\d{2})", r"Tháng \2/\1", item_str)
                                  formatted_items.append(item_str)
                              out = f"{msg_str}\n" + "\n".join(formatted_items)
                         else:
                              out = f"{msg_str} {json.dumps(payload, ensure_ascii=False) if payload else ''}"
                    else: out = out_raw
                except: out = out_raw

                if len(out) > 3000: out = out[:3000] + "..."
                results_context += f"\n--- {tool_name.upper()} ---\n{out}\n"

        # 3. Prompt
        has_chart = "CÓ" if "chart_json" in chart_update or "plot_url" in chart_update else "KHÔNG"
        # 3. Optimized Professional Engineer Prompt
        has_chart = "CÓ BIỂU ĐỒ" if "chart_json" in chart_update or "plot_url" in chart_update else "KHÔNG"
        system_prompt = f"""Bạn là Chuyên gia Vận hành Cấp nước (Senior Water Operations Engineer) tại Hanoi Water AI.
Hãy tổng hợp dữ liệu để TRẢ LỜI NGƯỜI DÙNG theo phong cách chuyên nghiệp, chính xác và có chiều sâu:

1. **CƠ SỞ DỮ LIỆU**: CHỈ sử dụng những con số và thông tin được cung cấp dưới đây. KHÔNG tự bịa số liệu.
2. **PHÂN TÍCH XU HƯỚNG**: Nếu có dữ liệu Lịch sử và Dự báo, hãy so sánh để chỉ ra xu hướng (tăng/giảm/ổn định).
3. **TRỰC QUAN HÓA ({has_chart})**:
   - Nếu có biểu đồ, hãy nhắc người dùng xem biểu đồ và TÓM TẮT những gì biểu đồ thể hiện (Vd: "Biểu đồ cho thấy sản lượng đạt đỉnh vào tháng 10...").
4. **CẤU TRÚC PHẢN HỒI**:
   - **Tóm tắt ngắn gọn** tình hình hiện tại của DMA.
   - **Chi tiết dữ liệu** (dùng bảng nếu có nhiều con số).
   - **Kết luận/Khuyến nghị** dựa trên SOP.

DỮ LIỆU CÔNG CỤ TRẢ VỀ:
{results_context}"""

        try:
            response = await llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": state["messages"][0].content}
            ])
            res_dict = {"messages": [AIMessage(content=response.content)]}
            res_dict.update(chart_update)
            await log_transcript({**state, **res_dict}, "synthesize")
            return res_dict
        except Exception as e:
            logger.error(f"SYNTHESIZE_ERROR: {e}")
            err_res = {"messages": [AIMessage(content=f"Lỗi: {e}")], **chart_update}
            await log_transcript({**state, **err_res}, "synthesize_error")
            return err_res
        
    return synthesize
