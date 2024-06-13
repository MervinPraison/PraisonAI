#!/bin/bash

# Ensure we are in the docs folder
cd "$(dirname "$0")"

# Define the sections and their corresponding filenames
sections=(
  "Praison AI:index.md"
  "TL;DR:tldr.md"
  "Installation:installation.md"
  "Initialise:initialise.md"
  "Run:run.md"
  "Create Custom Tools:create_custom_tools.md"
  "Test:test.md"
  "Agents Playbook:agents_playbook.md"
  "Include praisonai package in your project:include_package.md"
  "Deploy:deploy.md"
  "Other Models:other_models.md"
  "Contributing:contributing.md"
)

# Function to extract section content
extract_section() {
  section_name="$1"
  input_file="$2"
  output_file="$3"
  
  # Escape special characters in section name for use in regex
  section_name_escaped=$(echo "$section_name" | sed 's/[.[\*^$(){}?+|]/\\&/g')
  
  # Extract content
  if command -v gsed > /dev/null; then
    gsed -n "/## $section_name_escaped/,/## /{p;}" "$input_file" | gsed '$d' >> "$output_file"
  else
    sed -n "/## $section_name_escaped/,/## /{p;}" "$input_file" | sed '$d' >> "$output_file"
  fi
}

# Extract content above the first section from README.md
if command -v gsed > /dev/null; then
  gsed -n '1,/^## /{p;}' ../README.md | gsed '$d' > index.md
else
  sed -n '1,/^## /{p;}' ../README.md | sed '$d' > index.md
fi

# Create the files and add content
for section in "${sections[@]}"; do
  section_name="${section%%:*}"
  filename="${section##*:}"
  if [[ "$filename" == "index.md" ]]; then
    extract_section "$section_name" ../README.md index.md
  elif [[ "$section_name" == "TL;DR" ]]; then
    extract_section "$section_name" ../README.md index.md
  else
    extract_section "$section_name" ../README.md "$filename"
  fi
done

# Special handling for the last section (Contributing)
if command -v gsed > /dev/null; then
  gsed -n "/## Contributing/,\$p" ../README.md > "contributing.md"
else
  sed -n "/## Contributing/,\$p" ../README.md > "contributing.md"
fi
