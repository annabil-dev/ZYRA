import sys
import os

libs_dir_local = os.path.join(os.path.dirname(os.path.dirname(__file__)), "libs")
if os.path.exists(libs_dir_local) and libs_dir_local not in sys.path:
    sys.path.insert(0, libs_dir_local)

if getattr(sys, 'frozen', False):
    libs_dir_bundled = os.path.join(sys._MEIPASS, "app", "libs")
    if libs_dir_bundled not in sys.path:
        sys.path.insert(1, libs_dir_bundled)

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
