"""Live interactive mode smoke tests.

These tests verify PraisonAI's interactive mode using real API calls.
Tests use HeadlessInteractiveCore to execute prompts through the same
pipeline as the interactive TUI.

Environment variables:
- PRAISONAI_LIVE_INTERACTIVE=1  - Enable live interactive tests
- OPENAI_API_KEY                - Required for live tests
- PRAISONAI_LIVE_MODEL          - Override model (default: gpt-4o-mini)
"""
