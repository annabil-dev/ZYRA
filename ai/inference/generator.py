import time
import threading
import logging
from typing import Dict, Any, Generator, Tuple
from transformers import TextIteratorStreamer, AutoModelForCausalLM, AutoTokenizer
import torch

class TextGenerator:
    """
    Handles text generation using HuggingFace Transformers.
    """
    def __init__(self, model: AutoModelForCausalLM, tokenizer: AutoTokenizer, device: torch.device):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.logger = logging.getLogger("inference.generator")
        
        self.is_interrupted = False

    def interrupt(self):
        """Safely signals the generation loop to stop."""
        self.is_interrupted = True

    def generate(
        self,
        prompt: str,
        max_tokens: int = 50,
        temperature: float = 0.8,
        top_k: int = 40,
        top_p: float = 0.9,
    ) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        
        self.is_interrupted = False
        
        messages = [
            {"role": "system", "content": "Anda adalah asisten AI berbahasa Indonesia yang cerdas dan ramah. Anda harus selalu merespons menggunakan bahasa Indonesia."},
            {"role": "user", "content": prompt},
        ]
        
        try:
            input_text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            input_text = f"User: {prompt}\nAI:"
            
        inputs = self.tokenizer([input_text], return_tensors="pt").to(self.device)
        
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=max_tokens,
            temperature=max(temperature, 0.01),
            top_k=top_k,
            top_p=top_p,
            do_sample=True if temperature > 0 else False,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        thread = threading.Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()
        
        generated_text = ""
        start_time = time.time()
        
        for new_text in streamer:
            if self.is_interrupted:
                self.logger.info("Generation interrupted by user.")
                break
                
            generated_text += new_text
            
            dt = max(time.time() - start_time, 0.001)
            tok_per_sec = len(self.tokenizer.encode(generated_text)) / dt
            
            vram_alloc_mb = 0
            if self.device.type == "cuda":
                vram_alloc_mb = torch.cuda.memory_allocated() / (1024**2)
                
            metrics = {
                "latency_ms": dt * 1000,
                "tokens_per_sec": tok_per_sec,
                "vram_mb": vram_alloc_mb
            }
            
            yield generated_text, metrics
