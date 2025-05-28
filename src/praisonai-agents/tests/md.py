from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("sample.txt")
print(result.text_content)