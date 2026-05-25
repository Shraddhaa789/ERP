import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        database="construction_erp",
        user="postgres",
        password="pass123"
    )
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'documents';")
    cols = [r[0] for r in cur.fetchall()]
    print(f"Columns in 'documents': {cols}")
    
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'work_uploads';")
    cols = [r[0] for r in cur.fetchall()]
    print(f"Columns in 'work_uploads': {cols}")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
