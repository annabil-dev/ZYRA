import logging
import json
import time
from typing import List, Dict, Any, Callable
from app.core.tools import execute_tool, TOOLS_SCHEMA

class AgentState:
    IDLE = "IDLE"
    THINKING = "THINKING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"

class AutonomousAgent:
    """
    A robust ReAct-style Agent loop that can run long tasks and emit state changes.
    This replaces the simple 5-iteration loop in the standard inference worker,
    laying the groundwork for Proof-of-Useful-Work (PoUW).
    """
    def __init__(self, llm_client, max_iterations: int = 15):
        self.llm_client = llm_client
        self.max_iterations = max_iterations
        self.state = AgentState.IDLE
        self.logger = logging.getLogger("agent.core")
        
        # Callbacks for UI updates
        self.on_state_change: Callable[[str], None] = None
        self.on_log: Callable[[str], None] = None
        
        self.is_interrupted = False

    def interrupt(self):
        self.is_interrupted = True
        self.llm_client.interrupt()

    def _set_state(self, new_state: str):
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(self.state)

    def _log(self, msg: str):
        self.logger.info(msg)
        if self.on_log:
            self.on_log(msg)

    def run_task(
        self, 
        task_prompt: str, 
        system_context: str = "",
        security_callback: Callable = None
    ) -> str:
        """
        Executes a task autonomously until completion or max iterations.
        """
        self.is_interrupted = False
        self._set_state(AgentState.THINKING)
        self._log(f"Task started: {task_prompt}")
        
        messages = [
            {"role": "system", "content": system_context},
            {"role": "user", "content": task_prompt}
        ]
        
        iteration = 0
        final_answer = ""
        
        while iteration < self.max_iterations:
            if self.is_interrupted:
                self._log("Task interrupted by user.")
                self._set_state(AgentState.ERROR)
                return "Interrupted."
                
            iteration += 1
            self._log(f"--- Iteration {iteration}/{self.max_iterations} ---")
            self._set_state(AgentState.THINKING)
            
            try:
                # Call LLM via standard API
                response = self.llm_client.client.chat.completions.create(
                    model=self.llm_client.model_name,
                    messages=messages,
                    tools=TOOLS_SCHEMA,
                    temperature=0.7,
                )
                
                message = response.choices[0].message
                
                # Log thought process if any
                if message.content:
                    self._log(f"Agent Thought:\n{message.content}")
                    final_answer = message.content # Keep updating final answer
                    
                # Check for tool calls
                if message.tool_calls:
                    self._set_state(AgentState.ACTING)
                    
                    # Append assistant's tool calls to context
                    assistant_msg = {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            } for tc in message.tool_calls
                        ]
                    }
                    messages.append(assistant_msg)
                    
                    for tc in message.tool_calls:
                        func_name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {}
                            
                        self._log(f"Executing Tool: {func_name}")
                        
                        # Execute Tool
                        result_str = execute_tool(func_name, args, security_callback)
                        
                        self._set_state(AgentState.OBSERVING)
                        
                        # Truncate output for log UI to avoid freezing
                        log_out = result_str
                        if len(log_out) > 500:
                            log_out = log_out[:500] + "... (truncated)"
                        self._log(f"Tool Output:\n{log_out}")
                        
                        # Append observation to context
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str
                        })
                        
                    # Loop back to THINKING with the new context
                    continue 
                else:
                    # No tool calls means the agent is done
                    self._log("Task completed successfully.")
                    self._set_state(AgentState.COMPLETED)
                    # Append final answer to messages to save it in memory if needed
                    messages.append({"role": "assistant", "content": final_answer})
                    return final_answer
                    
            except Exception as e:
                self._log(f"Error during iteration: {str(e)}")
                self._set_state(AgentState.ERROR)
                return f"Error: {str(e)}"
                
        self._log("Max iterations reached without completion.")
        self._set_state(AgentState.ERROR)
        return final_answer + "\n[Warning: Task terminated because max iterations were reached.]"
