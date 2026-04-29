import pandas as pd
import psycopg2
from datetime import datetime

def get_conn():
    return psycopg2.connect(
        host="localhost",
        database="construction_erp",
        user="postgres",
        password="pass123"
    )

def clear_existing_data():
    """Clear all existing inward and outward data"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute("TRUNCATE TABLE basic_info RESTART IDENTITY")
        cur.execute("TRUNCATE TABLE outward_info RESTART IDENTITY")
        conn.commit()
        print("Successfully cleared existing data")
    except Exception as e:
        conn.rollback()
        print(f"Error clearing data: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def parse_date_value(value):
    """Parse date values in various formats"""
    if pd.isna(value) or value == "":
        return None
    
    if isinstance(value, datetime):
        return value.date()
    
    try:
        return pd.to_datetime(value).date()
    except:
        return None

def safe_str(value):
    """Convert value to string, handle NaN"""
    if pd.isna(value):
        return None
    return str(value) if value != "" else None

def import_inward_data(df):
    """Import inward data using existing database functions"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Find the header row - look for row containing 'Sr NO'
        header_row_idx = None
        for idx, row in df.iterrows():
            if any('Sr NO' in str(cell) for cell in row if pd.notna(cell)):
                header_row_idx = idx
                break
        
        if header_row_idx is None:
            print("Could not find header row in inward data")
            return
        
        # Use the header row and skip rows before it
        df = df.iloc[header_row_idx:].copy()
        df.columns = df.iloc[0]
        df = df.iloc[1:].copy()
        
        # Clean column names
        df.columns = [str(col).strip() for col in df.columns]
        
        print(f"Inward sheet columns after processing: {list(df.columns)}")
        print(f"Inward records to process: {len(df)}")
        
        imported_count = 0
        for index, row in df.iterrows():
            # Skip empty rows
            if pd.isna(row.get('Sr NO')) or str(row.get('Sr NO')).strip() == '':
                continue
            
            # Map Excel columns to database fields using the exact field order from app.py
            # Skip 'Total' column (additional_total) as it's not in database schema
            values = (
                safe_str(row.get('Sr NO')),  # sr_no
                safe_str(row.get('ATN')),  # atn
                safe_str(row.get('Shifting (A-C)')),  # shifting
                safe_str(row.get('Original Warehouse(Invoice/DC)')),  # original_wh
                parse_date_value(row.get('Month')),  # date
                safe_str(row.get('Warehouse')),  # warehouse
                safe_str(row.get('Shipment Type/P ackage - A & C')),  # shipment_type
                safe_str(row.get('Dispatched Type')),  # dispatch_type
                safe_str(row.get('IN. DOC No')),  # in_doc_no
                safe_str(row.get('Order No')),  # order_no
                safe_str(row.get('DC No')),  # dc_no
                parse_date_value(row.get('Challan Date')),  # challan_date
                safe_str(row.get('OEM')),  # oem
                safe_str(row.get('PO NO')),  # po_no (fixed column name)
                safe_str(row.get('PO Issued Name')),  # po_name
                safe_str(row.get('Invoice No.')),  # invoice_no
                parse_date_value(row.get('Invoice Date')),  # invoice_date
                safe_str(row.get('Item Code')),  # item_code
                safe_str(row.get('Description')),  # description
                safe_str(row.get('NO/Qty')),  # qty
                safe_str(row.get('PhysicalNO/Qty')),  # physical_qty
                safe_str(row.get('Unit')),  # unit
                safe_str(row.get('Rate per unit')),  # rate
                safe_str(row.get('Total Value')),  # total_value
                safe_str(row.get('Taxbale Value')),  # taxable_value
                safe_str(row.get('TSC0.075%')),  # tsc
                safe_str(row.get('Discont-2.4(HFCL')),  # discount
                safe_str(row.get('Freight Charges')),  # freight
                safe_str(row.get('CGST (9.00 %)')),  # cgst
                safe_str(row.get('SGST (9.00 %)')),  # sgst
                safe_str(row.get('Grant Total')),  # grand_total
                safe_str(row.get('Chmaber Unoading Charges')),  # unloading
                safe_str(row.get('Transport Name')),  # transport
                safe_str(row.get('Vehicle \nNo')),  # vehicle
                safe_str(row.get('LR/RR NO')),  # lr_no
                parse_date_value(row.get('LR Date')),  # lr_date
                safe_str(row.get('Pkgs Qty')),  # pkgs_qty
                parse_date_value(row.get('Delivery Date')),  # delivery_date
                safe_str(row.get('Mode of Delivery')),  # mode
                safe_str(row.get('Reporting Time')),  # reporting_time
                safe_str(row.get('Unloading Time')),  # unloading_time
                safe_str(row.get('W/H Remark')),  # wh_remark
                safe_str(row.get('e-WAY Bill No')),  # eway_bill
                safe_str(row.get('Shipment Type')),  # shipment_type2
                parse_date_value(row.get('Material Inspection Date/Date of Supply')),  # inspection_date
                safe_str(row.get('Material Inspection Person Name')),  # inspection_person
                safe_str(row.get('Document Remark')),  # doc_remark
                parse_date_value(row.get('PM Tools Update/update_date')),  # pm_update_date
                safe_str(row.get('PM Tools Update By')),  # pm_update_by
                safe_str(row.get('Re- Upload')),  # reupload
                safe_str(row.get('Reason/ Re- Upload')),  # reupload_reason
                safe_str(row.get('Remark')),  # pm_remark
                safe_str(row.get('Inspection Status on PM Tool')),  # inspection_status
                parse_date_value(row.get('PM Tool Submission Date')),  # pm_submit_date
                parse_date_value(row.get('Approved by DPM-Date')),  # approved_dpm
                parse_date_value(row.get('Approved by TPA-Date'))  # approved_tpa
            )
            
            # Verify we have exactly 56 values
            if len(values) != 56:
                print(f"Error: Expected 56 values, got {len(values)} for record {imported_count + 1}")
                continue
            
            # Insert into database using the exact same SQL as in app.py
            cur.execute("""
                INSERT INTO basic_info (
                    sr_no, atn, shifting, original_wh, date, warehouse, shipment_type, dispatch_type,
                    in_doc_no, order_no, dc_no, challan_date,
                    oem, po_no, po_name,
                    invoice_no, invoice_date,
                    item_code, description, qty, physical_qty, unit,
                    rate, total_value, taxable_value,
                    tsc, discount, freight,
                    cgst, sgst, grand_total,
                    unloading, transport, vehicle, lr_no, lr_date,
                    pkgs_qty, delivery_date, mode,
                    reporting_time, unloading_time, wh_remark,
                    eway_bill, shipment_type2,
                    inspection_date, inspection_person,
                    pm_update_date, doc_remark, pm_update_by, reupload, reupload_reason,
                    pm_remark, inspection_status, pm_submit_date,
                    approved_dpm, approved_tpa
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, values)
            imported_count += 1
            
            # Progress indicator
            if imported_count % 1000 == 0:
                print(f"Imported {imported_count} inward records...")
        
        conn.commit()
        print(f"Successfully imported {imported_count} inward records")
        
    except Exception as e:
        conn.rollback()
        print(f"Error importing inward data: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def import_outward_data(df):
    """Import outward data using existing database functions"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Find the header row - look for row containing 'Sr NO'
        header_row_idx = None
        for idx, row in df.iterrows():
            if any('Sr NO' in str(cell) for cell in row if pd.notna(cell)):
                header_row_idx = idx
                break
        
        if header_row_idx is None:
            print("Could not find header row in outward data")
            return
        
        # Use the header row and skip rows before it
        df = df.iloc[header_row_idx:].copy()
        df.columns = df.iloc[0]
        df = df.iloc[1:].copy()
        
        # Clean column names
        df.columns = [str(col).strip() for col in df.columns]
        
        print(f"Outward sheet columns after processing: {list(df.columns)}")
        print(f"Outward records to process: {len(df)}")
        
        imported_count = 0
        for index, row in df.iterrows():
            # Skip empty rows
            if pd.isna(row.get('Sr NO')) or str(row.get('Sr NO')).strip() == '':
                continue
            
            # Map Excel columns to database fields using the exact field order from app.py
            values = (
                safe_str(row.get('Sr NO')),  # out_sr_no
                safe_str(row.get('ATN')),  # out_atn
                parse_date_value(row.get('Month')),  # out_month
                safe_str(row.get('Warehouse')),  # out_warehouse
                safe_str(row.get('Shipment Type')),  # out_shipment_type
                safe_str(row.get('Dispatched Type')),  # out_dispatch_type
                safe_str(row.get('IN. DOC No')),  # out_in_doc_no
                safe_str(row.get('DC No')),  # out_dc_no
                parse_date_value(row.get('DC Date')),  # out_dc_date
                safe_str(row.get('Vendor Name')),  # out_vendor_name
                safe_str(row.get('GP Location')),  # out_gp_location
                safe_str(row.get('Block')),  # out_block
                safe_str(row.get('Dist')),  # out_dist
                safe_str(row.get('Item Code')),  # out_item_code
                safe_str(row.get('Description')),  # out_description
                safe_str(row.get('NO/Qty')),  # out_qty
                safe_str(row.get('PhysicalNO/Qty')),  # out_physical_qty
                safe_str(row.get('Unit')),  # out_unit
                safe_str(row.get('Rate per unit')),  # out_rate_per_unit
                safe_str(row.get('Total Value')),  # out_total_value
                safe_str(row.get('Taxbale Value')),  # out_taxable_value
                safe_str(row.get('TSC0.075%')),  # out_tsc
                safe_str(row.get('Discont-2.4(HFCL')),  # out_discount
                safe_str(row.get('Freight Charges')),  # out_freight_charge
                safe_str(row.get('Total')),  # out_total
                safe_str(row.get('CGST (9.00 %)')),  # out_cgst
                safe_str(row.get('SGST (9.00 %)')),  # out_sgst
                safe_str(row.get('Grant Total')),  # out_grand_total
                safe_str(row.get('Transport Name')),  # out_transport_name
                safe_str(row.get('Vehicle \nNo')),  # out_vehicle_no
                safe_str(row.get('Pkgs Qty')),  # out_pkgs_qty
                parse_date_value(row.get('Dispatched Date')),  # out_dispatched_date
                safe_str(row.get('Mode of Delivery')),  # out_mode_of_delivery
                safe_str(row.get('Reporting Time')),  # out_reporting_time
                safe_str(row.get('loading Time')),  # out_loading_time
                safe_str(row.get('Remark')),  # out_remark
                safe_str(row.get('UG/Aerial')),  # out_ug_aerial
                safe_str(row.get('FRT'))  # out_frt
            )
            
            # Verify we have exactly 38 values
            if len(values) != 38:
                print(f"Error: Expected 38 values, got {len(values)} for record {imported_count + 1}")
                continue
            
            # Insert into database using the exact same SQL as in app.py
            cur.execute("""
                INSERT INTO outward_info (
                    out_sr_no, out_atn, out_month, out_warehouse, out_shipment_type, out_dispatch_type,
                    out_in_doc_no, out_dc_no, out_dc_date, out_vendor_name, out_gp_location, out_block, out_dist,
                    out_item_code, out_description, out_qty, out_physical_qty, out_unit, out_rate_per_unit,
                    out_total_value, out_taxable_value, out_tsc, out_discount, out_freight_charge, out_total,
                    out_cgst, out_sgst, out_grand_total, out_transport_name, out_vehicle_no, out_pkgs_qty,
                    out_dispatched_date, out_mode_of_delivery, out_reporting_time, out_loading_time, out_remark,
                    out_ug_aerial, out_frt
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, values)
            imported_count += 1
            
            # Progress indicator
            if imported_count % 1000 == 0:
                print(f"Imported {imported_count} outward records...")
        
        conn.commit()
        print(f"Successfully imported {imported_count} outward records")
        
    except Exception as e:
        conn.rollback()
        print(f"Error importing outward data: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def main():
    excel_file = r"c:\Users\shraddha.more\Downloads\MAHANET-Inward Outward Report-28-Apr-2026.xlsx"
    
    try:
        # Read Excel file
        print("Reading Excel file...")
        excel_data = pd.read_excel(excel_file, sheet_name=None)
        
        print(f"Available sheets: {list(excel_data.keys())}")
        
        # Clear existing data
        print("Clearing existing data...")
        clear_existing_data()
        
        # Import inward data
        if 'Inwards' in excel_data:
            print("Importing inward data...")
            inward_df = excel_data['Inwards']
            import_inward_data(inward_df)
        
        # Import outward data
        if 'Outward' in excel_data:
            print("Importing outward data...")
            outward_df = excel_data['Outward']
            import_outward_data(outward_df)
        
        print("Data import completed successfully!")
        
    except Exception as e:
        print(f"Error during import: {e}")
        raise

if __name__ == "__main__":
    main()
