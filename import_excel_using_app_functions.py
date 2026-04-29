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

def db_scalar(value, is_date=False):
    """Convert value for database insertion"""
    if is_date:
        return parse_date_value(value)
    if value in (None, ""):
        return None
    return str(value)

def inward_db_values(record):
    """Create database values tuple using the same logic as app.py"""
    return (
        db_scalar(record.get("sr_no")),
        db_scalar(record.get("atn")),
        db_scalar(record.get("shifting")),
        db_scalar(record.get("original_wh")),
        db_scalar(record.get("date"), is_date=True),
        db_scalar(record.get("warehouse")),
        db_scalar(record.get("shipment_type")),
        db_scalar(record.get("dispatch_type")),
        db_scalar(record.get("in_doc_no")),
        db_scalar(record.get("order_no")),
        db_scalar(record.get("dc_no")),
        db_scalar(record.get("challan_date"), is_date=True),
        db_scalar(record.get("oem")),
        db_scalar(record.get("po_no")),
        db_scalar(record.get("po_name")),
        db_scalar(record.get("invoice_no")),
        db_scalar(record.get("invoice_date"), is_date=True),
        db_scalar(record.get("item_code")),
        db_scalar(record.get("description")),
        db_scalar(record.get("qty")),
        db_scalar(record.get("physical_qty")),
        db_scalar(record.get("unit")),
        db_scalar(record.get("rate")),
        db_scalar(record.get("total_value")),
        db_scalar(record.get("taxable_value")),
        db_scalar(record.get("tsc")),
        db_scalar(record.get("discount")),
        db_scalar(record.get("freight")),
        db_scalar(record.get("additional_total")),
        db_scalar(record.get("cgst")),
        db_scalar(record.get("sgst")),
        db_scalar(record.get("grand_total")),
        db_scalar(record.get("unloading")),
        db_scalar(record.get("transport")),
        db_scalar(record.get("vehicle")),
        db_scalar(record.get("lr_no")),
        db_scalar(record.get("lr_date"), is_date=True),
        db_scalar(record.get("pkgs_qty")),
        db_scalar(record.get("delivery_date"), is_date=True),
        db_scalar(record.get("mode")),
        db_scalar(record.get("reporting_time")),
        db_scalar(record.get("unloading_time")),
        db_scalar(record.get("wh_remark")),
        db_scalar(record.get("eway_bill")),
        db_scalar(record.get("shipment_type2")),
        db_scalar(record.get("inspection_date"), is_date=True),
        db_scalar(record.get("inspection_person")),
        db_scalar(record.get("pm_update_date"), is_date=True),
        db_scalar(record.get("doc_remark")),
        db_scalar(record.get("pm_update_by")),
        db_scalar(record.get("reupload")),
        db_scalar(record.get("reupload_reason")),
        db_scalar(record.get("pm_remark")),
        db_scalar(record.get("inspection_status")),
        db_scalar(record.get("pm_submit_date"), is_date=True),
        db_scalar(record.get("approved_dpm"), is_date=True),
        db_scalar(record.get("approved_tpa"), is_date=True)
    )

def outward_db_values(record):
    """Create database values tuple using the same logic as app.py"""
    return (
        db_scalar(record.get("out_sr_no")),
        db_scalar(record.get("out_atn")),
        db_scalar(record.get("out_month"), is_date=True),
        db_scalar(record.get("out_warehouse")),
        db_scalar(record.get("out_shipment_type")),
        db_scalar(record.get("out_dispatch_type")),
        db_scalar(record.get("out_in_doc_no")),
        db_scalar(record.get("out_dc_no")),
        db_scalar(record.get("out_dc_date"), is_date=True),
        db_scalar(record.get("out_vendor_name")),
        db_scalar(record.get("out_gp_location")),
        db_scalar(record.get("out_block")),
        db_scalar(record.get("out_dist")),
        db_scalar(record.get("out_item_code")),
        db_scalar(record.get("out_description")),
        db_scalar(record.get("out_qty")),
        db_scalar(record.get("out_physical_qty")),
        db_scalar(record.get("out_unit")),
        db_scalar(record.get("out_rate_per_unit")),
        db_scalar(record.get("out_total_value")),
        db_scalar(record.get("out_taxable_value")),
        db_scalar(record.get("out_tsc")),
        db_scalar(record.get("out_discount")),
        db_scalar(record.get("out_freight_charge")),
        db_scalar(record.get("out_total")),
        db_scalar(record.get("out_cgst")),
        db_scalar(record.get("out_sgst")),
        db_scalar(record.get("out_grand_total")),
        db_scalar(record.get("out_transport_name")),
        db_scalar(record.get("out_vehicle_no")),
        db_scalar(record.get("out_pkgs_qty")),
        db_scalar(record.get("out_dispatched_date"), is_date=True),
        db_scalar(record.get("out_mode_of_delivery")),
        db_scalar(record.get("out_reporting_time")),
        db_scalar(record.get("out_loading_time")),
        db_scalar(record.get("out_remark")),
        db_scalar(record.get("out_ug_aerial")),
        db_scalar(record.get("out_frt"))
    )

def import_inward_data(df):
    """Import inward data using the same field mapping as app.py"""
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
            
            # Map Excel columns to database field names using the same mapping as INWARD_FIELD_ORDER
            record = {
                "sr_no": safe_str(row.get('Sr NO')),
                "atn": safe_str(row.get('ATN')),
                "shifting": safe_str(row.get('Shifting (A-C)')),
                "original_wh": safe_str(row.get('Original Warehouse(Invoice/DC)')),
                "date": parse_date_value(row.get('Month')),
                "warehouse": safe_str(row.get('Warehouse')),
                "shipment_type": safe_str(row.get('Shipment Type/P ackage - A & C')),
                "dispatch_type": safe_str(row.get('Dispatched Type')),
                "in_doc_no": safe_str(row.get('IN. DOC No')),
                "order_no": safe_str(row.get('Order No')),
                "dc_no": safe_str(row.get('DC No')),
                "challan_date": parse_date_value(row.get('Challan Date')),
                "oem": safe_str(row.get('OEM')),
                "po_no": safe_str(row.get('PO NO')),
                "po_name": safe_str(row.get('PO Issued Name')),
                "invoice_no": safe_str(row.get('Invoice No.')),
                "invoice_date": parse_date_value(row.get('Invoice Date')),
                "item_code": safe_str(row.get('Item Code')),
                "description": safe_str(row.get('Description')),
                "qty": safe_str(row.get('NO/Qty')),
                "physical_qty": safe_str(row.get('PhysicalNO/Qty')),
                "unit": safe_str(row.get('Unit')),
                "rate": safe_str(row.get('Rate per unit')),
                "total_value": safe_str(row.get('Total Value')),
                "taxable_value": safe_str(row.get('Taxbale Value')),
                "tsc": safe_str(row.get('TSC0.075%')),
                "discount": safe_str(row.get('Discont-2.4(HFCL')),
                "freight": safe_str(row.get('Freight Charges')),
                "additional_total": safe_str(row.get('Total')),  # This is the key addition!
                "cgst": safe_str(row.get('CGST (9.00 %)')),
                "sgst": safe_str(row.get('SGST (9.00 %)')),
                "grand_total": safe_str(row.get('Grant Total')),
                "unloading": safe_str(row.get('Chmaber Unoading Charges')),
                "transport": safe_str(row.get('Transport Name')),
                "vehicle": safe_str(row.get('Vehicle \nNo')),
                "lr_no": safe_str(row.get('LR/RR NO')),
                "lr_date": parse_date_value(row.get('LR Date')),
                "pkgs_qty": safe_str(row.get('Pkgs Qty')),
                "delivery_date": parse_date_value(row.get('Delivery Date')),
                "mode": safe_str(row.get('Mode of Delivery')),
                "reporting_time": safe_str(row.get('Reporting Time')),
                "unloading_time": safe_str(row.get('Unloading Time')),
                "wh_remark": safe_str(row.get('W/H Remark')),
                "eway_bill": safe_str(row.get('e-WAY Bill No')),
                "shipment_type2": safe_str(row.get('Shipment Type')),
                "inspection_date": parse_date_value(row.get('Material Inspection Date/Date of Supply')),
                "inspection_person": safe_str(row.get('Material Inspection Person Name')),
                "doc_remark": safe_str(row.get('Document Remark')),
                "pm_update_date": parse_date_value(row.get('PM Tools Update/update_date')),
                "pm_update_by": safe_str(row.get('PM Tools Update By')),
                "reupload": safe_str(row.get('Re- Upload')),
                "reupload_reason": safe_str(row.get('Reason/ Re- Upload')),
                "pm_remark": safe_str(row.get('Remark')),
                "inspection_status": safe_str(row.get('Inspection Status on PM Tool')),
                "pm_submit_date": parse_date_value(row.get('PM Tool Submission Date')),
                "approved_dpm": parse_date_value(row.get('Approved by DPM-Date')),
                "approved_tpa": parse_date_value(row.get('Approved by TPA-Date'))
            }
            
            # Use the same database insertion logic as app.py
            values = inward_db_values(record)
            
            # Insert into database using the exact same SQL as in app.py
            cur.execute("""
                INSERT INTO basic_info (
                    sr_no, atn, shifting, original_wh, date, warehouse, shipment_type, dispatch_type,
                    in_doc_no, order_no, dc_no, challan_date,
                    oem, po_no, po_name,
                    invoice_no, invoice_date,
                    item_code, description, qty, physical_qty, unit,
                    rate, total_value, taxable_value,
                    tsc, discount, freight, additional_total,
                    cgst, sgst, grand_total,
                    unloading, transport, vehicle, lr_no, lr_date,
                    pkgs_qty, delivery_date, mode,
                    reporting_time, unloading_time, wh_remark,
                    eway_bill, shipment_type2,
                    inspection_date, inspection_person,
                    pm_update_date, doc_remark, pm_update_by, reupload, reupload_reason,
                    pm_remark, inspection_status, pm_submit_date,
                    approved_dpm, approved_tpa
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    """Import outward data using the same field mapping as app.py"""
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
            
            # Map Excel columns to database field names
            record = {
                "out_sr_no": safe_str(row.get('Sr NO')),
                "out_atn": safe_str(row.get('ATN')),
                "out_month": parse_date_value(row.get('Month')),
                "out_warehouse": safe_str(row.get('Warehouse')),
                "out_shipment_type": safe_str(row.get('Shipment Type')),
                "out_dispatch_type": safe_str(row.get('Dispatched Type')),
                "out_in_doc_no": safe_str(row.get('IN. DOC No')),
                "out_dc_no": safe_str(row.get('DC No')),
                "out_dc_date": parse_date_value(row.get('DC Date')),
                "out_vendor_name": safe_str(row.get('Vendor Name')),
                "out_gp_location": safe_str(row.get('GP Location')),
                "out_block": safe_str(row.get('Block')),
                "out_dist": safe_str(row.get('Dist')),
                "out_item_code": safe_str(row.get('Item Code')),
                "out_description": safe_str(row.get('Description')),
                "out_qty": safe_str(row.get('NO/Qty')),
                "out_physical_qty": safe_str(row.get('PhysicalNO/Qty')),
                "out_unit": safe_str(row.get('Unit')),
                "out_rate_per_unit": safe_str(row.get('Rate per unit')),
                "out_total_value": safe_str(row.get('Total Value')),
                "out_taxable_value": safe_str(row.get('Taxbale Value')),
                "out_tsc": safe_str(row.get('TSC0.075%')),
                "out_discount": safe_str(row.get('Discont-2.4(HFCL')),
                "out_freight_charge": safe_str(row.get('Freight Charges')),
                "out_total": safe_str(row.get('Total')),
                "out_cgst": safe_str(row.get('CGST (9.00 %)')),
                "out_sgst": safe_str(row.get('SGST (9.00 %)')),
                "out_grand_total": safe_str(row.get('Grant Total')),
                "out_transport_name": safe_str(row.get('Transport Name')),
                "out_vehicle_no": safe_str(row.get('Vehicle \nNo')),
                "out_pkgs_qty": safe_str(row.get('Pkgs Qty')),
                "out_dispatched_date": parse_date_value(row.get('Dispatched Date')),
                "out_mode_of_delivery": safe_str(row.get('Mode of Delivery')),
                "out_reporting_time": safe_str(row.get('Reporting Time')),
                "out_loading_time": safe_str(row.get('loading Time')),
                "out_remark": safe_str(row.get('Remark')),
                "out_ug_aerial": safe_str(row.get('UG/Aerial')),
                "out_frt": safe_str(row.get('FRT'))
            }
            
            # Use the same database insertion logic as app.py
            values = outward_db_values(record)
            
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            print("Importing inward data with all 57 columns...")
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
