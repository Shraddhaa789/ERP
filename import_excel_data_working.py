import pandas as pd
import json
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
    
    # Try to parse string dates
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
    """Import inward data from DataFrame"""
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
            
            # Map Excel columns to database fields using actual column names
            inward_record = {
                'sr_no': safe_str(row.get('Sr NO')),
                'atn': safe_str(row.get('ATN')),
                'shifting': safe_str(row.get('Shifting (A-C)')),
                'original_wh': safe_str(row.get('Original Warehouse(Invoice/DC)')),
                'date': parse_date_value(row.get('Month')),
                'warehouse': safe_str(row.get('Warehouse')),
                'shipment_type': safe_str(row.get('Shipment Type/P ackage - A & C')),
                'dispatch_type': safe_str(row.get('Dispatched Type')),
                'in_doc_no': safe_str(row.get('IN. DOC No')),
                'order_no': safe_str(row.get('Order No')),
                'dc_no': safe_str(row.get('DC No')),
                'challan_date': parse_date_value(row.get('Challan Date')),
                'oem': safe_str(row.get('OEM')),
                'po_no': safe_str(row.get('PO O NO')),
                'po_name': safe_str(row.get('PO Issued Name')),
                'invoice_no': safe_str(row.get('Invoice No.')),
                'invoice_date': parse_date_value(row.get('Invoice Date')),
                'item_code': safe_str(row.get('Item Code')),
                'description': safe_str(row.get('Description')),
                'qty': safe_str(row.get('NO/Qty')),
                'physical_qty': safe_str(row.get('PhysicalNO/Qty')),
                'unit': safe_str(row.get('Unit')),
                'rate': safe_str(row.get('Rate per unit')),
                'total_value': safe_str(row.get('Total Value')),
                'taxable_value': safe_str(row.get('Taxbale Value')),
                'tsc': safe_str(row.get('TSC0.075%')),
                'discount': safe_str(row.get('Discont-2.4(HFCL')),
                'freight': safe_str(row.get('Freight Charges')),
                'additional_total': safe_str(row.get('Total')),
                'cgst': safe_str(row.get('CGST (9.00 %)')),
                'sgst': safe_str(row.get('SGST (9.00 %)')),
                'grand_total': safe_str(row.get('Grant Total')),
                'unloading': safe_str(row.get('Chmaber Unoading Charges')),
                'transport': safe_str(row.get('Transport Name')),
                'vehicle': safe_str(row.get('Vehicle \nNo')),
                'lr_no': safe_str(row.get('LR/RR NO')),
                'lr_date': parse_date_value(row.get('LR Date')),
                'pkgs_qty': safe_str(row.get('Pkgs Qty')),
                'delivery_date': parse_date_value(row.get('Delivery Date')),
                'mode': safe_str(row.get('Mode of Delivery')),
                'reporting_time': safe_str(row.get('Reporting Time')),
                'unloading_time': safe_str(row.get('Unloading Time')),
                'wh_remark': safe_str(row.get('W/H Remark')),
                'eway_bill': safe_str(row.get('e-WAY Bill No')),
                'shipment_type2': safe_str(row.get('Shipment Type')),
                'inspection_date': parse_date_value(row.get('Material Inspection Date/Date of Supply')),
                'inspection_person': safe_str(row.get('Material Inspection Person Name')),
                'doc_remark': safe_str(row.get('Document Remark')),
                'pm_update_date': parse_date_value(row.get('PM Tools Update/update_date')),
                'pm_update_by': safe_str(row.get('PM Tools Update By')),
                'reupload': safe_str(row.get('Re- Upload')),
                'reupload_reason': safe_str(row.get('Reason/ Re- Upload')),
                'pm_remark': safe_str(row.get('Remark')),
                'inspection_status': safe_str(row.get('Inspection Status on PM Tool')),
                'pm_submit_date': parse_date_value(row.get('PM Tool Submission Date')),
                'approved_dpm': parse_date_value(row.get('Approved by DPM-Date')),
                'approved_tpa': parse_date_value(row.get('Approved by TPA-Date'))
            }
            
            # Create values tuple in the correct order
            values = (
                inward_record['sr_no'], inward_record['atn'], inward_record['shifting'], inward_record['original_wh'],
                inward_record['date'], inward_record['warehouse'], inward_record['shipment_type'], inward_record['dispatch_type'],
                inward_record['in_doc_no'], inward_record['order_no'], inward_record['dc_no'], inward_record['challan_date'],
                inward_record['oem'], inward_record['po_no'], inward_record['po_name'],
                inward_record['invoice_no'], inward_record['invoice_date'],
                inward_record['item_code'], inward_record['description'], inward_record['qty'], inward_record['physical_qty'],
                inward_record['unit'], inward_record['rate'], inward_record['total_value'], inward_record['taxable_value'],
                inward_record['tsc'], inward_record['discount'], inward_record['freight'],
                inward_record['cgst'], inward_record['sgst'], inward_record['grand_total'],
                inward_record['unloading'], inward_record['transport'], inward_record['vehicle'], inward_record['lr_no'],
                inward_record['lr_date'], inward_record['pkgs_qty'], inward_record['delivery_date'], inward_record['mode'],
                inward_record['reporting_time'], inward_record['unloading_time'], inward_record['wh_remark'],
                inward_record['eway_bill'], inward_record['shipment_type2'],
                inward_record['inspection_date'], inward_record['inspection_person'],
                inward_record['pm_update_date'], inward_record['doc_remark'], inward_record['pm_update_by'],
                inward_record['reupload'], inward_record['reupload_reason'],
                inward_record['pm_remark'], inward_record['inspection_status'], inward_record['pm_submit_date'],
                inward_record['approved_dpm'], inward_record['approved_tpa']
            )
            
            # Insert into database
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
    """Import outward data from DataFrame"""
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
            
            # Map Excel columns to database fields using actual column names
            outward_record = {
                'out_sr_no': safe_str(row.get('Sr NO')),
                'out_atn': safe_str(row.get('ATN')),
                'out_month': parse_date_value(row.get('Month')),
                'out_warehouse': safe_str(row.get('Warehouse')),
                'out_shipment_type': safe_str(row.get('Shipment Type')),
                'out_dispatch_type': safe_str(row.get('Dispatched Type')),
                'out_in_doc_no': safe_str(row.get('IN. DOC No')),
                'out_dc_no': safe_str(row.get('DC No')),
                'out_dc_date': parse_date_value(row.get('DC Date')),
                'out_vendor_name': safe_str(row.get('Vendor Name')),
                'out_gp_location': safe_str(row.get('GP Location')),
                'out_block': safe_str(row.get('Block')),
                'out_dist': safe_str(row.get('Dist')),
                'out_item_code': safe_str(row.get('Item Code')),
                'out_description': safe_str(row.get('Description')),
                'out_qty': safe_str(row.get('NO/Qty')),
                'out_physical_qty': safe_str(row.get('PhysicalNO/Qty')),
                'out_unit': safe_str(row.get('Unit')),
                'out_rate_per_unit': safe_str(row.get('Rate per unit')),
                'out_total_value': safe_str(row.get('Total Value')),
                'out_taxable_value': safe_str(row.get('Taxbale Value')),
                'out_tsc': safe_str(row.get('TSC0.075%')),
                'out_discount': safe_str(row.get('Discont-2.4(HFCL')),
                'out_freight_charge': safe_str(row.get('Freight Charges')),
                'out_total': safe_str(row.get('Total')),
                'out_cgst': safe_str(row.get('CGST (9.00 %)')),
                'out_sgst': safe_str(row.get('SGST (9.00 %)')),
                'out_grand_total': safe_str(row.get('Grant Total')),
                'out_transport_name': safe_str(row.get('Transport Name')),
                'out_vehicle_no': safe_str(row.get('Vehicle \nNo')),
                'out_pkgs_qty': safe_str(row.get('Pkgs Qty')),
                'out_dispatched_date': parse_date_value(row.get('Dispatched Date')),
                'out_mode_of_delivery': safe_str(row.get('Mode of Delivery')),
                'out_reporting_time': safe_str(row.get('Reporting Time')),
                'out_loading_time': safe_str(row.get('loading Time')),
                'out_remark': safe_str(row.get('Remark')),
                'out_ug_aerial': safe_str(row.get('UG/Aerial')),
                'out_frt': safe_str(row.get('FRT'))
            }
            
            # Create values tuple in the correct order
            values = (
                outward_record['out_sr_no'], outward_record['out_atn'], outward_record['out_month'], outward_record['out_warehouse'],
                outward_record['out_shipment_type'], outward_record['out_dispatch_type'],
                outward_record['out_in_doc_no'], outward_record['out_dc_no'], outward_record['out_dc_date'],
                outward_record['out_vendor_name'], outward_record['out_gp_location'], outward_record['out_block'], outward_record['out_dist'],
                outward_record['out_item_code'], outward_record['out_description'], outward_record['out_qty'], outward_record['out_physical_qty'],
                outward_record['out_unit'], outward_record['out_rate_per_unit'],
                outward_record['out_total_value'], outward_record['out_taxable_value'], outward_record['out_tsc'],
                outward_record['out_discount'], outward_record['out_freight_charge'], outward_record['out_total'],
                outward_record['out_cgst'], outward_record['out_sgst'], outward_record['out_grand_total'],
                outward_record['out_transport_name'], outward_record['out_vehicle_no'], outward_record['out_pkgs_qty'],
                outward_record['out_dispatched_date'], outward_record['out_mode_of_delivery'],
                outward_record['out_reporting_time'], outward_record['out_loading_time'], outward_record['out_remark'],
                outward_record['out_ug_aerial'], outward_record['out_frt']
            )
            
            # Insert into database
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
