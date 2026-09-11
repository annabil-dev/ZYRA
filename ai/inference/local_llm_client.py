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
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_k: int = 40,
        top_p: float = 0.9,
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
            
        messages.append({"role": "user", "content": prompt})
        
        start_time = time.time()
        generated_text = ""
        token_count = 0
        
        try:
            # We MUST stream the response. For a 70B model offloaded to RAM, 
            # waiting for the entire response would trigger timeouts and degrade UX.
            response_stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=True,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                # Extra params for llama.cpp compatible backends
                extra_body={"top_k": top_k}
            )
            
            for chunk in response_stream:
                if self.is_interrupted:
                    self.logger.info("Generation interrupted by user.")
                    break
                    
                delta_content = chunk.choices[0].delta.content
                if delta_content:
                    generated_text += delta_content
                    token_count += 1
                    
                    dt = max(time.time() - start_time, 0.001)
                    tok_per_sec = token_count / dt
                    
                    # VRAM metrics for Ollama are typically opaque at the generation call layer,
                    # but we cap our assumptions at the 8GB limit we have strictly allocated.
                    metrics = {
                        "latency_ms": dt * 1000,
                        "tokens_per_sec": tok_per_sec,
                        "vram_mb": 8192.0 # Assume strict 8GB maximization
                    }
                    
                    # Yield: full_text, delta_text, metrics
                    yield generated_text, delta_content, metrics
                    
        except APITimeoutError as e:
            error_msg = f"Timeout Error: Engine took too long to respond. (TTFT > {self.timeout_settings.read}s)"
            self.logger.error(error_msg)
            yield generated_text + f"\n[ERROR: {error_msg}]", f"\n[ERROR: {error_msg}]", {"latency_ms": 0, "tokens_per_sec": 0, "vram_mb": 0}
            
        except APIConnectionError as e:
            error_msg = f"Connection Error: Could not connect to {self.base_url}. Is Ollama/llama.cpp running?"
            self.logger.error(error_msg)
            yield f"[ERROR: {error_msg}]", f"[ERROR: {error_msg}]", {"latency_ms": 0, "tokens_per_sec": 0, "vram_mb": 0}
            
        except Exception as e:
            self.logger.error(f"Unexpected inference error: {str(e)}")
            yield generated_text + f"\n[ERROR: {str(e)}]", f"\n[ERROR: {str(e)}]", {"latency_ms": 0, "tokens_per_sec": 0, "vram_mb": 0}
