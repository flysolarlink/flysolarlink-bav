with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver la dernière ligne avec __main__ et tout couper apres
new_lines = []
for line in lines:
    if '__main__' in line:
        break
    new_lines.append(line)

# Ajouter le bon bloc final
new_lines.append('\nif __name__ == "__main__":\n')
new_lines.append('    import os\n')
new_lines.append('    port = int(os.environ.get("PORT", 5000))\n')
new_lines.append('    app.run(debug=False, host="0.0.0.0", port=port)\n')

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("OK")
