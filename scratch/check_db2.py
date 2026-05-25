import psycopg2
import json

conn = psycopg2.connect(
    host="localhost",
    database="construction_erp",
    user="postgres",
    password="pass123",
    port=5432
)
cur = conn.cursor()
cur.execute("SELECT id, user_id, photo_path, captured_at FROM survey_submissions ORDER BY id DESC LIMIT 5")
rows = cur.fetchall()
print("Recent survey submissions:")
for row in rows:
    print(row)

cur.execute("SELECT survey_id, category, quantity FROM survey_material_items ORDER BY id DESC LIMIT 5")
items = cur.fetchall()
print("\nRecent survey materials:")
for item in items:
    print(item)
    
conn.close()
