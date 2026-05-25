import psycopg2
from psycopg2 import pool

db_pool = psycopg2.pool.SimpleConnectionPool(
    1, 1,
    host="localhost",
    database="construction_erp",
    user="postgres",
    password="pass123"
)

conn = db_pool.getconn()
cur = conn.cursor()

cur.execute("SELECT id, user_id, warehouse_name, photo_path, captured_at FROM survey_submissions ORDER BY id DESC LIMIT 10;")
rows = cur.fetchall()

print("ID | User | Warehouse | Photo Path | Captured At")
print("-" * 60)
for row in rows:
    print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]}")

cur.close()
db_pool.putconn(conn)
db_pool.closeall()
