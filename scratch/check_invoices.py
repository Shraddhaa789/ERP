import os
import psycopg2

def get_conn():
    # Let's check the database connection config from app.py
    # We will read db connection settings using psycopg2
    # In app.py, get_conn() probably uses a local postgres db
    return psycopg2.connect(
        dbname="construction_erp",
        user="postgres",
        password="pass123",
        host="127.0.0.1",
        port=5432
    )

try:
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("SELECT id, invoice_no, dc_no FROM basic_info WHERE invoice_no IS NOT NULL LIMIT 20")
    print("INWARD INVOICES:")
    for row in cur.fetchall():
        print(f"ID: {row[0]}, Invoice: {row[1]}, DC: {row[2]}")
        
    cur.execute("SELECT id, out_dc_no, out_in_doc_no FROM outward_info LIMIT 20")
    print("\nOUTWARD INVOICES:")
    for row in cur.fetchall():
        print(f"ID: {row[0]}, Out DC: {row[1]}, Out In Doc: {row[2]}")
        
    cur.close()
    conn.close()
except Exception as e:
    print("Error:", e)
