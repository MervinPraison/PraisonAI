#!/bin/bash

# Check the first argument provided to the script for platform selection
if [ "$1" = "groq" ]; then
  # Check for a second argument for the model name, default to mixtral-8x7b-32768 if not provided
  MODEL_NAME=${2:-mixtral-8x7b-32768}
  # Set environment variables for Groq configuration with dynamic model name
  export OPENAI_MODEL_NAME=$MODEL_NAME
  export OPENAI_API_BASE=https://api.groq.com/openai/v1
  export OPENAI_API_KEY=$(echo $GROQ_API_KEY)
  echo "Groq configuration initiated with model $MODEL_NAME."
elif [ "$1" = "openai" ] || [ -z "$1" ]; then
  # Check for a second argument for the model name, default to gpt-3.5-turbo if not provided
  MODEL_NAME=${2:-gpt-3.5-turbo}
  # Set environment variables for OpenAI configuration with dynamic model name
  export OPENAI_MODEL_NAME=$MODEL_NAME
  export OPENAI_API_BASE=https://api.openai.com/v1
  export OPENAI_API_KEY=$(echo $OAI_API_KEY)
  echo "OpenAI configuration initiated with model $MODEL_NAME."
fi
