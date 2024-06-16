# PraisonAI User Interface (UI)

## Chainlit
```bash
pip install chainlit
export OPENAI_API_KEY="Enter your API key"
chainlit create-secret
export CHAINLIT_AUTH_SECRET=xxxxxxxx
praisonai --ui chainlit
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
pip install gradio
export OPENAI_API_KEY="Enter your API key"
praisonai --ui gradio
```