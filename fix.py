with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "if __name__ == \"__main__\":"
new = "if __name__ == \"__main__\":\n    import os\n    port = int(os.environ.get(\"PORT\", 5000))\n    app.run(debug=False, host=\"0.0.0.0\", port=port)\n    exit()"

content = content.replace(old, new, 1)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK")
