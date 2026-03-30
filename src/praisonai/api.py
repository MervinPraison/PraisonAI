from flask import Flask
from markupsafe import escape
import markdown

app = Flask(__name__)

def basic():
    from praisonai import PraisonAI
    praisonai = PraisonAI(agent_file="agents.yaml")
    return praisonai.run()

@app.route('/')
def home():
    output = basic()
    # Convert markdown to HTML, then sanitize the output to prevent XSS
    html_output = markdown.markdown(str(output))
    # Use bleach to sanitize HTML output (allows safe tags only)
    try:
        import bleach
        allowed_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 
                       'strong', 'em', 'code', 'pre', 'blockquote', 'a', 'br', 'hr']
        allowed_attrs = {'a': ['href', 'title']}
        # Strip javascript: URLs from href attributes
        def filter_href(tag, name, value):
            if name == 'href':
                if value.lower().startswith(('javascript:', 'data:', 'vbscript:')):
                    return False
            return True
        html_output = bleach.clean(html_output, tags=allowed_tags, attributes=allowed_attrs, 
                                   strip=True, protocols=['http', 'https', 'mailto'])
    except ImportError:
        # Fallback: escape the entire output if bleach not available
        html_output = str(escape(html_output))
    return f'<html><body>{html_output}</body></html>'

if __name__ == "__main__":
    app.run(debug=True)
