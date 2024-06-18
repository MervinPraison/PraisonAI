# PraisonAI User Interface (UI)

## Chainlit
```bash
pip install "praisonai[ui]"
export OPENAI_API_KEY="Enter your API key"
chainlit create-secret
export CHAINLIT_AUTH_SECRET=xxxxxxxx
praisonai ui
```

Default Username: admin
Default Password: admin

### To Change Username and Password

create .env file in the root folder of the project
Add below Variables and required Username/Password
```
CHAINLIT_USERNAME=admin
CHAINLIT_USERNAME=admin
```

## Gradio
```bash
pip install "praisonai[gradio]"
export OPENAI_API_KEY="Enter your API key"
praisonai --ui gradio
```

## Streamlit

```
git clone https://github.com/leporejoseph/PraisonAi-Streamlit
cd PraisonAi-Streamlit
pip install -r requirements.txt
streamlit run app.py
```