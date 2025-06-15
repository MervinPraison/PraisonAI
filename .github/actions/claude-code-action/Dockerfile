FROM node:20-alpine

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"] 