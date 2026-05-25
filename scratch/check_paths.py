import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        database="construction_erp",
        user="postgres",
        password="pass123"
    )
    cur = conn.cursor()
    
    print("--- survey_submissions ---")
    cur.execute("SELECT id, photo_path FROM survey_submissions LIMIT 5;")
    for row in cur.fetchall():
        print(row)
        
    print("\n--- work_uploads ---")
    cur.execute("SELECT id, image_path FROM work_uploads LIMIT 5;")
    for row in cur.fetchall():
        print(row)
        
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
