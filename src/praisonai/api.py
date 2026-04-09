from flask import Flask
import markdown

app = Flask(__name__)

try:
    import nh3
    def _sanitize_html(html: str) -> str:
        """Sanitize HTML to prevent XSS from markdown-generated content."""
        return nh3.clean(html)
except ImportError:
    def _sanitize_html(html_str: str) -> str:
        """Fallback: no nh3, return escaped HTML. Install nh3 for rich HTML rendering."""
        import html
        return html.escape(html_str)

def basic():
    from praisonai import PraisonAI
    praisonai = PraisonAI(agent_file="agents.yaml")
    return praisonai.run()

@app.route('/')
def home():
    output = basic()
    html_output = _sanitize_html(markdown.markdown(str(output)))
    return f'<html><body>{html_output}</body></html>'

if __name__ == "__main__":
    app.run(debug=False)
