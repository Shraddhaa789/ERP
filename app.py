from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session
import json
import psycopg2
import os
import base64
from datetime import date, datetime, time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_REPORT_DATA_PATH = os.path.join(BASE_DIR, "database", "sample_report_data.json")
WAREHOUSE_INVENTORY_DATA_PATH = os.path.join(BASE_DIR, "database", "warehouse_inventory_data.json")

INWARD_FIELD_ORDER = [
    "sr_no", "atn", "shifting", "original_wh", "date", "warehouse", "shipment_type", "dispatch_type",
    "in_doc_no", "order_no", "dc_no", "challan_date",
    "oem", "po_no", "po_name",
    "invoice_no", "invoice_date",
    "item_code", "description", "qty", "physical_qty", "unit",
    "rate", "total_value", "taxable_value",
    "tsc", "discount", "freight", "additional_total",
    "cgst", "sgst", "grand_total",
    "unloading", "transport", "vehicle", "lr_no", "lr_date",
    "pkgs_qty", "delivery_date", "mode",
    "reporting_time", "unloading_time", "wh_remark",
    "eway_bill", "shipment_type2",
    "inspection_date", "inspection_person",
    "doc_remark", "pm_update_date", "pm_update_by", "reupload", "reupload_reason",
    "pm_remark", "inspection_status", "pm_submit_date",
    "approved_dpm", "approved_tpa"
]

OUTWARD_FIELD_ORDER = [
    "out_sr_no", "out_atn", "out_month", "out_warehouse", "out_shipment_type", "out_dispatch_type",
    "out_in_doc_no", "out_dc_no", "out_dc_date", "out_vendor_name", "out_gp_location", "out_block", "out_dist",
    "out_item_code", "out_description", "out_qty", "out_physical_qty", "out_unit", "out_rate_per_unit",
    "out_total_value", "out_taxable_value", "out_tsc", "out_discount", "out_freight_charge", "out_total",
    "out_cgst", "out_sgst", "out_grand_total", "out_transport_name", "out_vehicle_no", "out_pkgs_qty",
    "out_dispatched_date", "out_mode_of_delivery", "out_reporting_time", "out_loading_time", "out_remark",
    "out_ug_aerial", "out_frt"
]

INWARD_DATE_FIELDS = {
    "date", "challan_date", "invoice_date", "lr_date", "delivery_date", "inspection_date",
    "pm_update_date", "pm_submit_date", "approved_dpm", "approved_tpa"
}

OUTWARD_DATE_FIELDS = {"out_month", "out_dc_date", "out_dispatched_date"}

REAL_DATA_BOOTSTRAPPED = False

# folders
os.makedirs("uploads/images", exist_ok=True)
os.makedirs("uploads/documents", exist_ok=True)


def default_profile():
    return {
        "name": "ERP Admin Pune",
        "designation": "ADMIN",
        "employee_code": "1",
        "location": "Admin, Maharashtra",
        "mobile": "9561583126",
        "email": "ADMIN",
        "gender": "Male",
        "blood_group": "A+",
        "photo_name": "No file selected",
        "photo_path": ""
    }


def get_conn():
    return psycopg2.connect(
        host="localhost",
        database="construction_erp",
        user="postgres",
        password="pass123"
    )


def require_login():
    if "user" not in session:
        return redirect("/")
    return None


def require_role(role):
    if session.get("role") != role:
        return redirect("/")
    return None


def get_profile():
    profile = default_profile()
    profile.update(session.get("profile", {}))
    return profile


def load_sample_report_data():
    if not os.path.exists(SAMPLE_REPORT_DATA_PATH):
        return {"inward": [], "outward": []}

    try:
        with open(SAMPLE_REPORT_DATA_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"inward": [], "outward": []}

    return {
        "inward": data.get("inward", []),
        "outward": data.get("outward", [])
    }


def load_warehouse_inventory_data():
    if not os.path.exists(WAREHOUSE_INVENTORY_DATA_PATH):
        return {"rows": []}

    try:
        with open(WAREHOUSE_INVENTORY_DATA_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"rows": []}

    return {"rows": data.get("rows", [])}


def get_warehouse_inventory_payload():
    bootstrap_real_data()

    baseline_rows = load_warehouse_inventory_data().get("rows", [])
    inventory_map = {}
    for row in baseline_rows:
        key = (str(row.get("warehouse", "")).strip(), str(row.get("description", "")).strip())
        inventory_map[key] = {
            "warehouse": key[0],
            "description": key[1],
            "inward_qty": float(row.get("inward_qty") or 0),
            "inward_mtr": float(row.get("inward_mtr") or 0),
            "inward_unit_km": float(row.get("inward_unit_km") or 0),
            "outward_qty": float(row.get("outward_qty") or 0),
            "outward_mtr": float(row.get("outward_mtr") or 0),
            "outward_unit_km": float(row.get("outward_unit_km") or 0),
            "phy_stock_qty": float(row.get("phy_stock_qty") or 0),
            "phy_stock_mtr": float(row.get("phy_stock_mtr") or 0),
            "phy_stock_unit_km": float(row.get("phy_stock_unit_km") or 0)
        }

    conn = get_conn()
    cur = conn.cursor()

    def numeric_sql(column_name):
        cleaned = f"REGEXP_REPLACE(COALESCE({column_name}, ''), ',', '', 'g')"
        return f"""
            CASE
                WHEN BTRIM(COALESCE({column_name}, '')) = '' THEN 0
                WHEN {cleaned} ~ '^[-+]?\\d*\\.?\\d+$' THEN CAST({cleaned} AS DOUBLE PRECISION)
                ELSE 0
            END
        """

    inward_qty_sql = numeric_sql("qty")
    inward_unit_sql = numeric_sql("unit")
    outward_qty_sql = numeric_sql("out_qty")
    outward_unit_sql = numeric_sql("out_unit")

    cur.execute(
        f"""
        SELECT
            BTRIM(warehouse) AS warehouse,
            BTRIM(description) AS description,
            SUM({inward_qty_sql}) AS inward_qty,
            SUM(CASE WHEN ABS({inward_unit_sql} - {inward_qty_sql}) > 0.000001 THEN {inward_unit_sql} ELSE 0 END) AS inward_mtr
        FROM basic_info
        WHERE source_tag = 'manual'
          AND BTRIM(COALESCE(warehouse, '')) <> ''
          AND BTRIM(COALESCE(description, '')) <> ''
        GROUP BY BTRIM(warehouse), BTRIM(description)
        """
    )
    manual_inward = cur.fetchall()

    cur.execute(
        f"""
        SELECT
            BTRIM(out_warehouse) AS warehouse,
            BTRIM(out_description) AS description,
            SUM({outward_qty_sql}) AS outward_qty,
            SUM(CASE WHEN ABS({outward_unit_sql} - {outward_qty_sql}) > 0.000001 THEN {outward_unit_sql} ELSE 0 END) AS outward_mtr
        FROM outward_info
        WHERE source_tag = 'manual'
          AND BTRIM(COALESCE(out_warehouse, '')) <> ''
          AND BTRIM(COALESCE(out_description, '')) <> ''
        GROUP BY BTRIM(out_warehouse), BTRIM(out_description)
        """
    )
    manual_outward = cur.fetchall()

    cur.close()
    conn.close()

    for warehouse, description, inward_qty, inward_mtr in manual_inward:
        key = (warehouse, description)
        row = inventory_map.setdefault(key, {
            "warehouse": warehouse,
            "description": description,
            "inward_qty": 0.0,
            "inward_mtr": 0.0,
            "inward_unit_km": 0.0,
            "outward_qty": 0.0,
            "outward_mtr": 0.0,
            "outward_unit_km": 0.0,
            "phy_stock_qty": 0.0,
            "phy_stock_mtr": 0.0,
            "phy_stock_unit_km": 0.0
        })
        row["inward_qty"] += float(inward_qty or 0)
        row["inward_mtr"] += float(inward_mtr or 0)
        row["inward_unit_km"] = row["inward_mtr"] / 1000.0
        row["phy_stock_qty"] += float(inward_qty or 0)
        row["phy_stock_mtr"] += float(inward_mtr or 0)
        row["phy_stock_unit_km"] = row["phy_stock_mtr"] / 1000.0

    for warehouse, description, outward_qty, outward_mtr in manual_outward:
        key = (warehouse, description)
        row = inventory_map.setdefault(key, {
            "warehouse": warehouse,
            "description": description,
            "inward_qty": 0.0,
            "inward_mtr": 0.0,
            "inward_unit_km": 0.0,
            "outward_qty": 0.0,
            "outward_mtr": 0.0,
            "outward_unit_km": 0.0,
            "phy_stock_qty": 0.0,
            "phy_stock_mtr": 0.0,
            "phy_stock_unit_km": 0.0
        })
        row["outward_qty"] += float(outward_qty or 0)
        row["outward_mtr"] += float(outward_mtr or 0)
        row["outward_unit_km"] = row["outward_mtr"] / 1000.0
        row["phy_stock_qty"] -= float(outward_qty or 0)
        row["phy_stock_mtr"] -= float(outward_mtr or 0)
        row["phy_stock_unit_km"] = row["phy_stock_mtr"] / 1000.0

    rows = []
    for key in sorted(inventory_map.keys()):
        row = inventory_map[key]
        rows.append({
            "warehouse": row["warehouse"],
            "description": row["description"],
            "inward_qty": round(row["inward_qty"], 6),
            "inward_mtr": round(row["inward_mtr"], 6),
            "inward_unit_km": round(row["inward_unit_km"], 6),
            "outward_qty": round(row["outward_qty"], 6),
            "outward_mtr": round(row["outward_mtr"], 6),
            "outward_unit_km": round(row["outward_unit_km"], 6),
            "phy_stock_qty": round(row["phy_stock_qty"], 6),
            "phy_stock_mtr": round(row["phy_stock_mtr"], 6),
            "phy_stock_unit_km": round(row["phy_stock_unit_km"], 6)
        })

    warehouses = sorted({row["warehouse"] for row in rows if row.get("warehouse")})
    materials = sorted({row["description"] for row in rows if row.get("description")})
    total_physical_qty = sum(float(row.get("phy_stock_qty") or 0) for row in rows)

    return {
        "rows": rows,
        "warehouses": warehouses,
        "materials": materials,
        "summary": {
            "row_count": len(rows),
            "warehouse_count": len(warehouses),
            "material_count": len(materials),
            "total_physical_qty": total_physical_qty,
            "source": "summary_plus_live_delta"
        }
    }


def serialize_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return "" if value is None else value


def parse_date_value(value):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("a.m.", "AM").replace("p.m.", "PM").replace("a.m", "AM").replace("p.m", "PM")

    for pattern in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y, %I:%M %p", "%b %d, %Y, %I:%M %p"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue

    if "T" in normalized:
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            pass

    return None


def db_scalar(value, is_date=False):
    if is_date:
        return parse_date_value(value)
    if value in (None, ""):
        return None
    return str(value)


def inward_db_values(record):
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


def prepare_inward_record(record):
    prepared = {key: serialize_value(record.get(key, "")) for key in INWARD_FIELD_ORDER if key != "additional_total"}

    if "additional_total" in record and record.get("additional_total") not in (None, ""):
        prepared["additional_total"] = serialize_value(record.get("additional_total"))
    else:
        total_value = float(record.get("total_value") or 0)
        tsc = float(record.get("tsc") or 0)
        discount = float(record.get("discount") or 0)
        freight = float(record.get("freight") or 0)
        prepared["additional_total"] = round(total_value + tsc - discount + freight, 2) if any([total_value, tsc, discount, freight]) else ""

    return prepared


def prepare_outward_record(record):
    prepared = {key: serialize_value(record.get(key, "")) for key in OUTWARD_FIELD_ORDER}
    return prepared


def ensure_basic_info_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS basic_info (
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
            pm_update_date DATE,
            doc_remark TEXT,
            pm_update_by TEXT,
            reupload TEXT,
            reupload_reason TEXT,
            pm_remark TEXT,
            inspection_status TEXT,
            pm_submit_date DATE,
            approved_dpm DATE,
            approved_tpa DATE,
            source_tag TEXT DEFAULT 'seed'
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_basic_info_challan_date ON basic_info (challan_date)")
    cur.execute("ALTER TABLE basic_info ADD COLUMN IF NOT EXISTS source_tag TEXT DEFAULT 'seed'")
    cur.execute("UPDATE basic_info SET source_tag = 'seed' WHERE source_tag IS NULL")


def ensure_outward_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS outward_info (
            id SERIAL PRIMARY KEY,
            out_sr_no TEXT,
            out_atn TEXT,
            out_month DATE,
            out_warehouse TEXT,
            out_shipment_type TEXT,
            out_dispatch_type TEXT,
            out_in_doc_no TEXT,
            out_dc_no TEXT,
            out_dc_date DATE,
            out_vendor_name TEXT,
            out_gp_location TEXT,
            out_block TEXT,
            out_dist TEXT,
            out_item_code TEXT,
            out_description TEXT,
            out_qty TEXT,
            out_physical_qty TEXT,
            out_unit TEXT,
            out_rate_per_unit TEXT,
            out_total_value TEXT,
            out_taxable_value TEXT,
            out_tsc TEXT,
            out_discount TEXT,
            out_freight_charge TEXT,
            out_total TEXT,
            out_cgst TEXT,
            out_sgst TEXT,
            out_grand_total TEXT,
            out_transport_name TEXT,
            out_vehicle_no TEXT,
            out_pkgs_qty TEXT,
            out_dispatched_date DATE,
            out_mode_of_delivery TEXT,
            out_reporting_time TEXT,
            out_loading_time TEXT,
            out_remark TEXT,
            out_ug_aerial TEXT,
            out_frt TEXT,
            out_from_location TEXT,
            out_to_location TEXT,
            out_tracking TEXT,
            out_distance_km TEXT,
            source_tag TEXT DEFAULT 'seed'
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_outward_info_dc_date ON outward_info (out_dc_date)")
    cur.execute("ALTER TABLE outward_info ADD COLUMN IF NOT EXISTS out_from_location TEXT")
    cur.execute("ALTER TABLE outward_info ADD COLUMN IF NOT EXISTS out_to_location TEXT")
    cur.execute("ALTER TABLE outward_info ADD COLUMN IF NOT EXISTS out_tracking TEXT")
    cur.execute("ALTER TABLE outward_info ADD COLUMN IF NOT EXISTS out_distance_km TEXT")
    cur.execute("ALTER TABLE outward_info ADD COLUMN IF NOT EXISTS source_tag TEXT DEFAULT 'seed'")
    cur.execute("UPDATE outward_info SET source_tag = 'seed' WHERE source_tag IS NULL")


def inward_record_exists(cur, record):
    cur.execute(
        """
        SELECT 1
        FROM basic_info
        WHERE sr_no IS NOT DISTINCT FROM %s
          AND warehouse IS NOT DISTINCT FROM %s
          AND item_code IS NOT DISTINCT FROM %s
          AND dc_no IS NOT DISTINCT FROM %s
          AND challan_date IS NOT DISTINCT FROM %s
        LIMIT 1
        """,
        (
            db_scalar(record.get("sr_no")),
            db_scalar(record.get("warehouse")),
            db_scalar(record.get("item_code")),
            db_scalar(record.get("dc_no")),
            db_scalar(record.get("challan_date"), is_date=True)
        )
    )
    return cur.fetchone() is not None


def outward_record_exists(cur, record):
    cur.execute(
        """
        SELECT 1
        FROM outward_info
        WHERE out_sr_no IS NOT DISTINCT FROM %s
          AND out_warehouse IS NOT DISTINCT FROM %s
          AND out_item_code IS NOT DISTINCT FROM %s
          AND out_dc_no IS NOT DISTINCT FROM %s
          AND out_dc_date IS NOT DISTINCT FROM %s
        LIMIT 1
        """,
        (
            db_scalar(record.get("out_sr_no")),
            db_scalar(record.get("out_warehouse")),
            db_scalar(record.get("out_item_code")),
            db_scalar(record.get("out_dc_no")),
            db_scalar(record.get("out_dc_date"), is_date=True)
        )
    )
    return cur.fetchone() is not None


def bootstrap_real_data(force=False):
    global REAL_DATA_BOOTSTRAPPED

    seed_data = load_sample_report_data()
    conn = get_conn()
    cur = conn.cursor()

    try:
        ensure_basic_info_table(cur)
        ensure_outward_table(cur)

        if REAL_DATA_BOOTSTRAPPED and not force:
            conn.commit()
            return

        if force:
            cur.execute("TRUNCATE TABLE outward_info RESTART IDENTITY")
            cur.execute("TRUNCATE TABLE basic_info RESTART IDENTITY")

        cur.execute("SELECT COUNT(*) FROM basic_info")
        inward_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM outward_info")
        outward_count = cur.fetchone()[0]

        if inward_count == 0:
            for record in seed_data.get("inward", []):
                cur.execute(
                    """
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
                    approved_dpm, approved_tpa, source_tag
                )
                VALUES ({})
                """.format(", ".join(["%s"] * 57)),
                inward_db_values(record) + ("seed",)
            )

        if outward_count == 0:
            for record in seed_data.get("outward", []):
                cur.execute(
                    """
                    INSERT INTO outward_info (
                        out_sr_no, out_atn, out_month, out_warehouse, out_shipment_type, out_dispatch_type,
                        out_in_doc_no, out_dc_no, out_dc_date, out_vendor_name, out_gp_location, out_block, out_dist,
                        out_item_code, out_description, out_qty, out_physical_qty, out_unit, out_rate_per_unit,
                        out_total_value, out_taxable_value, out_tsc, out_discount, out_freight_charge, out_total,
                        out_cgst, out_sgst, out_grand_total, out_transport_name, out_vehicle_no, out_pkgs_qty,
                        out_dispatched_date, out_mode_of_delivery, out_reporting_time, out_loading_time, out_remark,
                        out_ug_aerial, out_frt, source_tag
                    )
                    VALUES ({})
                    """.format(", ".join(["%s"] * 39)),
                    outward_db_values(record) + ("seed",)
                )

        conn.commit()
        REAL_DATA_BOOTSTRAPPED = True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def default_app_settings():
    return {
        "default_report_type": "inward",
        "report_rows": "50",
        "export_format": "csv",
        "notify_email": True,
        "notify_dashboard": True,
        "compact_tables": False,
        "approval_lock": True,
        "show_totals": True
    }


def get_app_settings():
    settings = default_app_settings()
    settings.update(session.get("app_settings", {}))
    return settings


def get_inward_report_records(limit=None, year=None):
    bootstrap_real_data()

    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT
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
        FROM basic_info
    """
    params = []

    if year is not None:
        query += " WHERE challan_date IS NOT NULL AND EXTRACT(YEAR FROM challan_date) = %s"
        params.append(year)

    query += " ORDER BY challan_date DESC NULLS LAST, id DESC"

    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)
        cur.execute(query, tuple(params))
    else:
        cur.execute(query, tuple(params))
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    cur.close()
    conn.close()

    return [dict(zip(columns, row)) for row in rows]


def get_outward_report_records(limit=None, year=None):
    bootstrap_real_data()

    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT
            out_sr_no, out_atn, out_month, out_warehouse, out_shipment_type, out_dispatch_type,
            out_in_doc_no, out_dc_no, out_dc_date, out_vendor_name, out_gp_location, out_block, out_dist,
            out_item_code, out_description, out_qty, out_physical_qty, out_unit, out_rate_per_unit,
            out_total_value, out_taxable_value, out_tsc, out_discount, out_freight_charge, out_total,
            out_cgst, out_sgst, out_grand_total, out_transport_name, out_vehicle_no, out_pkgs_qty,
            out_dispatched_date, out_mode_of_delivery, out_reporting_time, out_loading_time, out_remark,
            out_ug_aerial, out_frt
        FROM outward_info
    """
    params = []

    if year is not None:
        query += " WHERE out_dc_date IS NOT NULL AND EXTRACT(YEAR FROM out_dc_date) = %s"
        params.append(year)

    query += " ORDER BY out_dc_date DESC NULLS LAST, id DESC"

    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)
        cur.execute(query, tuple(params))
    else:
        cur.execute(query, tuple(params))
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    cur.close()
    conn.close()

    return [dict(zip(columns, row)) for row in rows]


def get_report_years(report_type):
    bootstrap_real_data()

    conn = get_conn()
    cur = conn.cursor()

    if report_type == "outward":
        cur.execute(
            """
            SELECT DISTINCT EXTRACT(YEAR FROM out_dc_date)::INT AS year_value
            FROM outward_info
            WHERE out_dc_date IS NOT NULL
            ORDER BY year_value DESC
            """
        )
    else:
        cur.execute(
            """
            SELECT DISTINCT EXTRACT(YEAR FROM challan_date)::INT AS year_value
            FROM basic_info
            WHERE challan_date IS NOT NULL
            ORDER BY year_value DESC
            """
        )

    min_year = 2018
    max_year = date.today().year + 1
    years = [row[0] for row in cur.fetchall() if row[0] is not None and min_year <= row[0] <= max_year]
    cur.close()
    conn.close()
    return years


def get_report_page(report_type, year=None, limit=100, offset=0, search_term="", search_field="all"):
    bootstrap_real_data()

    report_type = "outward" if report_type == "outward" else "inward"
    is_outward = report_type == "outward"

    select_columns = """
        out_sr_no, out_atn, out_month, out_warehouse, out_shipment_type, out_dispatch_type,
        out_in_doc_no, out_dc_no, out_dc_date, out_vendor_name, out_gp_location, out_block, out_dist,
        out_item_code, out_description, out_qty, out_physical_qty, out_unit, out_rate_per_unit,
        out_total_value, out_taxable_value, out_tsc, out_discount, out_freight_charge, out_total,
        out_cgst, out_sgst, out_grand_total, out_transport_name, out_vehicle_no, out_pkgs_qty,
        out_dispatched_date, out_mode_of_delivery, out_reporting_time, out_loading_time, out_remark,
        out_ug_aerial, out_frt
    """ if is_outward else """
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
    """

    table_name = "outward_info" if is_outward else "basic_info"
    date_column = "out_dc_date" if is_outward else "challan_date"
    allowed_fields = set(OUTWARD_FIELD_ORDER if is_outward else [field for field in INWARD_FIELD_ORDER if field != "additional_total"])

    conditions = []
    params = []

    if year is not None:
        conditions.append(f"{date_column} >= %s AND {date_column} < %s")
        params.extend([date(year, 1, 1), date(year + 1, 1, 1)])

    search_text = (search_term or "").strip()
    if search_text:
        if search_field and search_field != "all" and search_field in allowed_fields:
            conditions.append(f"COALESCE(CAST({search_field} AS TEXT), '') ILIKE %s")
            params.append(f"%{search_text}%")
        else:
            search_targets = list(allowed_fields)
            search_sql = " OR ".join([f"COALESCE(CAST({field} AS TEXT), '') ILIKE %s" for field in search_targets])
            conditions.append(f"({search_sql})")
            params.extend([f"%{search_text}%"] * len(search_targets))

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    conn = get_conn()
    cur = conn.cursor()

    count_query = f"SELECT COUNT(*) FROM {table_name}{where_clause}"
    cur.execute(count_query, tuple(params))
    total_count = cur.fetchone()[0]

    data_query = f"""
        SELECT {select_columns}
        FROM {table_name}
        {where_clause}
        ORDER BY {date_column} DESC NULLS LAST, id DESC
        LIMIT %s OFFSET %s
    """
    cur.execute(data_query, tuple(params + [limit, offset]))
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    cur.close()
    conn.close()

    return [dict(zip(columns, row)) for row in rows], total_count


def get_dashboard_payload():
    bootstrap_real_data()
    inventory_payload = get_warehouse_inventory_payload()
    inventory_rows = inventory_payload.get("rows", [])

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM basic_info")
    inward_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM outward_info")
    outward_count = cur.fetchone()[0]

    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM challan_date)::INT AS year_value, COUNT(*)
        FROM basic_info
        WHERE challan_date IS NOT NULL
        GROUP BY year_value
        ORDER BY year_value
        """
    )
    inward_year_map = {row[0]: row[1] for row in cur.fetchall() if row[0] is not None}

    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM out_dc_date)::INT AS year_value, COUNT(*)
        FROM outward_info
        WHERE out_dc_date IS NOT NULL
        GROUP BY year_value
        ORDER BY year_value
        """
    )
    outward_year_map = {row[0]: row[1] for row in cur.fetchall() if row[0] is not None}

    cur.execute(
        """
        SELECT entry_type, movement_date, warehouse_name, description, qty_value, document_no
        FROM (
            SELECT
                'Inward' AS entry_type,
                challan_date AS movement_date,
                warehouse AS warehouse_name,
                description,
                qty AS qty_value,
                dc_no AS document_no
            FROM basic_info
            WHERE challan_date IS NOT NULL

            UNION ALL

            SELECT
                'Outward' AS entry_type,
                out_dc_date AS movement_date,
                out_warehouse AS warehouse_name,
                out_description AS description,
                out_qty AS qty_value,
                out_dc_no AS document_no
            FROM outward_info
            WHERE out_dc_date IS NOT NULL
        ) movement_log
        ORDER BY movement_date DESC, entry_type
        LIMIT 8
        """
    )
    recent_rows = cur.fetchall()

    cur.close()
    conn.close()

    years = sorted(set(inward_year_map) | set(outward_year_map))
    movement_years = years[-6:] if len(years) > 6 else years
    yearly_trend = [
        {
            "year": year,
            "inward": inward_year_map.get(year, 0),
            "outward": outward_year_map.get(year, 0)
        }
        for year in movement_years
    ]

    warehouse_totals = {}
    material_totals = {}
    positive_stock_rows = []
    total_inward_qty = 0.0
    total_outward_qty = 0.0
    total_physical_qty = 0.0

    for row in inventory_rows:
        warehouse = row.get("warehouse") or "-"
        material = row.get("description") or "-"
        inward_qty = float(row.get("inward_qty") or 0)
        outward_qty = float(row.get("outward_qty") or 0)
        physical_qty = float(row.get("phy_stock_qty") or 0)

        total_inward_qty += inward_qty
        total_outward_qty += outward_qty
        total_physical_qty += physical_qty

        warehouse_totals[warehouse] = warehouse_totals.get(warehouse, 0) + physical_qty
        material_totals[material] = material_totals.get(material, 0) + physical_qty

        if physical_qty > 0:
            positive_stock_rows.append({
                "warehouse": warehouse,
                "description": material,
                "phy_stock_qty": physical_qty
            })

    top_warehouses = sorted(
        [{"warehouse": key, "stock_qty": value} for key, value in warehouse_totals.items()],
        key=lambda item: item["stock_qty"],
        reverse=True
    )[:5]

    top_materials = sorted(
        [{"description": key, "stock_qty": value} for key, value in material_totals.items()],
        key=lambda item: item["stock_qty"],
        reverse=True
    )[:6]

    low_stock_items = sorted(positive_stock_rows, key=lambda item: item["phy_stock_qty"])[:6]

    recent_activity = [
        {
            "type": row[0],
            "date": row[1].isoformat() if row[1] else "",
            "warehouse": row[2] or "-",
            "description": row[3] or "-",
            "qty": row[4] or "0",
            "document_no": row[5] or "-"
        }
        for row in recent_rows
    ]

    return {
        "hero": {
            "inventory_source": inventory_payload.get("summary", {}).get("source", "live"),
            "warehouse_count": inventory_payload.get("summary", {}).get("warehouse_count", 0),
            "material_count": inventory_payload.get("summary", {}).get("material_count", 0)
        },
        "kpis": {
            "inward_count": inward_count,
            "outward_count": outward_count,
            "inventory_rows": inventory_payload.get("summary", {}).get("row_count", 0),
            "warehouse_count": inventory_payload.get("summary", {}).get("warehouse_count", 0),
            "material_count": inventory_payload.get("summary", {}).get("material_count", 0),
            "total_inward_qty": total_inward_qty,
            "total_outward_qty": total_outward_qty,
            "total_physical_qty": total_physical_qty
        },
        "yearly_trend": yearly_trend,
        "top_warehouses": top_warehouses,
        "top_materials": top_materials,
        "low_stock_items": low_stock_items,
        "recent_activity": recent_activity
    }


def render_page(template_name, panel_title, active_page, **context):
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    return render_template(
        template_name,
        user=session["user"],
        role=session.get("role"),
        panel_title=panel_title,
        active_page=active_page,
        profile=get_profile(),
        app_settings=get_app_settings(),
        **context
    )


# ================= LOGIN =================

@app.route("/")
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT username, role FROM users WHERE username=%s AND password=%s",
        (username, password)
    )
    user = cur.fetchone()

    cur.close()
    conn.close()

    if user:
        session["user"] = user[0]
        session["role"] = user[1]

        if user[1] == "admin":
            return redirect("/admin-dashboard")
        elif user[1] == "ground":
            return redirect("/ground-dashboard")
        elif user[1] == "user":
            return redirect("/user-dashboard")

    return "Invalid Username or Password"




# ======user route =====
@app.route("/add-user", methods=["POST"])
def add_user():
    if require_role("admin"):
        return redirect("/")

    name = request.form["name"]
    username = request.form["username"]
    password = request.form["password"]
    role = request.form["role"]

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO users (name, username, password, role)
        VALUES (%s, %s, %s, %s)
    """, (name, username, password, role))

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/admin-dashboard")







# ================= DASHBOARDS =================

@app.route("/admin-dashboard")
def admin_dashboard():
    if require_role("admin"):
        return redirect("/")
    return render_page("admin.html", "Admin Panel", "admin_dashboard")


@app.route("/ground-dashboard")
def ground_dashboard():
    if require_role("ground"):
        return redirect("/")
    return render_page("ground/ground_dashboard.html", "Ground Team Panel", "ground_dashboard")


@app.route("/user-dashboard")
def user_dashboard():
    if require_role("user"):
        return redirect("/")
    return render_page("users/user_dashboard.html", "User Dashboard", "user_dashboard")


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if require_role("admin"):
        return redirect("/")

    if request.method == "POST":
        session["profile"] = {
            **get_profile(),
            "name": request.form["name"],
            "designation": request.form["designation"],
            "employee_code": request.form["employee_code"],
            "location": request.form["location"],
            "mobile": request.form["mobile"],
            "email": request.form["email"],
            "gender": request.form["gender"],
            "blood_group": request.form["blood_group"]
        }
        return redirect("/my-account")

    return render_page("edit_profile.html", "Edit Profile", "account")


@app.route("/change-photo", methods=["GET", "POST"])
def change_photo():
    if require_role("admin"):
        return redirect("/")

    if request.method == "POST":
        uploaded_file = request.files.get("photo")
        profile = get_profile()

        if uploaded_file and uploaded_file.filename:
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(uploaded_file.filename)}"
            relative_path = f"images/{filename}"
            absolute_path = os.path.join(BASE_DIR, "uploads", "images", filename)
            uploaded_file.save(absolute_path)
            profile["photo_name"] = uploaded_file.filename
            profile["photo_path"] = relative_path

        session["profile"] = profile
        return redirect("/my-account")

    return render_page("change_photo.html", "Change Photo", "account")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(os.path.join(BASE_DIR, "uploads"), filename)


@app.route("/add-material", methods=["POST"])
def add_material():
    if session.get("role") not in {"admin", "ground"}:
        return redirect("/")

    payload = request.json if request.is_json else request.form

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO materials (name, unit, quantity) VALUES (%s, %s, %s)",
        (payload.get("name"), payload.get("unit"), payload.get("quantity"))
    )

    conn.commit()
    cur.close()
    conn.close()

    if request.is_json:
        return jsonify({"message": "Material Added"})

    return redirect("/ground-dashboard")


# ================= USER MODULE =================

@app.route("/upload-work", methods=["GET", "POST"])
def upload_work():
    if require_role("user"):
        return redirect("/")

    if request.method == "POST":
        image_data = request.form.get("image_data")

        if image_data:
            header, encoded = image_data.split(",", 1)
            data = base64.b64decode(encoded)

            filename = f"{datetime.now().timestamp()}.png"
            filepath = f"uploads/images/{filename}"

            with open(filepath, "wb") as f:
                f.write(data)

            conn = get_conn()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO work_uploads 
                (user_id, image_path, location, material, quantity, remarks)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                1,
                filepath,
                request.form.get("location"),
                request.form.get("material"),
                request.form.get("quantity"),
                request.form.get("remarks")
            ))

            conn.commit()
            cur.close()
            conn.close()

        return redirect("/user-dashboard")

    return render_page("users/upload_work.html", "Upload Work", "upload_work")


@app.route("/upload-documents", methods=["GET", "POST"])
def upload_documents():
    if require_role("user"):
        return redirect("/")

    if request.method == "POST":
        file = request.files.get("document")

        if file and file.filename:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)

            if size > 5 * 1024 * 1024:
                return "File must be less than 5MB"

            filename = f"{datetime.now().timestamp()}_{file.filename}"
            filepath = f"uploads/documents/{filename}"

            file.save(filepath)

            conn = get_conn()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO documents (user_id, file_path)
                VALUES (%s, %s)
            """, (1, filepath))

            conn.commit()
            cur.close()
            conn.close()

        return redirect("/user-dashboard")

    return render_page("users/upload_documents.html", "Upload Documents", "upload_documents")


@app.route("/user-profile", methods=["GET", "POST"])
def user_profile():
    if require_role("user"):
        return redirect("/")

    if request.method == "POST":
        session["profile"] = {
            **get_profile(),
            "mobile": request.form["mobile"],
            "email": request.form["email"],
            "location": request.form["location"]
        }
        return redirect("/user-dashboard")

    return render_page("users/user_profile.html", "User Profile", "user_profile")


# ================= ADMIN ACCESS (FIX ADDED) =================

@app.route("/master")
def master():
    if require_role("admin"):
        return redirect("/")
    return render_page("master.html", "Field Data", "master")


@app.route("/new_entry")
def new_entry():
    if require_role("admin"):
        return redirect("/")
    return render_page("new_entry.html", "New Entry", "new_entry")


@app.route("/outward-entry")
def outward_entry():
    if require_role("admin"):
        return redirect("/")
    return render_page("outward_entry.html", "Outward Entry", "outward_entry")


@app.route("/dashboard-summary")
def dashboard_summary():
    if require_role("admin"):
        return redirect("/")
    return render_page("dashboard.html", "Dashboard", "dashboard")


@app.route("/tracking")
def tracking():
    if require_role("admin"):
        return redirect("/")
    return render_page("tracking.html", "Tracking", "tracking", frameless_page=True)


@app.route("/warehouse-inventory")
def warehouse_inventory():
    if require_role("admin"):
        return redirect("/")
    return render_page("warehouse_inventory.html", "Warehouse Inventory", "inventory")


@app.route("/report")
def report():
    if require_role("admin"):
        return redirect("/")
    return render_page("report.html", "Report", "report")


@app.route("/admin")
def admin():
    if require_role("admin"):
        return redirect("/")
    return render_page("admin_create.html", "Create User", "admin_create")


@app.route("/view-users")
def view_users():
    if require_role("admin"):
        return redirect("/")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, COALESCE(name, username) AS display_name, username, role
        FROM users
        WHERE role IN ('ground', 'user')
        ORDER BY role, username
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    ground_users = [row for row in rows if row[3] == "ground"]
    individual_users = [row for row in rows if row[3] == "user"]

    return render_page(
        "view_users.html",
        "View Users",
        "admin_view",
        ground_users=ground_users,
        individual_users=individual_users,
        password_updated=request.args.get("password_updated") == "1",
        updated_username=request.args.get("username", "")
    )


@app.route("/reset-user-password", methods=["POST"])
def reset_user_password():
    if require_role("admin"):
        return redirect("/")

    user_id = request.form.get("user_id")
    username = request.form.get("username", "")
    new_password = (request.form.get("new_password") or "").strip()

    if not user_id or not new_password:
        return redirect("/view-users")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password=%s WHERE id=%s AND role IN ('ground', 'user')",
        (new_password, user_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(f"/view-users?password_updated=1&username={username}")


@app.route("/setting", methods=["GET", "POST"])
def setting():
    if require_role("admin"):
        return redirect("/")

    if request.method == "POST":
        session["app_settings"] = {
            "default_report_type": request.form.get("default_report_type", "inward"),
            "report_rows": request.form.get("report_rows", "50"),
            "export_format": request.form.get("export_format", "csv"),
            "notify_email": request.form.get("notify_email") == "on",
            "notify_dashboard": request.form.get("notify_dashboard") == "on",
            "compact_tables": request.form.get("compact_tables") == "on",
            "approval_lock": request.form.get("approval_lock") == "on",
            "show_totals": request.form.get("show_totals") == "on"
        }
        session.modified = True
        return redirect("/setting?saved=1")

    return render_page(
        "setting.html",
        "Setting",
        "setting",
        settings_saved=request.args.get("saved") == "1"
    )


@app.route("/setting/reset", methods=["POST"])
def reset_setting():
    if require_role("admin"):
        return redirect("/")

    session["app_settings"] = default_app_settings()
    session.modified = True
    return redirect("/setting?reset=1")



# ====basic info =====
# ====basic info =====
@app.route("/add-basic-info", methods=["POST"])
def add_basic_info():
    if require_role("admin"):
        return redirect("/")

    data = request.json
    bootstrap_real_data()

    conn = get_conn()
    cur = conn.cursor()

    values = (
        data.get("sr_no"),
        data.get("atn"),
        data.get("shifting"),
        data.get("original_wh"),
        data.get("date") or None,
        data.get("warehouse"),
        data.get("shipment_type"),
        data.get("dispatch_type"),

        data.get("in_doc_no"),
        data.get("order_no"),
        data.get("dc_no"),
        data.get("challan_date") or None,

        data.get("oem"),
        data.get("po_no"),
        data.get("po_name"),

        data.get("invoice_no"),
        data.get("invoice_date") or None,

        data.get("item_code"),
        data.get("description"),
        data.get("qty"),
        data.get("physical_qty"),
        data.get("unit"),

        data.get("rate"),
        data.get("total_value"),
        data.get("taxable_value"),

        data.get("tsc"),
        data.get("discount"),
        data.get("freight"),

        data.get("cgst"),
        data.get("sgst"),
        data.get("grand_total"),

        data.get("unloading"),
        data.get("transport"),
        data.get("vehicle"),
        data.get("lr_no"),
        data.get("lr_date") or None,

        data.get("pkgs_qty"),
        data.get("delivery_date") or None,
        data.get("mode"),

        data.get("reporting_time"),
        data.get("unloading_time"),
        data.get("wh_remark"),

        data.get("eway_bill"),
        data.get("shipment_type2"),

        data.get("inspection_date") or None,
        data.get("inspection_person"),

        data.get("pm_update_date") or None,
        data.get("doc_remark"),
        data.get("pm_update_by"),
        data.get("reupload"),
        data.get("reupload_reason"),
        data.get("pm_remark"),
        data.get("inspection_status"),
        data.get("pm_submit_date") or None,

        data.get("approved_dpm") or None,
        data.get("approved_tpa") or None
    )

    placeholders = ", ".join(["%s"] * len(values))

    try:
        cur.execute(f"""
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
            approved_dpm, approved_tpa, source_tag
        )
        VALUES ({placeholders})
        """, values + ("manual",))

        conn.commit()
    except Exception as exc:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"message": "Save failed", "error": str(exc)}), 500

    cur.close()
    conn.close()

    return jsonify({"message": "Saved successfully"})


@app.route("/basic-info")
def get_basic_info():
    if require_role("admin"):
        return redirect("/")

    return jsonify([prepare_inward_record(record) for record in get_inward_report_records(limit=20)])


@app.route("/add-outward-info", methods=["POST"])
def add_outward_info():
    if require_role("admin"):
        return redirect("/")

    data = request.json or {}
    bootstrap_real_data()

    conn = get_conn()
    cur = conn.cursor()

    try:
        ensure_outward_table(cur)
        cur.execute(
            """
            INSERT INTO outward_info (
                out_sr_no, out_atn, out_month, out_warehouse, out_shipment_type, out_dispatch_type,
                out_in_doc_no, out_dc_no, out_dc_date, out_vendor_name, out_gp_location, out_block, out_dist,
                out_item_code, out_description, out_qty, out_physical_qty, out_unit, out_rate_per_unit,
                out_total_value, out_taxable_value, out_tsc, out_discount, out_freight_charge, out_total,
                out_cgst, out_sgst, out_grand_total, out_transport_name, out_vehicle_no, out_pkgs_qty,
                out_dispatched_date, out_mode_of_delivery, out_reporting_time, out_loading_time, out_remark,
                out_ug_aerial, out_frt, source_tag
            )
            VALUES ({})
            """.format(", ".join(["%s"] * 39)),
            outward_db_values(data) + ("manual",)
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"message": "Save failed", "error": str(exc)}), 500

    cur.close()
    conn.close()

    return jsonify({"message": "Saved successfully"})


@app.route("/outward-info")
def outward_info():
    if require_role("admin"):
        return redirect("/")

    return jsonify([prepare_outward_record(record) for record in get_outward_report_records(limit=20)])


@app.route("/report-data")
def report_data():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    report_type = request.args.get("type", "inward").lower()
    year_value = request.args.get("year")
    year = int(year_value) if year_value and year_value.isdigit() else None
    limit_value = request.args.get("limit", "100")
    offset_value = request.args.get("offset", "0")
    search_term = request.args.get("search", "")
    search_field = request.args.get("field", "all")

    try:
        limit = max(25, min(200, int(limit_value)))
    except ValueError:
        limit = 100

    try:
        offset = max(0, int(offset_value))
    except ValueError:
        offset = 0

    rows, total_count = get_report_page(
        report_type=report_type,
        year=year,
        limit=limit,
        offset=offset,
        search_term=search_term,
        search_field=search_field
    )

    if report_type == "outward":
        data = [prepare_outward_record(record) for record in rows]
    else:
        data = [prepare_inward_record(record) for record in rows]

    return jsonify({
        "data": data,
        "total_count": total_count,
        "page_size": limit,
        "offset": offset
    })


@app.route("/report-years")
def report_years():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    report_type = request.args.get("type", "inward").lower()
    return jsonify(get_report_years(report_type))


@app.route("/warehouse-inventory-data")
def warehouse_inventory_data():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    return jsonify(get_warehouse_inventory_payload())


@app.route("/dashboard-data")
def dashboard_data():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    return jsonify(get_dashboard_payload())




# ================= COMMON PAGES (FIX) =================

@app.route("/my-account", methods=["GET", "POST"])
def my_account():
    if require_login():
        return redirect("/")

    if request.method == "POST":
        profile = {
            **get_profile(),
            "name": request.form.get("name", "").strip() or get_profile().get("name"),
            "designation": request.form.get("designation", "").strip() or get_profile().get("designation"),
            "employee_code": request.form.get("employee_code", "").strip() or get_profile().get("employee_code"),
            "location": request.form.get("location", "").strip() or get_profile().get("location"),
            "mobile": request.form.get("mobile", "").strip() or get_profile().get("mobile"),
            "email": request.form.get("email", "").strip() or get_profile().get("email"),
            "gender": request.form.get("gender", "").strip() or get_profile().get("gender"),
            "blood_group": request.form.get("blood_group", "").strip() or get_profile().get("blood_group")
        }

        uploaded_file = request.files.get("photo")
        if uploaded_file and uploaded_file.filename:
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(uploaded_file.filename)}"
            relative_path = f"images/{filename}"
            absolute_path = os.path.join(BASE_DIR, "uploads", "images", filename)
            uploaded_file.save(absolute_path)
            profile["photo_name"] = uploaded_file.filename
            profile["photo_path"] = relative_path

        session["profile"] = profile
        session.modified = True
        return redirect("/my-account?saved=1")

    return render_page(
        "my_account.html",
        "My Account",
        "account",
        account_saved=request.args.get("saved") == "1",
        frameless_page=True
    )


@app.route("/dashboard")
def dashboard_redirect():
    role = session.get("role")

    if role == "admin":
        return redirect("/admin-dashboard")
    elif role == "user":
        return redirect("/user-dashboard")
    elif role == "ground":
        return redirect("/ground-dashboard")

    return redirect("/")


# ================= LOGOUT =================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN =================

if __name__ == "__main__":
    app.run(debug=True)
