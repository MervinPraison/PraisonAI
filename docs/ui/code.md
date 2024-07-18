# PraisonAI Code

PraisonAI Code helps you to interact with your whole codebase using the power of AI.

## Different User Interfaces:

| Interface | Description | URL |
|---|---|---|
| **UI** | Multi Agents such as CrewAI or AutoGen | [https://docs.praison.ai/ui/ui](https://docs.praison.ai/ui/ui) |
| **Chat** | Chat with 100+ LLMs, single AI Agent | [https://docs.praison.ai/ui/chat](https://docs.praison.ai/ui/chat) |
| **Code** | Chat with entire Codebase, single AI Agent | [https://docs.praison.ai/ui/code](https://docs.praison.ai/ui/code) |

1. 
```bash
pip install "praisonai[code]"
```

2. 
```bash
export OPENAI_API_KEY=xxxxxxxx
```

3. 
```bash
praisonai code
```

4. Username and Password will be asked for the first time. `admin` is the default username and password.

5. Set Model name to be gpt-3.5-turbo in the settings 


## Other Models

* Use 100+ LLMs
* Includes Gemini 1.5 for 2 Million Context Length

## To Use Gemini 1.5

* ```export GEMINI_API_KEY=xxxxxxxxx```
* ```praisonai code```
* Set Model name to be ```gemini/gemini-1.5-flash``` in the settings

## Ignore Files

### Using settings.yaml

* Create a settings.yaml file in the root folder of the project
* Add below Variables and required Ignore Files

```yaml
code:
  ignore_files:
  - ".*"
  - "*.pyc"
  - "pycache"
  - ".git"
  - ".gitignore"
  - ".vscode"
  - ".idea"
  - ".DS_Store"
  - ".lock"
  - ".pyc"
  - ".env"
```

### Using .env File

* Create a .env file in the root folder of the project
* Add below Variables and required Ignore Files

```bash
PRAISONAI_IGNORE_FILES=".*,*.pyc,__pycache__,.git,.gitignore,.vscode,.idea,.DS_Store,*.lock,.env,docs,tests,test,tmp,temp,*.txt,*.md,*.json,*.csv,*.tsv,public,*.sql,*.sqlite,*.db,*.db3,*.sqlite3,*.log,*.zip,*.gz,*.tar,*.rar,*.7z,*.pdf,*.jpg,*.jpeg,*.png,*.gif,*.svg,cookbooks,assets,dist,build,node_modules,venv,crewAI,.cache,*.__pycache__,*chroma.sqlite3,test/,dist/,praisonAI.egg-info,test.yaml,db,praisonai_prompt.txt,watch.sh,docs.sh,other,output,*.chainlit,.files,site,flagged,*public,threads.db,trained_agents_data.pkl,.pytest_cache"
```

### Using Environment Variables in the Terminal

```bash
export PRAISONAI_IGNORE_FILES=".*,*.pyc,__pycache__,.git,.gitignore,.vscode,.idea,.DS_Store,*.lock,.env,docs,tests,test,tmp,temp,*.txt,*.md,*.json,*.csv,*.tsv,public,*.sql,*.sqlite,*.db,*.db3,*.sqlite3,*.log,*.zip,*.gz,*.tar,*.rar,*.7z,*.pdf,*.jpg,*.jpeg,*.png,*.gif,*.svg,cookbooks,assets,dist,build,node_modules,venv,crewAI,.cache,*.__pycache__,*chroma.sqlite3,test/,dist/,praisonAI.egg-info,test.yaml,db,praisonai_prompt.txt,watch.sh,docs.sh,other,output,*.chainlit,.files,site,flagged,*public,threads.db,trained_agents_data.pkl,.pytest_cache"
```

## Set Max Tokens

Note: By Default Max Tokens set is 128,000

```bash
export PRAISONAI_MAX_TOKENS=200000
```

or 

* Create a .env file in the root folder of the project
* Add below Variables and required Max Tokens
* ```
  PRAISONAI_MAX_TOKENS=200000
  ```