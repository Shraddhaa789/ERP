import re

with open(r'd:\enterprise resource\app.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'DELETE FROM' in line.upper():
            print(f"Line {i+1}: {line.strip()}")
