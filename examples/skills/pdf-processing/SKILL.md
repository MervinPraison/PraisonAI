---
name: pdf-processing
description: Process and extract information from PDF documents. Use this skill when the user asks to read, analyze, or extract data from PDF files.
license: Apache-2.0
compatibility: Works with PraisonAI Agents
metadata:
  author: praisonai
  version: "1.0"
---

# PDF Processing Skill

## Overview

This skill enables agents to process PDF documents, extract text content, and analyze the information within them.

## When to Use

Activate this skill when:
- User asks to read or analyze a PDF file
- User needs to extract text from a PDF
- User wants to summarize a PDF document
- User needs to search for information within a PDF

## Instructions

1. First, verify the PDF file exists at the specified path
2. Use appropriate tools to read the PDF content
3. Extract text while preserving structure where possible
4. For large PDFs, process in chunks to manage context
5. Summarize or analyze based on user's specific request

## Best Practices

- Always confirm the file path before processing
- Handle encrypted PDFs gracefully with appropriate error messages
- For scanned PDFs, note that OCR may be required
- Preserve important formatting like tables and lists
