# Legacy root scripts

One-off scripts, demos and old fix-verification `test_*.py` files that used to sit in the package root (G-27). They are kept for reference, not collected by pytest (`testpaths = tests`) and not shipped in the wheel. Many call real LLMs. Move anything still useful into `examples/` or `tests/`.
