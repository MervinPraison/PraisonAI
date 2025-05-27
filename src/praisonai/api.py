from flask import Flask
from praisonai import PraisonAI
import markdown

app = Flask(__name__)

def basic():
    praisonai = PraisonAI(agent_file="agents.yaml")
    return praisonai.run()

@app.route('/')
def home():
    output = basic()
    html_output = markdown.markdown(output)
    return f'<html><body>{html_output}</body></html>'

if __name__ == "__main__":
    app.run(debug=True)
