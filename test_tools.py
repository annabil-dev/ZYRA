import os
import sys

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ai.inference.local_llm_client import LocalLLMGenerator

def test_tool_calling():
    # Use qwen2.5:32b or llama3.1
    # We will assume Llama 3.1 is available since it's the default in the code.
    generator = LocalLLMGenerator(model_name="llama3.1")
    
    prompt = "Tolong kasih tau gua apa isi dari file D:\\Semester 5\\AI\\my_ai\\publish\\version.json"
    print(f"User: {prompt}")
    print("AI: ", end="", flush=True)
    
    for full_text, delta, metrics in generator.generate(prompt=prompt, max_tokens=1024):
        print(delta, end="", flush=True)
        
    print("\n--- DONE ---")

if __name__ == "__main__":
    test_tool_calling()
