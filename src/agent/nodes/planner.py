import logging
import json
from langchain_core.messages import SystemMessage
from src.agent.state import AgentState
from src.agent.prompts.prompts import PLANNER_PROMPT

logger = logging.getLogger(__name__)

def get_planner_node(llm):
    """
    ARCHITECTURE (Architect): Determines the high-level strategy and updates the task list.
    """
    async def planner_node(state: AgentState) -> dict:
        print(f"🏗️  PLANNING: Architecting strategy for mission...")
        
        long_term_context = state.get("long_term_context", "Dữ liệu vận hành trạm cấp nước Hà Nội.")
        resolved_dmas_list = list(state.get("resolved_dma", {}).keys())
        task_list = state.get("task_list", [])
        
        # 1. Format Final Prompt
        prompt = PLANNER_PROMPT.format(
            long_term_context=long_term_context,
            resolved_dmas=resolved_dmas_list,
            task_list=json.dumps(task_list, ensure_ascii=False, indent=2)
        )
        
        # 2. Invoke LLM with strict priority directive
        mission_directive = "MISSION: Strictly prioritize get_dma_info first for any station-specific query. No exceptions."
        
        try:
            response = await llm.ainvoke([
                SystemMessage(content=prompt),
                SystemMessage(content=mission_directive),
                *state["messages"]
            ])
            
            # 3. Handle JSON Parsing with retry/repair
            from src.agent.utils import parse_json_from_llm
            parsed = parse_json_from_llm(response.content)
            
            new_tasks = parsed.get("updated_task_list", task_list)
            next_node = parsed.get("next_node", "executor")
            monologue = parsed.get("internal_monologue", "")
            
            logger.info(f"PLANNER: Next={next_node}, Tasks={len(new_tasks)}")
            return {
                "task_list": new_tasks,
                "next_node": next_node,
                "internal_monologue": monologue
            }
            
        except Exception as e:
            logger.error(f"PLANNER_ERROR: {e}")
            # Fallback to executor if planning fails, to avoid bridge break
            return {"next_node": "executor"}

    return planner_node
