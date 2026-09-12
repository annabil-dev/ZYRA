import sys
import os

# Ensure bundled libs are available
if getattr(sys, 'frozen', False):
    libs_dir = os.path.join(sys._MEIPASS, "app", "libs")
    if libs_dir not in sys.path:
        sys.path.insert(0, libs_dir)
else:
    libs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "libs")
    if libs_dir not in sys.path:
        sys.path.insert(0, libs_dir)

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

def search_web(query: str, max_results: int = 3) -> str:
    """Searches the web using duckduckgo and returns a formatted string of results."""
    if DDGS is None:
        return "Web search is currently unavailable (library missing)."
        
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=max_results)
        
        if not results:
            return "No web search results found."
            
        context_parts = []
        for i, res in enumerate(results):
            title = res.get('title', 'Unknown Title')
            href = res.get('href', 'Unknown URL')
            body = res.get('body', 'No snippet available')
            context_parts.append(f"Source {i+1}: {title}\nURL: {href}\nContent: {body}")
            
        return "\n\n".join(context_parts)
    except Exception as e:
        return f"Web search failed: {str(e)}"
