with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'port = int(os.environ.get("PORT", 5000))'
new = 'port = int(os.environ.get("PORT", 8080))'

content = content.replace(old, new)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK - port set to 8080")
