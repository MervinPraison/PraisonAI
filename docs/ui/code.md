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

5. Set Model name to be gpt-4o-mini in the settings 


## Other Models

* Use 100+ LLMs - [Litellm](https://litellm.vercel.app/docs/providers)
* Includes Gemini 1.5 for 2 Million Context Length

## To Use Gemini 1.5

* ```export GEMINI_API_KEY=xxxxxxxxx```
* ```praisonai code```
* Set Model name to be ```gemini/gemini-1.5-flash``` in the settings

## Ignore Files

### Using .praisonignore

* Create a `.praisonignore` file in the root folder of the project
* Add files to ignore

```bash
.*
*.pyc
pycache
.git
.gitignore
.vscode
.idea
.DS_Store
.lock
.pyc
.env
```

### Using settings.yaml (.praisonignore is preferred)

* Create a `settings.yaml` file in the root folder of the project
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

* Create a `.env` file in the root folder of the project
* Add below Variables and required Ignore Files

```bash
PRAISONAI_IGNORE_FILES=".*,*.pyc,__pycache__,.git,.gitignore,.vscode"
```

### Using Environment Variables in the Terminal

```bash
export PRAISONAI_IGNORE_FILES=".*,*.pyc,__pycache__,.git,.gitignore,.vscode"
```

## Include Files

- Add files you wish to Include files in the context
- This will automatically ignore all the ignore files option
- This will include only the files/folders mentioned in `.praisoninclude` to the context

* Create a `.praisoninclude` file in the root folder of the project
* Add files to Include

```bash
projectfiles
docs
```

## Set Max Tokens

Note: By Default Max Tokens set is 900,000

```bash
export PRAISONAI_MAX_TOKENS=1000000
```

or 

* Create a .env file in the root folder of the project
* Add below Variables and required Max Tokens
* ```
  PRAISONAI_MAX_TOKENS=1000000
  ```