import os
import sys

# Add root folder to sys.path to import app.py
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from app import find_matching_report_entries, compact_match_value, document_match_tokens

# Let's mock a database query or run against the actual db if connection works
import psycopg2
def get_conn():
    return psycopg2.connect(
        dbname="construction_erp",
        user="postgres",
        password="pass123",
        host="127.0.0.1",
        port=5432
    )

# Let's insert a dummy entry with invoice number 'C122/2324/12059' in basic_info
conn = get_conn()
cur = conn.cursor()
try:
    cur.execute("SELECT id, invoice_no FROM basic_info WHERE invoice_no LIKE '%C122%'")
    rows = cur.fetchall()
    print("Existing matching basic_info rows:", rows)
    
    # If no rows, insert a test row
    if not rows:
        print("No matching rows, inserting a dummy one...")
        cur.execute(
            """
            INSERT INTO basic_info (
                invoice_no, invoice_date, dc_no, order_no, in_doc_no, item_code, oem, warehouse, description, quantity, remarks
            ) VALUES (
                'C122/2324/12059', '2026-05-19', 'DC-999', 'ORD-999', 'IND-999', 'ITEM-999', 'OEM-999', 'PUNE YARD', 'Test matched item', 100, 'Test'
            ) RETURNING id
            """
        )
        dummy_id = cur.fetchone()[0]
        conn.commit()
        print(f"Inserted dummy row with ID: {dummy_id}")
    else:
        dummy_id = rows[0][0]
        
    # Let's run matching for 'C122232412059.pdf'
    filename = "C122232412059.pdf"
    scanned_text = filename
    print(f"\nTesting match for filename: '{filename}'")
    matched_ids, matched_terms = find_matching_report_entries("inward", scanned_text)
    print("Matched IDs:", matched_ids)
    print("Matched terms:", matched_terms)
    
    # Clean up dummy if we inserted it
    if not rows:
        cur.execute("DELETE FROM basic_info WHERE id = %s", (dummy_id,))
        conn.commit()
        print("Deleted dummy row.")
        
finally:
    cur.close()
    conn.close()
