response_text = '   '
old_result = response_text and response_text.strip() and len(response_text.strip()) > 10
new_result = response_text and len(response_text.strip()) > 10
print('Old result:', old_result)
print('New result:', new_result)
print('response_text:', repr(response_text))
print('response_text.strip():', repr(response_text.strip()))
print('len(response_text.strip()):', len(response_text.strip()))
print('len(response_text.strip()) > 10:', len(response_text.strip()) > 10)