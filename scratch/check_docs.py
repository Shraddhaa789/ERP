import psycopg2
import os

try:
    conn = psycopg2.connect(
        host="localhost",
        database="construction_erp",
        user="postgres",
        password="pass123"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents;")
    doc_count = cur.fetchone()[0]
    print(f"Document count: {doc_count}")
    
    cur.execute("SELECT * FROM documents;")
    docs = cur.fetchall()
    print("Documents:")
    for doc in docs:
        print(doc)
        
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
