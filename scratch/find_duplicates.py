import re

with open(r'd:\enterprise resource\app.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'def delete_survey' in line:
            print(f"Line {i+1}: {line.strip()}")
