import psycopg2

def get_conn():
    return psycopg2.connect(
        host="localhost",
        database="construction_erp",
        user="postgres",
        password="pass123"
    )

def create_basic_info_table():
    """Create basic_info table with all INWARD_FIELD_ORDER columns"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Drop existing table if it exists to start fresh
        cur.execute("DROP TABLE IF EXISTS basic_info")
        print("Dropped existing basic_info table")
        
        # Create table with all columns from INWARD_FIELD_ORDER
        create_table_sql = """
        CREATE TABLE basic_info (
            id SERIAL PRIMARY KEY,
            sr_no TEXT,
            atn TEXT,
            shifting TEXT,
            original_wh TEXT,
            date DATE,
            warehouse TEXT,
            shipment_type TEXT,
            dispatch_type TEXT,
            in_doc_no TEXT,
            order_no TEXT,
            dc_no TEXT,
            challan_date DATE,
            oem TEXT,
            po_no TEXT,
            po_name TEXT,
            invoice_no TEXT,
            invoice_date DATE,
            item_code TEXT,
            description TEXT,
            qty TEXT,
            physical_qty TEXT,
            unit TEXT,
            rate TEXT,
            total_value TEXT,
            taxable_value TEXT,
            tsc TEXT,
            discount TEXT,
            freight TEXT,
            additional_total TEXT,
            cgst TEXT,
            sgst TEXT,
            grand_total TEXT,
            unloading TEXT,
            transport TEXT,
            vehicle TEXT,
            lr_no TEXT,
            lr_date DATE,
            pkgs_qty TEXT,
            delivery_date DATE,
            mode TEXT,
            reporting_time TEXT,
            unloading_time TEXT,
            wh_remark TEXT,
            eway_bill TEXT,
            shipment_type2 TEXT,
            inspection_date DATE,
            inspection_person TEXT,
            doc_remark TEXT,
            pm_update_date DATE,
            pm_update_by TEXT,
            reupload TEXT,
            reupload_reason TEXT,
            pm_remark TEXT,
            inspection_status TEXT,
            pm_submit_date DATE,
            approved_dpm DATE,
            approved_tpa DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        cur.execute(create_table_sql)
        conn.commit()
        print("Successfully created basic_info table with all 57 columns!")
        
        # Show table structure
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'basic_info' 
            ORDER BY ordinal_position
        """)
        
        columns = cur.fetchall()
        print(f"\nTable structure (total columns: {len(columns)}):")
        for col in columns:
            print(f"  {col[0]}: {col[1]}")
            
    except Exception as e:
        conn.rollback()
        print(f"Error creating basic_info table: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def main():
    try:
        print("Creating basic_info table with all INWARD_FIELD_ORDER columns...")
        create_basic_info_table()
        print("Table creation completed successfully!")
        
    except Exception as e:
        print(f"Error during table creation: {e}")
        raise

if __name__ == "__main__":
    main()
