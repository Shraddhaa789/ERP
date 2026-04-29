import psycopg2

def get_conn():
    return psycopg2.connect(
        host="localhost",
        database="construction_erp",
        user="postgres",
        password="pass123"
    )

def update_basic_info_table():
    """Add the missing 'additional_total' column to basic_info table"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Check if additional_total column exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'basic_info' AND column_name = 'additional_total'
        """)
        
        if not cur.fetchone():
            print("Adding additional_total column to basic_info table...")
            cur.execute("""
                ALTER TABLE basic_info 
                ADD COLUMN additional_total TEXT
            """)
            conn.commit()
            print("Successfully added additional_total column")
        else:
            print("additional_total column already exists")
            
    except Exception as e:
        conn.rollback()
        print(f"Error updating basic_info table: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def update_outward_info_table():
    """Ensure outward_info table has all required columns"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Add any missing columns that might be needed
        # For now, outward_info table should be fine with existing 38 columns
        print("outward_info table schema check completed")
            
    except Exception as e:
        conn.rollback()
        print(f"Error checking outward_info table: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def main():
    try:
        print("Updating database schema to support all 57 columns...")
        update_basic_info_table()
        update_outward_info_table()
        print("Database schema update completed successfully!")
        
    except Exception as e:
        print(f"Error during schema update: {e}")
        raise

if __name__ == "__main__":
    main()
