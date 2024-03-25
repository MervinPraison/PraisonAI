# api.py
from flask import Flask
from praisonai import PraisonAI

app = Flask(__name__)

def basic():
    praison_ai = PraisonAI(agent_file="agents.yaml")
    return praison_ai.main()

@app.route('/')
def home():
    basic()
    return basic()

if __name__ == "__main__":
    app.run(debug=True)