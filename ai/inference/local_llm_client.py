import time
import logging
from typing import Dict, Any, Generator, Tuple
import httpx
from openai import OpenAI, APIConnectionError, APITimeoutError

class LocalLLMGenerator:
    """
    Handles text generation by offloading to a local Ollama/llama.cpp engine
    using GGUF format for optimal split across 8GB VRAM and 64GB System RAM.
    """
    def __init__(
        self, 
        base_url: str = "http://localhost:11434/v1", 
        model_name: str = "llama3.1:70b-instruct-q4_K_M"
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.logger = logging.getLogger("inference.local_llm")
        self.is_interrupted = False
        
        # 70B parameters heavily offloaded to 64GB RAM means slower token generation.
        # Strict handling of HTTP timeouts to prevent freezing.
        # TTFT (Time-to-First-Token) can easily take 10-30 seconds depending on prompt context.
        self.timeout_settings = httpx.Timeout(
            connect=10.0,
            read=300.0, # Generous 5-minute read timeout for long generations or slow TTFT
            write=10.0,
            pool=10.0
        )
        
        self.http_client = httpx.Client(timeout=self.timeout_settings)
        
        # We use the OpenAI client which natively integrates with Ollama/llama.cpp's OpenAI compatible endpoints
        self.client = OpenAI(
            base_url=self.base_url,
            api_key="local-engine", # Required by SDK but ignored by local engine
            http_client=self.http_client,
            max_retries=0
        )
        
        self.logger.info(f"Initialized Local LLM Client. Endpoint: {self.base_url}, Model: {self.model_name}")

    def interrupt(self):
        """Safely signals the generation loop to stop processing further tokens."""
        self.is_interrupted = True

    def generate(
        self,
        prompt: str,
        history: list = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_k: int = 40,
        top_p: float = 0.9,
        image_paths: list = None
    ) -> Generator[Tuple[str, str, Dict[str, Any]], None, None]:
        
        self.is_interrupted = False
        
        messages = [
            {"role": "system", "content": (
                "Kamu adalah asisten AI lokal yang cerdas, ramah, dan membantu. "
                "Selalu balas menggunakan bahasa yang sama dengan pengguna. "
                "Jika pengguna berbicara bahasa Indonesia, balas dalam bahasa Indonesia. "
                "Jika pengguna berbicara bahasa Inggris, balas dalam bahasa Inggris. "
                "Berikan jawaban yang jelas, ringkas, dan informatif."
            )}
        ]
        
        if history:
            messages.extend(history)
            
        if not image_paths:
            messages.append({"role": "user", "content": prompt})
        else:
            import base64
            content_list = [{"type": "text", "text": prompt}]
            for img_path in image_paths:
                try:
                    with open(img_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        content_list.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_string}"
                            }
                        })
                except Exception as e:
                    self.logger.error(f"Failed to encode image {img_path}: {e}")
            messages.append({"role": "user", "content": content_list})
        
        from app.core.tools import TOOLS_SCHEMA, execute_tool
        import json
        
        start_time = time.time()
        generated_text = ""
        token_count = 0
        
        # Tool execution loop
        MAX_TOOL_CALLS = 5
        tool_call_count = 0
        
        while tool_call_count < MAX_TOOL_CALLS:
            if self.is_interrupted:
                break
                
            try:
                response_stream = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    stream=True,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    tools=TOOLS_SCHEMA,
                    extra_body={"top_k": top_k}
                )
                
                tool_calls_accumulator = {}
                is_calling_tool = False
                
                for chunk in response_stream:
                    if self.is_interrupted:
                        self.logger.info("Generation interrupted by user.")
                        break
                        
                    delta = chunk.choices[0].delta
                    
                    # Accumulate tool calls if present
                    if getattr(delta, 'tool_calls', None):
                        is_calling_tool = True
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_accumulator:
                                tool_calls_accumulator[idx] = {
                                    "id": tc.id or "",
                                    "type": "function",
                                    "function": {"name": tc.function.name or "", "arguments": tc.function.arguments or ""}
                                }
                            else:
                                if tc.id: tool_calls_accumulator[idx]["id"] = tc.id
                                if tc.function.name: tool_calls_accumulator[idx]["function"]["name"] += tc.function.name
                                if tc.function.arguments: tool_calls_accumulator[idx]["function"]["arguments"] += tc.function.arguments
                        continue
                    
                    # Normal text streaming
                    delta_content = delta.content
                    if delta_content and not is_calling_tool:
                        generated_text += delta_content
                        token_count += 1
                        
                        dt = max(time.time() - start_time, 0.001)
                        tok_per_sec = token_count / dt
                        
                        metrics = {
                            "latency_ms": dt * 1000,
                            "tokens_per_sec": tok_per_sec,
                            "vram_mb": 8192.0
                        }
                        
                        yield generated_text, delta_content, metrics
                        
                # Handle tool execution if tools were called
                if is_calling_tool and tool_calls_accumulator:
                    # Notify UI that a tool is being called
                    tool_names = [tc["function"]["name"] for tc in tool_calls_accumulator.values()]
                    ui_notify = f"\n*[Calling tools: {', '.join(tool_names)}]*\n"
                    generated_text += ui_notify
                    yield generated_text, ui_notify, {"latency_ms": 0, "tokens_per_sec": 0, "vram_mb": 8192.0}
                    
                    # Append assistant's tool calls to messages
                    assistant_message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": tc["function"]["arguments"]
                                }
                            }
                            for tc in tool_calls_accumulator.values()
                        ]
                    }
                    messages.append(assistant_message)
                    
                    # Execute tools and append results
                    for tc in tool_calls_accumulator.values():
                        func_name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                            
                        self.logger.info(f"Executing tool: {func_name} with args: {args}")
                        result_str = execute_tool(func_name, args)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_str
                        })
                        
                    tool_call_count += 1
                    continue # Loop back to API with the new messages
                    
                # If no tools were called and stream finished normally, break the loop
                break
                    
            except APITimeoutError as e:
                error_msg = f"Timeout Error: Engine took too long to respond. (TTFT > {self.timeout_settings.read}s)"
                self.logger.error(error_msg)
                yield generated_text + f"\n[ERROR: {error_msg}]", f"\n[ERROR: {error_msg}]", {"latency_ms": 0, "tokens_per_sec": 0, "vram_mb": 0}
                break
                
            except APIConnectionError as e:
                error_msg = f"Connection Error: Could not connect to {self.base_url}. Is Ollama/llama.cpp running?"
                self.logger.error(error_msg)
                yield f"[ERROR: {error_msg}]", f"[ERROR: {error_msg}]", {"latency_ms": 0, "tokens_per_sec": 0, "vram_mb": 0}
                break
                
            except Exception as e:
                self.logger.error(f"Unexpected inference error: {str(e)}")
                yield generated_text + f"\n[ERROR: {str(e)}]", f"\n[ERROR: {str(e)}]", {"latency_ms": 0, "tokens_per_sec": 0, "vram_mb": 0}
                break
