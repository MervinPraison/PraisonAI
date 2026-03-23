import html as html_module
import os

from flask import Flask
import markdown

app = Flask(__name__)

try:
    import nh3
    def _sanitize_html(raw_html: str) -> str:
        """Sanitize HTML to prevent XSS from markdown-generated content."""
        return nh3.clean(raw_html)
except ImportError:
    def _sanitize_html(raw_html: str) -> str:
        """Fallback: no nh3, escape HTML to prevent XSS."""
        return html_module.escape(raw_html)

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
    app.run(debug=os.environ.get("DEBUG", "false").lower() == "true")
