import os
import sys

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from app.ui.chat_bubble import highlight_universal_code, parse_simple_markdown

def test():
    # Test JS highlight
    js_code = """
    function greet(name) {
        console.log(`Hello ${name}`);
        return true;
    }
    """
    html_js = highlight_universal_code(js_code, "javascript")
    print("--- JS HTML ---")
    print(html_js)
    
    # Test markdown lists
    md_text = """
    Berikut adalah daftarnya:
    - Item pertama
    - Item kedua
    - Item ketiga
    
    Dan teks biasa lagi.
    """
    html_md = parse_simple_markdown(md_text)
    print("--- MD HTML ---")
    print(html_md)

if __name__ == "__main__":
    test()
