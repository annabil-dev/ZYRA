from PySide6.QtCore import QThread, Signal
import traceback
import logging
import threading
import json

class InferenceWorker(QThread):
    """
    Background worker for generating text without blocking the UI.
    """
    token_generated = Signal(str, str) # full_text, delta_text
    metrics_updated = Signal(float, float, float) # latency_ms, tokens_per_sec, vram_mb
    generation_finished = Signal()
    generation_error = Signal(str)
    
    # New signal for Agentic Write & Execute security popup
    # Emits (tool_name, arguments_json_string)
    security_check_requested = Signal(str, str)

    def __init__(self, generator, prompt: str, history: list, max_tokens: int, temperature: float, top_k: int, top_p: float, image_paths: list = None):
        super().__init__()
        self.generator = generator
        self.prompt = prompt
        self.history = history
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self.image_paths = image_paths or []
        
        self.security_event = threading.Event()
        self.security_response = False
        
        self.logger = logging.getLogger("inference.worker")

    def set_security_response(self, allow: bool):
        """Called by the UI thread to unblock the worker with the user's decision."""
        self.security_response = allow
        self.security_event.set()

    def run(self):
        import time
        try:
            last_emit_time = time.time()
            delta_buffer = ""
            
            # Security callback passed to execute_tool via generator
            def _security_callback(tool_name, arguments_dict):
                self.security_event.clear()
                self.security_response = False
                # Emit to UI Thread
                self.security_check_requested.emit(tool_name, json.dumps(arguments_dict))
                # Block this worker thread until UI calls set_security_response
                self.security_event.wait()
                return self.security_response
            
            import inspect
            sig = inspect.signature(self.generator.generate)
            kwargs = {
                "prompt": self.prompt,
                "history": self.history,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_k": self.top_k,
                "top_p": self.top_p
            }
            if "image_paths" in sig.parameters:
                kwargs["image_paths"] = self.image_paths
                
            if "security_callback" in sig.parameters:
                kwargs["security_callback"] = _security_callback
                
            for text, delta, metrics in self.generator.generate(**kwargs):
                delta_buffer += delta
                current_time = time.time()
                
                # Emit every ~40ms to avoid flooding UI thread (causes stuttering)
                if current_time - last_emit_time > 0.04:
                    self.token_generated.emit(text, delta_buffer)
                    self.metrics_updated.emit(
                        metrics.get("latency_ms", 0.0),
                        metrics.get("tokens_per_sec", 0.0),
                        metrics.get("vram_mb", 0.0)
                    )
                    delta_buffer = ""
                    last_emit_time = current_time
            
            # Emit any remaining text in buffer at the end
            if delta_buffer:
                self.token_generated.emit(text, delta_buffer)
                
            self.generation_finished.emit()
            
        except Exception as e:
            self.logger.error(f"Generation error: {e}")
            self.logger.error(traceback.format_exc())
            self.generation_error.emit(str(e))

    def stop(self):
        """Signals the generator to stop."""
        if self.generator:
            self.generator.interrupt()
