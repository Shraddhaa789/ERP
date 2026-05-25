import os
import json
import re
import zlib
from uuid import uuid4
from pathlib import Path
import psycopg2
from psycopg2 import pool
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session
from datetime import date, datetime, time
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = "secret123"

def format_qty(value):
    if value in (None, ""):
        return "0"
    try:
        val = float(value)
        if val.is_integer():
            return f"{int(val):,}"
        return f"{val:,.2f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return str(value)

app.jinja_env.filters['format_qty'] = format_qty

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Hardcoded uploads directory as per user request
UPLOADS_BASE = r"D:\ERP_NEW\ERP\ERP APP\uploads"
os.makedirs(os.path.join(UPLOADS_BASE, "images"), exist_ok=True)
os.makedirs(os.path.join(UPLOADS_BASE, "documents"), exist_ok=True)

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


def upload_disk_path(relative_path):
    if not relative_path:
        return None
    clean_path = str(relative_path).replace("\\", "/").lstrip("/")
    if clean_path.startswith("uploads/"):
        clean_path = clean_path[len("uploads/"):]
    return os.path.normpath(os.path.join(UPLOADS_BASE, clean_path))


def upload_exists(relative_path):
    path = upload_disk_path(relative_path)
    return bool(path and os.path.isfile(path) and os.path.getsize(path) > 0)


def existing_upload_path(relative_path):
    clean_path = str(relative_path or "").replace("\\", "/").lstrip("/")
    if clean_path.startswith("uploads/"):
        clean_path = clean_path[len("uploads/"):]

    candidates = [
        upload_disk_path(clean_path),
        os.path.normpath(os.path.join(BASE_DIR, "uploads", clean_path))
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return candidates[0]


def delete_upload_file(relative_path):
    candidates = []
    primary_path = upload_disk_path(relative_path)
    if primary_path:
        candidates.append(primary_path)
    if relative_path:
        clean_path = str(relative_path).replace("\\", "/").lstrip("/")
        if clean_path.startswith("uploads/"):
            clean_path = clean_path[len("uploads/"):]
        candidates.append(os.path.normpath(os.path.join(BASE_DIR, "uploads", clean_path)))

    for path in dict.fromkeys(candidates):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass


def save_document_upload(file, filename):
    relative_path = f"documents/{filename}"
    primary_path = os.path.join(UPLOADS_BASE, "documents", filename)
    fallback_path = os.path.join(BASE_DIR, "uploads", "documents", filename)

    for absolute_path in (primary_path, fallback_path):
        try:
            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
            file.save(absolute_path)
            return relative_path
        except OSError:
            file.seek(0)

    raise PermissionError("Unable to save document upload")


def decode_pdf_literal(value):
    result = []
    escaped = False
    for char in value:
        if escaped:
            result.append({
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "b": "\b",
                "f": "\f",
                "\\": "\\",
                "(": "(",
                ")": ")"
            }.get(char, char))
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    return "".join(result)


def extract_pdf_text(raw):
    chunks = []

    for match in re.finditer(rb"<<(?P<dict>.*?)>>\s*stream\r?\n?(?P<body>.*?)\r?\n?endstream", raw, re.S):
        stream_dict = match.group("dict")
        body = match.group("body").strip(b"\r\n")

        if b"FlateDecode" in stream_dict:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                continue

        text = body.decode("latin-1", errors="ignore")
        chunks.extend(decode_pdf_literal(item) for item in re.findall(r"\((.*?)(?<!\\)\)", text, re.S))

        for hex_value in re.findall(r"<([0-9A-Fa-f\s]{6,})>", text):
            try:
                data = bytes.fromhex(re.sub(r"\s+", "", hex_value))
            except ValueError:
                continue
            for encoding in ("utf-16-be", "latin-1"):
                decoded = data.decode(encoding, errors="ignore").strip()
                if decoded:
                    chunks.append(decoded)
                    break

    return " ".join(chunks)


def extract_document_text(file_path, original_filename=""):
    chunks = [original_filename or ""]
    try:
        with open(file_path, "rb") as fh:
            raw = fh.read(2 * 1024 * 1024)
    except OSError:
        return " ".join(chunks)

    decoded = raw.decode("utf-8", errors="ignore")
    if not decoded.strip():
        decoded = raw.decode("latin-1", errors="ignore")

    if raw.startswith(b"%PDF") or str(original_filename).lower().endswith(".pdf"):
        chunks.append(extract_pdf_text(raw))

    # This catches useful text from plain files and many text-based PDFs.
    printable_runs = re.findall(r"[A-Za-z0-9][A-Za-z0-9\s./:_#,&()\-]{2,}", decoded)
    chunks.extend(printable_runs[:1200])
    return " ".join(chunks)


def document_match_tokens(text):
    tokens = set()
    normalized = str(text or "").upper()
    labels = [
        r"INVOICE\s*(?:NO|NUMBER|#|:|-)\s*([A-Z0-9./_-]{3,})",
        r"INV\s*(?:NO|NUMBER|#|:|-)\s*([A-Z0-9./_-]{3,})",
        r"DC\s*(?:NO|NUMBER|#|:|-)\s*([A-Z0-9./_-]{3,})",
        r"CHALLAN\s*(?:NO|NUMBER|#|:|-)\s*([A-Z0-9./_-]{3,})",
        r"ORDER\s*(?:NO|NUMBER|#|:|-)\s*([A-Z0-9./_-]{3,})",
        r"DOCUMENT\s*(?:NO|NUMBER|#|:|-)\s*([A-Z0-9./_-]{3,})"
    ]
    for pattern in labels:
        for value in re.findall(pattern, normalized):
            cleaned = value.strip("._-/")
            if len(cleaned) >= 3:
                tokens.add(cleaned)

    for token in re.findall(r"[A-Z0-9][A-Z0-9./_-]{3,}", normalized):
        cleaned = token.strip("._-/")
        if len(cleaned) >= 4 and cleaned not in {"INVOICE", "CHALLAN", "DOCUMENT", "REPORT", "WAREHOUSE"}:
            tokens.add(cleaned)
    return sorted(tokens, key=len, reverse=True)[:80]


def compact_match_value(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def clean_db_text(value, limit=None):
    text = str(value or "").replace("\x00", "")
    text = "".join(char for char in text if char == "\n" or char == "\t" or ord(char) >= 32)
    if limit is not None:
        return text[:limit]
    return text


def report_table_match_config(report_type):
    report_type = normalize_report_type(report_type)
    if report_type == "outward":
        return {
            "table": "outward_info",
            "fields": ["out_dc_no", "out_in_doc_no", "out_item_code", "out_vendor_name", "out_warehouse", "out_description"],
            "strong_fields": {"out_dc_no", "out_in_doc_no"}
        }
    return {
        "table": "basic_info",
        "fields": ["invoice_no", "dc_no", "order_no", "in_doc_no", "item_code", "oem", "warehouse", "description"],
        "strong_fields": {"invoice_no", "dc_no", "order_no", "in_doc_no"}
    }


def find_matching_report_entries(report_type, scanned_text, original_filename=""):
    report_type = normalize_report_type(report_type)
    config = report_table_match_config(report_type)
    table_name = config["table"]
    fields = config["fields"]
    strong_fields = config["strong_fields"]
    compact_text = compact_match_value(scanned_text)
    tokens = document_match_tokens(scanned_text)

    # Clean original filename to get candidate matching strings
    filename_candidates = []
    if original_filename:
        # Strip extension if present
        base_name, _ = os.path.splitext(original_filename)
        # Convert base name to compact value
        compact_base = compact_match_value(base_name)
        if len(compact_base) >= 4:
            filename_candidates.append(compact_base)
        # Also include the raw original filename compact value
        compact_raw = compact_match_value(original_filename)
        if len(compact_raw) >= 4:
            filename_candidates.append(compact_raw)

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT id, {", ".join(fields)}
            FROM {table_name}
            ORDER BY id DESC
            """
        )
        all_rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    compact_matches = []
    for row in all_rows:
        row_id = row[0]
        values = dict(zip(fields, row[1:]))
        score = 0
        terms = []
        seen_compact_values = set()
        for field, value in values.items():
            compact_value = compact_match_value(value)
            if len(compact_value) < 4 or compact_value in seen_compact_values:
                continue
            seen_compact_values.add(compact_value)
            
            matched = False
            # Check 1: Is the compact value in the scanned document text?
            if compact_value in compact_text:
                matched = True
            
            # Check 2: Direct match against the filename candidates (flexible comparison)
            if not matched and filename_candidates:
                for candidate in filename_candidates:
                    if compact_value == candidate:
                        matched = True
                        break
                    elif len(compact_value) >= 5 and compact_value in candidate:
                        matched = True
                        break
                    elif len(candidate) >= 5 and candidate in compact_value:
                        matched = True
                        break

            if matched:
                score += (len(compact_value) * 10) if field in strong_fields else min(len(compact_value), 10)
                terms.append(str(value))
        if score >= 40:
            compact_matches.append((row_id, score, terms))

    if compact_matches:
        best_score = max(score for _, score, _ in compact_matches)
        best_ids = [row_id for row_id, score, _ in compact_matches if score == best_score]
        best_terms = []
        for _, score, terms in compact_matches:
            if score == best_score:
                best_terms.extend(terms)
        return best_ids, sorted(set(best_terms))[:12]


    if not tokens:
        return [], []

    exactish_tokens = [token for token in tokens if any(ch.isdigit() for ch in token)][:30]
    if not exactish_tokens:
        exactish_tokens = tokens[:20]

    conditions = []
    params = []
    for token in exactish_tokens:
        field_checks = " OR ".join([f"COALESCE(CAST({field} AS TEXT), '') ILIKE %s" for field in fields])
        conditions.append(f"({field_checks})")
        params.extend([f"%{token}%"] * len(fields))

    if not conditions:
        return [], []

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT id, {", ".join(fields)}
            FROM {table_name}
            WHERE {" OR ".join(conditions)}
            LIMIT 200
            """,
            tuple(params)
        )
        candidates = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    best_id = None
    best_score = 0
    best_terms = []
    scored = []
    for row in candidates:
        candidate_id = row[0]
        values = [str(value or "").upper() for value in row[1:]]
        score = 0
        terms = []
        for token in tokens:
            if any(token and token in value for value in values):
                score += 3 if any(ch.isdigit() for ch in token) else 1
                terms.append(token)
        if score > best_score:
            best_id = candidate_id
            best_score = score
            best_terms = terms[:12]
        if score >= 3:
            scored.append((candidate_id, score, terms[:12]))

    if best_score < 3:
        return [], []

    best_ids = [candidate_id for candidate_id, score, _ in scored if score == best_score]
    return best_ids or [best_id], best_terms


def find_matching_report_entry(report_type, scanned_text):
    ids, terms = find_matching_report_entries(report_type, scanned_text)
    return (ids[0] if ids else None), terms


def default_profile(role="admin"):
    if role == "ground":
        return {
            "name": "Ground Team Lead",
            "designation": "GROUND OPERATIONS",
            "employee_code": "GT-001",
            "location": "Site Office, Maharashtra",
            "mobile": "Not Provided",
            "email": "ground@erp.com",
            "gender": "Not Provided",
            "blood_group": "Not Provided",
            "photo_name": "No file selected",
            "photo_path": ""
        }
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


db_pool = pool.SimpleConnectionPool(
    1, 20,
    host="localhost",
    database="construction_erp",
    user="postgres",
    password="pass123"
)

class PooledConnection:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)
        
    def commit(self):
        self._conn.commit()
        
    def rollback(self):
        self._conn.rollback()
        
    def close(self):
        self._pool.putconn(self._conn)

def get_conn():
    return PooledConnection(db_pool.getconn(), db_pool)


def require_login():
    if "user" not in session:
        return redirect("/")
    return None


def require_role(role):
    if session.get("role") != role:
        return redirect("/")
    return None


def get_profile():
    role = session.get("role", "admin")
    profile = default_profile(role)
    
    username = session.get("user")
    if username:
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT name, designation, employee_code, location, mobile, email, gender, blood_group, photo_name, photo_path
                FROM users
                WHERE LOWER(username) = LOWER(%s)
            """, (username,))
            row = cur.fetchone()
            if row:
                db_profile = {
                    "name": row[0] if row[0] is not None else profile["name"],
                    "designation": row[1] if row[1] is not None else profile["designation"],
                    "employee_code": row[2] if row[2] is not None else profile["employee_code"],
                    "location": row[3] if row[3] is not None else profile["location"],
                    "mobile": row[4] if row[4] is not None else profile["mobile"],
                    "email": row[5] if row[5] is not None else profile["email"],
                    "gender": row[6] if row[6] is not None else profile["gender"],
                    "blood_group": row[7] if row[7] is not None else profile["blood_group"],
                    "photo_name": row[8] if row[8] is not None else profile["photo_name"],
                    "photo_path": row[9] if row[9] is not None else profile["photo_path"]
                }
                profile.update(db_profile)
        except Exception as e:
            print(f"Error loading profile from DB: {e}")
        finally:
            cur.close()
            conn.close()

    profile.update(session.get("profile", {}))
    return profile


def save_profile(username, profile):
    if not username:
        return
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users
            SET name = %s,
                designation = %s,
                employee_code = %s,
                location = %s,
                mobile = %s,
                email = %s,
                gender = %s,
                blood_group = %s,
                photo_name = %s,
                photo_path = %s
            WHERE LOWER(username) = LOWER(%s)
        """, (
            profile.get("name"),
            profile.get("designation"),
            profile.get("employee_code"),
            profile.get("location"),
            profile.get("mobile"),
            profile.get("email"),
            profile.get("gender"),
            profile.get("blood_group"),
            profile.get("photo_name"),
            profile.get("photo_path"),
            username
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error saving profile to DB: {e}")
    finally:
        cur.close()
        conn.close()


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


def load_material_category_map():
    path = os.path.join(BASE_DIR, "database", "material_categories.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


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
    cur.execute("SELECT warehouse, description, inward_qty, inward_mtr, outward_qty, outward_mtr, phy_stock_qty, phy_stock_mtr FROM inventory_stock")
    for warehouse, description, inward_qty, inward_mtr, outward_qty, outward_mtr, phy_qty, phy_mtr in cur.fetchall():
        key = (warehouse, description)
        if key not in inventory_map:
            inventory_map[key] = {
                "warehouse": warehouse,
                "description": description,
                "inward_qty": 0.0, "inward_mtr": 0.0, "inward_unit_km": 0.0,
                "outward_qty": 0.0, "outward_mtr": 0.0, "outward_unit_km": 0.0,
                "phy_stock_qty": 0.0, "phy_stock_mtr": 0.0, "phy_stock_unit_km": 0.0
            }
        
        r = inventory_map[key]
        r["inward_qty"] += float(inward_qty or 0)
        r["inward_mtr"] += float(inward_mtr or 0)
        r["inward_unit_km"] = r["inward_mtr"] / 1000.0
        
        r["outward_qty"] += float(outward_qty or 0)
        r["outward_mtr"] += float(outward_mtr or 0)
        r["outward_unit_km"] = r["outward_mtr"] / 1000.0
        
        r["phy_stock_qty"] += float(phy_qty or 0)
        r["phy_stock_mtr"] += float(phy_mtr or 0)
        r["phy_stock_unit_km"] = r["phy_stock_mtr"] / 1000.0

    cur.close()
    conn.close()

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

    inventory_source = "summary_plus_live_delta"

    return {
        "rows": rows,
        "warehouses": warehouses,
        "materials": materials,
        "source": inventory_source,
        "summary": {
            "row_count": len(rows),
            "warehouse_count": len(warehouses),
            "material_count": len(materials),
            "total_physical_qty": total_physical_qty,
            "source": inventory_source
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


def parse_float_value(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def get_current_user_id(default=1):
    if request.is_json:
        payload = request.json or {}
        user_id = payload.get("user_id")
    else:
        user_id = request.form.get("user_id")
    if user_id and str(user_id).isdigit():
        return int(user_id)

    username = session.get("user")
    if not username:
        return default

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else default
    except Exception:
        return default
    finally:
        cur.close()
        conn.close()


def collect_survey_material_items(form):
    raw_items = form.get("material_items") or form.get("items") or form.get("materials")
    if raw_items:
        try:
            parsed_items = json.loads(raw_items)
            if isinstance(parsed_items, list):
                return [
                    {
                        "item_index": int(item.get("item_index") or index + 1),
                        "category": item.get("category") or item.get("material_category") or "",
                        "sub_category": item.get("sub_category") or item.get("categorised_items") or "",
                        "quantity": item.get("quantity") or "",
                        "unit": item.get("unit") or item.get("uom") or "",
                        "description": item.get("description") or ""
                    }
                    for index, item in enumerate(parsed_items)
                    if isinstance(item, dict)
                ]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    categories = form.getlist("category[]") or form.getlist("material_category[]")
    sub_categories = form.getlist("sub_category[]") or form.getlist("categorised_items[]")
    quantities = form.getlist("quantity[]")
    units = form.getlist("unit[]") or form.getlist("uom[]")
    descriptions = form.getlist("description[]")

    max_count = max(len(categories), len(sub_categories), len(quantities), len(units), len(descriptions), 0)
    if max_count:
        items = []
        for index in range(max_count):
            items.append({
                "item_index": index + 1,
                "category": categories[index] if index < len(categories) else "",
                "sub_category": sub_categories[index] if index < len(sub_categories) else "",
                "quantity": quantities[index] if index < len(quantities) else "",
                "unit": units[index] if index < len(units) else "",
                "description": descriptions[index] if index < len(descriptions) else ""
            })
        return items

    return [{
        "item_index": 1,
        "category": form.get("category") or form.get("material_category", ""),
        "sub_category": form.get("sub_category") or form.get("categorised_items", ""),
        "quantity": form.get("quantity", ""),
        "unit": form.get("unit") or form.get("uom", ""),
        "description": form.get("description", "")
    }]


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
    if "id" in record:
        prepared["id"] = serialize_value(record.get("id"))
    if "doc_count" in record:
        prepared["doc_count"] = serialize_value(record.get("doc_count"))
    if "doc_url" in record and record.get("doc_url"):
        prepared["doc_url"] = serialize_value(record.get("doc_url"))

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
    if "id" in record:
        prepared["id"] = serialize_value(record.get("id"))
    if "doc_count" in record:
        prepared["doc_count"] = serialize_value(record.get("doc_count"))
    if "doc_url" in record and record.get("doc_url"):
        prepared["doc_url"] = serialize_value(record.get("doc_url"))
    return prepared


def ensure_inventory_stock_table(cur):
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS inventory_stock (
            warehouse TEXT,
            description TEXT,
            inward_qty DOUBLE PRECISION DEFAULT 0,
            inward_mtr DOUBLE PRECISION DEFAULT 0,
            outward_qty DOUBLE PRECISION DEFAULT 0,
            outward_mtr DOUBLE PRECISION DEFAULT 0,
            phy_stock_qty DOUBLE PRECISION DEFAULT 0,
            phy_stock_mtr DOUBLE PRECISION DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (warehouse, description)
        )
        '''
    )

def recalculate_warehouse_item(warehouse, description):
    if not warehouse or not description:
        return
        
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
    cur.execute(f"""
        SELECT SUM({inward_qty_sql}), SUM(CASE WHEN ABS({inward_unit_sql} - {inward_qty_sql}) > 0.000001 THEN {inward_unit_sql} ELSE 0 END)
        FROM basic_info WHERE source_tag = 'manual' AND BTRIM(warehouse) = %s AND BTRIM(description) = %s
    """, (warehouse.strip(), description.strip()))
    inward_res = cur.fetchone()
    in_qty = float(inward_res[0] or 0)
    in_mtr = float(inward_res[1] or 0)
    
    outward_qty_sql = numeric_sql("out_qty")
    outward_unit_sql = numeric_sql("out_unit")
    cur.execute(f"""
        SELECT SUM({outward_qty_sql}), SUM(CASE WHEN ABS({outward_unit_sql} - {outward_qty_sql}) > 0.000001 THEN {outward_unit_sql} ELSE 0 END)
        FROM outward_info WHERE source_tag = 'manual' AND BTRIM(out_warehouse) = %s AND BTRIM(out_description) = %s
    """, (warehouse.strip(), description.strip()))
    outward_res = cur.fetchone()
    out_qty = float(outward_res[0] or 0)
    out_mtr = float(outward_res[1] or 0)
    
    phy_qty = in_qty - out_qty
    phy_mtr = in_mtr - out_mtr
    
    cur.execute("""
        INSERT INTO inventory_stock (warehouse, description, inward_qty, inward_mtr, outward_qty, outward_mtr, phy_stock_qty, phy_stock_mtr, last_updated)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (warehouse, description) DO UPDATE SET
            inward_qty = EXCLUDED.inward_qty, inward_mtr = EXCLUDED.inward_mtr,
            outward_qty = EXCLUDED.outward_qty, outward_mtr = EXCLUDED.outward_mtr,
            phy_stock_qty = EXCLUDED.phy_stock_qty, phy_stock_mtr = EXCLUDED.phy_stock_mtr,
            last_updated = EXCLUDED.last_updated
    """, (warehouse.strip(), description.strip(), in_qty, in_mtr, out_qty, out_mtr, phy_qty, phy_mtr))
    conn.commit()
    cur.close()
    conn.close()

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


def ensure_user_survey_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS survey_submissions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            warehouse_name VARCHAR(255),
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            gps_accuracy_meters DOUBLE PRECISION,
            address_line TEXT,
            pincode VARCHAR(20),
            district VARCHAR(100),
            taluka VARCHAR(100),
            captured_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute("ALTER TABLE survey_submissions ADD COLUMN IF NOT EXISTS photo_path TEXT")
    cur.execute("ALTER TABLE survey_submissions ADD COLUMN IF NOT EXISTS captured_at TIMESTAMP NOT NULL DEFAULT NOW()")
    cur.execute("ALTER TABLE survey_submissions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()")
    cur.execute("ALTER TABLE survey_submissions ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP DEFAULT NOW()")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_survey_user_id ON survey_submissions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_survey_captured ON survey_submissions(captured_at DESC)")

    # Ensure media_registry table exists for multiple photo support
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS media_registry (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            media_type VARCHAR(50) DEFAULT 'Photo',
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            survey_id INTEGER REFERENCES survey_submissions(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_media_survey_id ON media_registry(survey_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_media_user_id ON media_registry(user_id)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS survey_material_items (
            id SERIAL PRIMARY KEY,
            survey_id INTEGER NOT NULL REFERENCES survey_submissions(id) ON DELETE CASCADE,
            item_index SMALLINT NOT NULL DEFAULT 1,
            category VARCHAR(100),
            sub_category VARCHAR(255),
            quantity VARCHAR(50),
            unit VARCHAR(50),
            description TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute("ALTER TABLE survey_material_items ADD COLUMN IF NOT EXISTS unit VARCHAR(50)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_material_survey ON survey_material_items(survey_id)")
    cur.execute("DROP VIEW IF EXISTS vw_survey_full")
    cur.execute(
        """
        CREATE VIEW vw_survey_full AS
        SELECT
            s.id AS survey_id,
            s.user_id,
            s.warehouse_name,
            s.latitude,
            s.longitude,
            s.gps_accuracy_meters,
            s.address_line,
            s.pincode,
            s.district,
            s.taluka,
            s.captured_at,
            m.item_index,
            m.category,
            m.sub_category,
            m.quantity,
            m.unit,
            m.description AS item_description
        FROM survey_submissions s
        LEFT JOIN survey_material_items m ON m.survey_id = s.id
        ORDER BY s.captured_at DESC, m.item_index ASC
        """
    )
    cur.execute("SELECT to_regclass('public.user_survey_data')")
    legacy_table = cur.fetchone()[0]
    if legacy_table:
        cur.execute("SELECT COUNT(*) FROM survey_submissions")
        survey_count = cur.fetchone()[0]
        if survey_count == 0:
            print("Migrating legacy survey data...")
            cur.execute(
                """
                INSERT INTO survey_submissions (
                    user_id, warehouse_name, latitude, longitude, gps_accuracy_meters,
                    captured_at, created_at, photo_path
                )
                SELECT
                    1,
                    warehouse_name,
                    CASE WHEN COALESCE(latitude, '') ~ '^[-+]?\\d*\\.?\\d+$' THEN latitude::DOUBLE PRECISION ELSE NULL END,
                    CASE WHEN COALESCE(longitude, '') ~ '^[-+]?\\d*\\.?\\d+$' THEN longitude::DOUBLE PRECISION ELSE NULL END,
                    CASE WHEN COALESCE(gps_accuracy, '') ~ '^[-+]?\\d*\\.?\\d+$' THEN gps_accuracy::DOUBLE PRECISION ELSE NULL END,
                    COALESCE(created_at, NOW()),
                    COALESCE(created_at, NOW()),
                    photo_path
                FROM user_survey_data
                ORDER BY id
                RETURNING id
                """
            )
            new_survey_ids = [row[0] for row in cur.fetchall()]
            cur.execute(
                """
                SELECT material_category, categorised_items, quantity, description
                FROM user_survey_data
                ORDER BY id
                """
            )
            legacy_items = cur.fetchall()
            for survey_id, item in zip(new_survey_ids, legacy_items):
                cur.execute(
                    """
                    INSERT INTO survey_material_items (
                        survey_id, item_index, category, sub_category, quantity, unit, description
                    )
                    VALUES (%s, 1, %s, %s, %s, %s, %s)
                    """,
                    (survey_id, item[0], item[1], item[2], "", item[3])
                )
            
            # After successful migration, drop the legacy table to prevent re-migration
            cur.execute("DROP TABLE user_survey_data")
            print("Legacy survey data migrated and table dropped.")

def ensure_route_requests_table(cur):

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS route_requests (
            id SERIAL PRIMARY KEY,
            transfer_id TEXT,
            source_warehouse TEXT,
            destination_warehouse TEXT,
            material_description TEXT,
            quantity TEXT,
            vehicle_type TEXT,
            remarks TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("ALTER TABLE route_requests ADD COLUMN IF NOT EXISTS admin_note TEXT")


def ensure_documents_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def ensure_report_documents_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS report_documents (
            id SERIAL PRIMARY KEY,
            report_type VARCHAR(20) NOT NULL,
            report_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            original_filename TEXT,
            uploaded_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("ALTER TABLE report_documents ADD COLUMN IF NOT EXISTS scanned_text TEXT")
    cur.execute("ALTER TABLE report_documents ADD COLUMN IF NOT EXISTS matched_terms TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_report_documents_entry ON report_documents(report_type, report_id)")


def ensure_work_uploads_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS work_uploads (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            location TEXT,
            material TEXT,
            quantity TEXT,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


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
        ensure_route_requests_table(cur)
        ensure_user_survey_table(cur)
        ensure_inventory_stock_table(cur)
        ensure_documents_table(cur)
        ensure_report_documents_table(cur)
        ensure_work_uploads_table(cur)
        
        # Ensure users table has soft delete, warehouse, and profile support
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS warehouse TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS designation TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_code TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS location TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS blood_group TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_name TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_path TEXT")


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
        "compact_tables": False,
        "show_analytics": True,
        "hide_map": False
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


def get_report_page(report_type, year=None, limit=100, offset=0, search_term="", search_field="all", category="", sub_category="", material=""):
    bootstrap_real_data()

    report_type = "outward" if report_type == "outward" else "inward"
    is_outward = report_type == "outward"

    select_columns = """
        id,
        (SELECT COUNT(*) FROM report_documents rd WHERE rd.report_type = 'outward' AND rd.report_id = outward_info.id) AS doc_count,
        (SELECT '/uploads/' || rd.file_path FROM report_documents rd WHERE rd.report_type = 'outward' AND rd.report_id = outward_info.id ORDER BY rd.created_at DESC, rd.id DESC LIMIT 1) AS doc_url,
        out_sr_no, out_atn, out_month, out_warehouse, out_shipment_type, out_dispatch_type,
        out_in_doc_no, out_dc_no, out_dc_date, out_vendor_name, out_gp_location, out_block, out_dist,
        out_item_code, out_description, out_qty, out_physical_qty, out_unit, out_rate_per_unit,
        out_total_value, out_taxable_value, out_tsc, out_discount, out_freight_charge, out_total,
        out_cgst, out_sgst, out_grand_total, out_transport_name, out_vehicle_no, out_pkgs_qty,
        out_dispatched_date, out_mode_of_delivery, out_reporting_time, out_loading_time, out_remark,
        out_ug_aerial, out_frt
    """ if is_outward else """
        id,
        (SELECT COUNT(*) FROM report_documents rd WHERE rd.report_type = 'inward' AND rd.report_id = basic_info.id) AS doc_count,
        (SELECT '/uploads/' || rd.file_path FROM report_documents rd WHERE rd.report_type = 'inward' AND rd.report_id = basic_info.id ORDER BY rd.created_at DESC, rd.id DESC LIMIT 1) AS doc_url,
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
    description_column = "out_description" if is_outward else "description"
    item_code_column = "out_item_code" if is_outward else "item_code"

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

    category = (category or "").strip()
    sub_category = (sub_category or "").strip()
    material = (material or "").strip()
    if category or sub_category or material:
        category_map = load_material_category_map()
        matched_descriptions = []
        matched_item_codes = []
        for description, info in category_map.items():
            info_category = str(info.get("category") or "").strip()
            info_sub_category = str(info.get("sub_category") or "").strip()
            info_item_code = str(info.get("item_code") or "").strip()
            if material and description != material:
                continue
            if category and info_category != category:
                continue
            if sub_category and info_sub_category != sub_category:
                continue
            matched_descriptions.append(description)
            if info_item_code:
                matched_item_codes.append(info_item_code)

        if material:
            matched_descriptions.append(material)

        material_conditions = []
        if matched_descriptions:
            material_conditions.append(f"{description_column} = ANY(%s)")
            params.append(list(dict.fromkeys(matched_descriptions)))
        if matched_item_codes:
            material_conditions.append(f"CAST({item_code_column} AS TEXT) = ANY(%s)")
            params.append(list(dict.fromkeys(matched_item_codes)))

        if material_conditions:
            conditions.append(f"({' OR '.join(material_conditions)})")
        else:
            conditions.append("1 = 0")

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
@app.route("/api/login", methods=["POST"])
def login():
    bootstrap_real_data()
    if request.is_json:
        data = request.json
        username = data.get("username") or data.get("email")
        password = data.get("password")
    else:
        username = request.form.get("username")
        password = request.form.get("password")

    if not username or not password:
        if request.is_json:
            return jsonify({"status": "error", "message": "Missing credentials"}), 400
        return "Missing Username or Password", 400

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, username, role, password, name, warehouse
        FROM users
        WHERE LOWER(username) = LOWER(%s)
        AND (
            is_deleted = FALSE
            OR is_deleted IS NULL
        )
        """,
        (username,)
    )

    user = cur.fetchone()

    cur.close()
    conn.close()

    is_valid = False
    if user:
        try:
            is_valid = check_password_hash(user[3], password)
        except Exception:
            pass
        if not is_valid:
            is_valid = (user[3] == password)

    if is_valid:
        session["user"] = user[1]
        session["role"] = user[2]
        session["warehouse"] = user[5]
        
        redirect_url = "/admin-dashboard"
        if user[2] == "ground":
            redirect_url = "/ground-dashboard"
        elif user[2] == "user":
            redirect_url = "/user-dashboard"

        if request.is_json:
            # Map database fields to the structure expected by the Flutter app
            return jsonify({
                "status": "success",
                "message": "Login successful",
                "user": {
                    "id": user[0],
                    "username": user[1],
                    "email": user[1],  # Fallback to username
                    "full_name": user[4],
                    "role": user[2],
                    "employee_id": "ERP-" + str(user[0]).zfill(3),
                    "designation": "Field Staff" if user[2] == "ground" else "Manager",
                    "department": "Construction"
                },
                "redirect": redirect_url
            })

        return redirect(redirect_url)

    if request.is_json:
        return jsonify({"status": "error", "message": "Invalid Username or Password"}), 401
    return "Invalid Username or Password", 401




# ======user route =====
@app.route("/add-user", methods=["POST"])
def add_user():
    if require_role("admin"):
        return redirect("/")

    name = request.form["name"]
    username = request.form["username"]
    password = request.form["password"]
    role = request.form["role"]
    warehouse = request.form.get("warehouse") or None

    hashed_password = generate_password_hash(password)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO users (name, username, password, role, warehouse)
        VALUES (%s, %s, %s, %s, %s)
    """, (name, username, hashed_password, role, warehouse))

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/admin-dashboard")







# ================= DASHBOARDS =================

@app.route("/admin-dashboard")
def admin_dashboard():
    if require_role("admin"):
        return redirect("/")
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT COUNT(*) FROM documents")
        doc_count = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM survey_submissions")
        survey_count = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM basic_info")
        inward_count = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM outward_info")
        outward_count = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM users WHERE is_deleted = FALSE")
        user_count = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM basic_info WHERE date = CURRENT_DATE")
        today_inward = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM outward_info WHERE out_dc_date = CURRENT_DATE")
        today_outward = cur.fetchone()[0] or 0

        cur.execute("""
            SELECT * FROM (
                SELECT 'Document' as type, SUBSTRING(file_path FROM '[^/]+$') as name, created_at as sort_date, TO_CHAR(created_at, 'DD Mon, HH:MI AM') as date
                FROM documents
                UNION ALL
                SELECT
                    CASE WHEN COALESCE(photo_path, (SELECT file_path FROM media_registry WHERE survey_id = survey_submissions.id LIMIT 1), '') <> '' THEN 'Survey Photo' ELSE 'Survey' END as type,
                    warehouse_name as name,
                    captured_at as sort_date,
                    TO_CHAR(captured_at, 'DD Mon, HH:MI AM') as date
                FROM survey_submissions
            ) combined
            ORDER BY sort_date DESC LIMIT 6
        """)
        recent_activity = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    
    return render_page("admin.html", "Admin Panel", "admin_dashboard", 
                       new_uploads_count=doc_count + survey_count,
                       doc_count=doc_count,
                       survey_count=survey_count,
                       inward_count=inward_count,
                       outward_count=outward_count,
                       user_count=user_count,
                       today_inward=today_inward,
                       today_outward=today_outward,
                       recent_activity=recent_activity)


@app.route("/ground-dashboard")
def ground_dashboard():
    if require_role("ground"):
        return redirect("/")
    return render_page("ground/ground_dashboard.html", "Ground Team Panel", "ground_dashboard")

@app.route("/my-inventory")
def my_inventory():
    if require_role("ground"):
        return redirect("/")
        
    inventory_payload = get_warehouse_inventory_payload()
    inventory_rows = inventory_payload.get("rows", [])
    warehouse_name = session.get("warehouse") or session.get("user", "")
    
    my_inventory = [row for row in inventory_rows if row.get("warehouse", "").lower() == warehouse_name.lower() and float(row.get("phy_stock_qty") or 0) > 0]
    
    total_items = len(my_inventory)
    total_stock = sum(float(row.get("phy_stock_qty") or 0) for row in my_inventory)
    low_stock = sum(1 for row in my_inventory if float(row.get("phy_stock_qty") or 0) < 10)
    
    return render_page(
        "ground/my_inventory.html", 
        "My Inventory", 
        "my_inventory", 
        my_inventory=my_inventory,
        total_items=total_items,
        total_stock=total_stock,
        low_stock=low_stock
    )


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
        profile = {
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
        session["profile"] = profile
        save_profile(session.get("user"), profile)
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
            absolute_path = os.path.join(UPLOADS_BASE, "images", filename)
            uploaded_file.save(absolute_path)
            profile["photo_name"] = uploaded_file.filename
            profile["photo_path"] = relative_path

        session["profile"] = profile
        save_profile(session.get("user"), profile)
        return redirect("/my-account")

    return render_page("change_photo.html", "Change Photo", "account")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    primary_path = upload_disk_path(filename)
    if primary_path and os.path.isfile(primary_path) and os.path.getsize(primary_path) > 0:
        return send_from_directory(UPLOADS_BASE, filename)

    legacy_uploads = os.path.join(BASE_DIR, "uploads")
    legacy_path = os.path.normpath(os.path.join(legacy_uploads, filename))
    if legacy_path.startswith(os.path.abspath(legacy_uploads)) and os.path.isfile(legacy_path):
        return send_from_directory(legacy_uploads, filename)

    return "Upload file not found", 404


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
            relative_path = f"images/{filename}"
            absolute_path = os.path.join(UPLOADS_BASE, "images", filename)

            with open(absolute_path, "wb") as f:
                f.write(data)

            conn = get_conn()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO work_uploads 
                (user_id, image_path, location, material, quantity, remarks)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                get_current_user_id(default=1),
                relative_path,
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
    role = session.get("role")
    if role not in ["admin", "user"]:
        return redirect("/")

    if request.method == "POST":
        file = request.files.get("document")

        if file and file.filename:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)

            if size > 5 * 1024 * 1024:
                return "File must be less than 5MB"

            filename = f"{datetime.now().timestamp()}_{secure_filename(file.filename)}"
            relative_path = f"documents/{filename}"
            absolute_path = os.path.join(UPLOADS_BASE, "documents", filename)
            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

            file.save(absolute_path)

            conn = get_conn()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO documents (user_id, file_path)
                VALUES (%s, %s)
            """, (get_current_user_id(default=1), relative_path))

            conn.commit()
            cur.close()
            conn.close()

        if role == "admin":
            return redirect("/master?tab=documents")
        return redirect("/user-dashboard")

    return render_page("users/upload_documents.html", "Upload Documents", "upload_documents")


@app.route("/delete-document", methods=["POST"])
def delete_document():
    if require_role("admin"):
        return redirect("/")

    doc_id = request.form.get("id")
    if doc_id:
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT file_path FROM documents WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            if row:
                file_path = row[0]
                cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                conn.commit()

                if file_path:
                    delete_upload_file(file_path)
        finally:
            cur.close()
            conn.close()
    return redirect("/master?tab=documents")


@app.route("/delete-multiple-documents", methods=["POST"])
def delete_multiple_documents():
    if require_role("admin"):
        return redirect("/")

    doc_ids = request.form.getlist("doc_ids")
    if doc_ids:
        conn = get_conn()
        cur = conn.cursor()
        try:
            placeholders = ", ".join(["%s"] * len(doc_ids))
            cur.execute(
                f"SELECT file_path FROM documents WHERE id IN ({placeholders})",
                [int(i) for i in doc_ids]
            )
            rows = cur.fetchall()
            
            cur.execute(
                f"DELETE FROM documents WHERE id IN ({placeholders})",
                [int(i) for i in doc_ids]
            )
            conn.commit()
            
            for row in rows:
                file_path = row[0]
                if file_path:
                    cur.execute("SELECT COUNT(*) FROM documents WHERE file_path = %s", (file_path,))
                    remaining_refs = cur.fetchone()[0]
                    if remaining_refs == 0:
                        delete_upload_file(file_path)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
    return redirect("/master?tab=documents")


@app.route("/delete-work-upload", methods=["POST"])
def delete_work_upload():
    if require_role("admin"):
        return redirect("/")

    upload_id = request.form.get("id")
    if upload_id:
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT image_path FROM work_uploads WHERE id = %s", (upload_id,))
            row = cur.fetchone()
            if row:
                image_path = row[0]
                cur.execute("DELETE FROM work_uploads WHERE id = %s", (upload_id,))
                conn.commit()

                if image_path:
                    delete_upload_file(image_path)
        finally:
            cur.close()
            conn.close()
    return redirect("/master")


@app.route("/user-profile", methods=["GET", "POST"])
def user_profile():
    if require_role("user"):
        return redirect("/")

    if request.method == "POST":
        profile = {
            **get_profile(),
            "mobile": request.form["mobile"],
            "email": request.form["email"],
            "location": request.form["location"]
        }
        session["profile"] = profile
        save_profile(session.get("user"), profile)
        return redirect("/user-dashboard")

    return render_page("users/user_profile.html", "User Profile", "user_profile")


# ================= ADMIN ACCESS (FIX ADDED) =================

# ================= ADMIN ACCESS =================

# ================= ADMIN ACCESS =================

@app.route("/master")
def master():

    if require_role("admin"):
        return redirect("/")

    bootstrap_real_data()

    conn = get_conn()
    cur = conn.cursor()

    # ================= PHOTOS & WORK =================
    cur.execute(
        """
        SELECT * FROM (

            SELECT
                s.id::TEXT AS id,
                s.captured_at AS sort_date,

                TO_CHAR(
                    s.captured_at,
                    'DD Mon YYYY, HH12:MI AM'
                ) AS formatted_date,

                s.warehouse_name AS warehouse,

                COALESCE(
                    STRING_AGG(
                        NULLIF(
                            CONCAT_WS(
                                ' ',
                                NULLIF(m.description, ''),

                                CASE
                                    WHEN NULLIF(m.quantity, '') IS NOT NULL
                                    THEN '(' || m.quantity ||
                                         COALESCE(' ' || NULLIF(m.unit, ''), '')
                                         || ')'
                                    ELSE NULL
                                END
                            ),
                            ''
                        ),
                        ', '
                        ORDER BY m.item_index
                    ),

                    STRING_AGG(
                        NULLIF(m.sub_category, ''),
                        ', '
                        ORDER BY m.item_index
                    ),

                    'Survey upload'

                ) AS description,

                COALESCE(
                    s.photo_path,
                    (
                        SELECT file_path
                        FROM media_registry
                        WHERE survey_id = s.id
                        LIMIT 1
                    )
                ) AS path,

                COUNT(m.id) AS item_count

            FROM survey_submissions s

            LEFT JOIN survey_material_items m
                ON m.survey_id = s.id

            WHERE COALESCE(
                s.photo_path,
                (
                    SELECT file_path
                    FROM media_registry
                    WHERE survey_id = s.id
                    LIMIT 1
                ),
                ''
            ) <> ''

            GROUP BY
                s.id,
                s.captured_at,
                s.warehouse_name,
                s.photo_path

            UNION ALL

            SELECT
                'work-' || w.id::TEXT AS id,

                w.created_at AS sort_date,

                TO_CHAR(
                    w.created_at,
                    'DD Mon YYYY, HH12:MI AM'
                ) AS formatted_date,

                w.location AS warehouse,

                COALESCE(
                    NULLIF(w.material, '') || ' (' || w.quantity || ')',
                    w.remarks,
                    'Work upload'
                ) AS description,

                w.image_path AS path,

                1 AS item_count

            FROM work_uploads w

            WHERE COALESCE(w.image_path, '') <> ''

        ) combined

        ORDER BY sort_date DESC
        """
    )

    photo_rows = cur.fetchall()

    uploaded_photos = [
        {
            "id": r[0],
            "date": r[2],
            "warehouse": r[3] or "-",
            "desc": r[4] or "Field upload",
            "path": r[5],
            "item_count": r[6]
        }
        for r in photo_rows
    ]

    # ================= DOCUMENTS =================
    cur.execute(
        """
        SELECT
            d.id,
            d.file_path,

            TO_CHAR(
                d.created_at,
                'DD Mon YYYY, HH12:MI AM'
            ) AS uploaded_at,

            COALESCE(
                u.name,
                u.username,
                'Unknown'
            ) AS uploader_name

        FROM documents d

        LEFT JOIN users u
            ON u.id = d.user_id

        ORDER BY d.created_at DESC
        """
    )

    doc_rows = cur.fetchall()

    cur.close()
    conn.close()

    # ================= FILE TYPE =================
    def get_doc_type(path):

        ext = os.path.splitext(
            path or ""
        )[1].lower().lstrip(".")

        if ext == "pdf":
            return "pdf"

        elif ext in ("xls", "xlsx"):
            return "xls"

        elif ext in ("doc", "docx"):
            return "doc"

        elif ext in ("png", "jpg", "jpeg", "gif", "webp"):
            return "img"

        return "doc"

    # ================= DOCUMENT LIST =================
    uploaded_documents = []

    for r in doc_rows:

        original_name = os.path.basename(
            r[1] or "Unknown"
        )

        # Remove UUID prefix
        clean_name = original_name

        if "_" in original_name:
            clean_name = original_name.split("_", 1)[1]

        uploaded_documents.append({
            "id": r[0],
            "file_path": r[1],
            "file_name": clean_name,
            "uploaded_at": r[2],
            "uploader": r[3],
            "doc_type": get_doc_type(r[1])
        })

    return render_page(
        "master.html",
        "Field Data",
        "master",
        uploaded_photos=uploaded_photos,
        uploaded_documents=uploaded_documents
    )

    


@app.route("/new_entry")
@app.route("/new-entry")
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

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM route_requests GROUP BY status")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    route_stats = {"Pending": 0, "Approved": 0, "Approved (Pending Fulfillment)": 0, "Rejected": 0}
    for r in rows:
        if r[0] in route_stats:
            route_stats[r[0]] = r[1]

    return render_page("dashboard.html", "Dashboard", "dashboard", route_stats=route_stats)


@app.route("/tracking")
def tracking():
    role = session.get("role")
    if require_login() or role not in ["admin", "ground"]:
        return redirect("/")
    
    template_name = "tracking_ground.html" if role == "ground" else "tracking.html"
    return render_page(template_name, "Tracking", "tracking", frameless_page=True)


@app.route("/submit-route-request", methods=["POST"])
def submit_route_request():
    if require_login() or session.get("role") not in ["admin", "ground"]:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    payload = request.json
    conn = get_conn()
    cur = conn.cursor()
    status = "Approved (Pending Fulfillment)" if session.get("role") == "admin" else "Pending"
    
    cur.execute(
        """
        INSERT INTO route_requests (transfer_id, source_warehouse, destination_warehouse, material_description, quantity, vehicle_type, remarks, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payload.get("transfer_id"),
            payload.get("source_warehouse"),
            payload.get("destination_warehouse"),
            payload.get("material_description"),
            payload.get("quantity"),
            payload.get("vehicle_type"),
            payload.get("remarks", ""),
            status
        )
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Request submitted successfully"})


@app.route("/admin-route-requests")
def admin_route_requests():
    if require_role("admin"):
        return redirect("/")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, transfer_id, source_warehouse, destination_warehouse, material_description, quantity, vehicle_type, remarks, status, TO_CHAR(created_at + INTERVAL '9 hours 30 minutes', 'DD Mon YYYY, HH12:MI AM'), admin_note FROM route_requests ORDER BY id DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    requests_data = [
        {
            "id": r[0],
            "transfer_id": r[1],
            "source": r[2],
            "destination": r[3],
            "material": r[4],
            "quantity": r[5],
            "vehicle": r[6],
            "remarks": r[7],
            "status": r[8],
            "created_at": r[9],
            "admin_note": r[10]
        }
        for r in rows
    ]

    return render_page("admin_route_requests.html", "Route Requests", "route_requests", requests=requests_data)


@app.route("/update-route-request-status", methods=["POST"])
def update_route_request_status():
    if require_role("admin"):
        return jsonify({"error": "Authentication required"}), 401

    payload = request.json
    req_id = payload.get("id")
    status = payload.get("status")
    admin_note = payload.get("admin_note", "")

    if not req_id or not status:
        return jsonify({"error": "Missing data"}), 400

    conn = get_conn()
    cur = conn.cursor()
    if status == "Approved":
        status = "Approved (Pending Fulfillment)"
    cur.execute("UPDATE route_requests SET status = %s, admin_note = %s WHERE id = %s", (status, admin_note, req_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Status updated successfully"})

@app.route("/fulfil-route-request", methods=["POST"])
def fulfil_route_request():
    if require_login() or session.get("role") != "ground":
        return jsonify({"error": "Authentication required"}), 401

    payload = request.json
    req_id = payload.get("id")

    if not req_id:
        return jsonify({"error": "Missing data"}), 400

    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("SELECT transfer_id, source_warehouse, destination_warehouse, material_description, quantity, status FROM route_requests WHERE id = %s", (req_id,))
    row = cur.fetchone()
    
    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Request not found"}), 404
        
    t_id, src, dst, desc, qty, current_status = row
    
    # Verify the user is actually the source warehouse
    if src.strip().lower() != session.get("user", "").strip().lower():
        cur.close()
        conn.close()
        return jsonify({"error": "Unauthorized to fulfil this request"}), 403
        
    if current_status != 'Approved (Pending Fulfillment)':
        cur.close()
        conn.close()
        return jsonify({"error": "Request is not pending fulfillment"}), 400

    cur.execute("UPDATE route_requests SET status = 'Fulfilled' WHERE id = %s", (req_id,))

    import datetime
    today_str = datetime.date.today().isoformat()
    
    cur.execute("""
        INSERT INTO outward_info (out_dc_no, out_warehouse, out_description, out_qty, out_dc_date, out_remark, source_tag)
        VALUES (%s, %s, %s, %s, %s, %s, 'manual')
    """, (t_id, src, desc, qty, today_str, "Auto-deducted via Route Request Fulfillment"))

    cur.execute("""
        INSERT INTO basic_info (dc_no, warehouse, description, qty, challan_date, wh_remark, source_tag)
        VALUES (%s, %s, %s, %s, %s, %s, 'manual')
    """, (t_id, dst, desc, qty, today_str, "Auto-added via Route Request Fulfillment"))
    
    conn.commit()
    cur.close()
    conn.close()
    
    try:
        recalculate_warehouse_item(src, desc)
        recalculate_warehouse_item(dst, desc)
    except Exception as e:
        pass

    return jsonify({"message": "Request fulfilled successfully"})



@app.route("/incoming-requests")
def incoming_requests():
    if require_login() or session.get("role") != "ground":
        return redirect("/")

    user_warehouse = session.get("user", "").strip()
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, transfer_id, source_warehouse, destination_warehouse, material_description, quantity, vehicle_type, remarks, status, TO_CHAR(created_at + INTERVAL '9 hours 30 minutes', 'DD Mon YYYY, HH12:MI AM'), admin_note FROM route_requests WHERE BTRIM(LOWER(source_warehouse)) = %s AND status = 'Approved (Pending Fulfillment)' ORDER BY id DESC", (user_warehouse.lower(),))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    requests_data = [
        {
            "id": r[0],
            "transfer_id": r[1],
            "source": r[2],
            "destination": r[3],
            "material": r[4],
            "quantity": r[5],
            "vehicle": r[6],
            "remarks": r[7],
            "status": r[8],
            "created_at": r[9],
            "admin_note": r[10]
        }
        for r in rows
    ]

    return render_page("incoming_requests.html", "Incoming Requests", "incoming_requests", requests=requests_data)

@app.route("/my-route-requests")
def my_route_requests():
    if require_login() or session.get("role") != "ground":
        return redirect("/")

    user_warehouse = session.get("user", "").strip()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, transfer_id, source_warehouse, destination_warehouse, material_description, quantity,
               vehicle_type, remarks, status,
               TO_CHAR(created_at + INTERVAL '9 hours 30 minutes', 'DD Mon YYYY, HH12:MI AM'),
               admin_note
        FROM route_requests
        WHERE BTRIM(LOWER(destination_warehouse)) = %s
        ORDER BY id DESC
        """,
        (user_warehouse.lower(),)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    requests_data = [
        {
            "id": r[0],
            "transfer_id": r[1],
            "source": r[2],
            "destination": r[3],
            "material": r[4],
            "quantity": r[5],
            "vehicle": r[6],
            "remarks": r[7],
            "status": r[8],
            "created_at": r[9],
            "admin_note": r[10]
        }
        for r in rows
    ]

    return render_page("ground_route_requests.html", "My Route Requests", "route_requests", requests=requests_data)


@app.route("/warehouse-inventory")
def warehouse_inventory():
    if require_login() or session.get("role") not in ["admin", "ground"]:
        return redirect("/")
    return render_page("warehouse_inventory.html", "Warehouse Inventory", "inventory")


@app.route("/report")
def report():
    if require_role("admin"):
        return redirect("/")
    return render_page("report.html", "Report", "report")


def normalize_report_type(report_type):
    return "outward" if str(report_type).lower() == "outward" else "inward"


def get_report_entry_summary(report_type, report_id):
    report_type = normalize_report_type(report_type)
    table_name = "outward_info" if report_type == "outward" else "basic_info"
    columns = """
        id,
        out_sr_no AS serial_no,
        out_warehouse AS warehouse,
        out_description AS description,
        out_dc_no AS document_no,
        out_dc_date AS document_date
    """ if report_type == "outward" else """
        id,
        sr_no AS serial_no,
        warehouse,
        description,
        dc_no AS document_no,
        challan_date AS document_date
    """

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT {columns} FROM {table_name} WHERE id = %s", (report_id,))
        row = cur.fetchone()
        if not row:
            return None
        keys = ["id", "serial_no", "warehouse", "description", "document_no", "document_date"]
        summary = dict(zip(keys, row))
        summary["report_type"] = report_type
        summary["document_date"] = serialize_value(summary.get("document_date"))
        return summary
    finally:
        cur.close()
        conn.close()


def get_report_documents(report_type, report_id):
    report_type = normalize_report_type(report_type)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, file_path, original_filename, created_at
            FROM report_documents
            WHERE report_type = %s AND report_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (report_type, report_id)
        )
        documents = []
        for doc_id, file_path, original_filename, created_at in cur.fetchall():
            file_name = original_filename or os.path.basename(file_path or "")
            ext = os.path.splitext(file_name)[1].replace(".", "").lower() or "file"
            documents.append({
                "id": doc_id,
                "file_path": file_path,
                "file_name": file_name,
                "doc_type": ext[:5],
                "uploaded_at": created_at.strftime("%d %b %Y, %I:%M %p") if created_at else ""
            })
        return documents
    finally:
        cur.close()
        conn.close()


def get_all_report_documents():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                rd.id,
                rd.report_type,
                rd.report_id,
                rd.file_path,
                rd.original_filename,
                rd.created_at,
                rd.matched_terms,
                COALESCE(b.invoice_no, b.in_doc_no, o.out_in_doc_no, o.out_dc_no, '') AS matched_no,
                COALESCE(b.warehouse, o.out_warehouse, '') AS warehouse,
                COALESCE(b.description, o.out_description, '') AS description
            FROM report_documents rd
            LEFT JOIN basic_info b ON rd.report_type = 'inward' AND rd.report_id = b.id
            LEFT JOIN outward_info o ON rd.report_type = 'outward' AND rd.report_id = o.id
            ORDER BY rd.created_at DESC, rd.id DESC
            """
        )
        docs = []
        for row in cur.fetchall():
            file_name = row[4] or os.path.basename(row[3] or "")
            ext = os.path.splitext(file_name)[1].replace(".", "").lower() or "file"
            docs.append({
                "id": row[0],
                "report_type": row[1],
                "report_id": row[2],
                "file_path": row[3],
                "file_name": file_name,
                "doc_type": ext[:5],
                "uploaded_at": row[5].strftime("%d %b %Y, %I:%M %p") if row[5] else "",
                "matched_terms": row[6] or "",
                "matched_no": row[7] or "-",
                "warehouse": row[8] or "-",
                "description": row[9] or "-"
            })
        return docs
    finally:
        cur.close()
        conn.close()


@app.route("/report-documents")
def report_documents_hub():
    if require_role("admin"):
        return redirect("/")

    return render_page(
        "report_documents_hub.html",
        "Report Documents",
        "report",
        documents=get_all_report_documents(),
        doc_status=request.args.get("doc_status"),
        matched_count=request.args.get("matched_count"),
        scan_chars=request.args.get("scan_chars"),
        selected_type=normalize_report_type(request.args.get("type", "inward"))
    )


@app.route("/report-documents/<report_type>/<int:report_id>", methods=["GET", "POST"])
def report_documents(report_type, report_id):
    if require_role("admin"):
        return redirect("/")

    report_type = normalize_report_type(report_type)
    entry = get_report_entry_summary(report_type, report_id)
    if not entry:
        return redirect("/report")

    if request.method == "POST":
        file = request.files.get("document")
        if file and file.filename:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)

            if size > 10 * 1024 * 1024:
                return "File must be less than 10MB", 400

            safe_name = secure_filename(file.filename)
            filename = f"report_{report_type}_{report_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
            relative_path = save_document_upload(file, filename)

            conn = get_conn()
            cur = conn.cursor()
            try:
                ensure_report_documents_table(cur)
                cur.execute(
                    """
                    INSERT INTO report_documents (report_type, report_id, file_path, original_filename, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (report_type, report_id, relative_path, file.filename, get_current_user_id(default=1))
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
                conn.close()

        return redirect(f"/report-documents/{report_type}/{report_id}")

    documents = get_report_documents(report_type, report_id)
    return render_page(
        "report_documents.html",
        "Report Documents",
        "report",
        entry=entry,
        documents=documents
    )


@app.route("/admin")
def admin():
    if require_role("admin"):
        return redirect("/")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT BTRIM(warehouse) FROM basic_info WHERE warehouse IS NOT NULL AND BTRIM(warehouse) <> ''
        UNION
        SELECT DISTINCT BTRIM(out_warehouse) FROM outward_info WHERE out_warehouse IS NOT NULL AND BTRIM(out_warehouse) <> ''
    """)
    warehouses = sorted([r[0] for r in cur.fetchall() if r[0]])
    cur.close()
    conn.close()

    return render_page("admin_create.html", "Create User", "admin_create", warehouses=warehouses)


@app.route("/view-users")
def view_users():
    if require_role("admin"):
        return redirect("/")

    conn = get_conn()
    cur = conn.cursor()

    # Fetch active users
    cur.execute("""
        SELECT id, COALESCE(name, username) AS display_name, username, role, warehouse
        FROM users
        WHERE role IN ('ground', 'user') AND deleted_at IS NULL
        ORDER BY role, username
    """)
    active_rows = cur.fetchall()

    # Fetch recently deleted users (last 30 days)
    cur.execute("""
        SELECT 
            id, 
            COALESCE(name, username) AS display_name, 
            username, 
            role,
            TO_CHAR(deleted_at, 'DD Mon YYYY, HH12:MI AM') as deleted_date
        FROM users
        WHERE deleted_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        ORDER BY deleted_at DESC
    """)
    deleted_rows = cur.fetchall()

    cur.close()
    conn.close()

    ground_users = [row for row in active_rows if row[3] == "ground"]
    individual_users = [row for row in active_rows if row[3] == "user"]
    
    deleted_users = [
        {
            "id": r[0],
            "name": r[1],
            "username": r[2],
            "role": r[3],
            "deleted_at": r[4]
        }
        for r in deleted_rows
    ]

    return render_page(
        "view_users.html",
        "View Users",
        "admin_view",
        ground_users=ground_users,
        individual_users=individual_users,
        deleted_users=deleted_users,
        password_updated=request.args.get("password_updated") == "1",
        user_deleted=request.args.get("deleted") == "1",
        user_restored=request.args.get("restored") == "1",
        user_purged=request.args.get("purged") == "1",
        updated_username=request.args.get("username", "")
    )


@app.route("/delete-user", methods=["POST"])
def delete_user():

    if require_role("admin"):
        return redirect("/")

    user_id = request.form.get("user_id")

    if user_id:

        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE users
            SET
                is_deleted = TRUE,
                deleted_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (user_id,)
        )

        conn.commit()

        cur.close()
        conn.close()

    return redirect("/view-users?deleted=1")


@app.route("/restore-user", methods=["POST"])
def restore_user():

    if require_role("admin"):
        return redirect("/")

    user_id = request.form.get("user_id")

    if user_id:

        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE users
            SET
                is_deleted = FALSE,
                deleted_at = NULL
            WHERE id = %s
            """,
            (user_id,)
        )

        conn.commit()

        cur.close()
        conn.close()

    return redirect("/view-users?restored=1")

@app.route("/permanently-delete-user", methods=["POST"])
def permanently_delete_user():

    if require_role("admin"):
        return redirect("/")

    user_id = request.form.get("user_id")

    if user_id:

        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "DELETE FROM users WHERE id = %s",
            (user_id,)
        )

        conn.commit()

        cur.close()
        conn.close()

    return redirect("/view-users?purged=1")


@app.route("/reset-user-password", methods=["POST"])
def reset_user_password():
    if require_role("admin"):
        return redirect("/")

    user_id = request.form.get("user_id")
    username = request.form.get("username", "")
    new_password = (request.form.get("new_password") or "").strip()

    if not user_id or not new_password:
        return redirect("/view-users")
        
    hashed_password = generate_password_hash(new_password)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password=%s WHERE id=%s AND role IN ('ground', 'user')",
        (hashed_password, user_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(f"/view-users?password_updated=1&username={username}")




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

    values = values + ("manual",)
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
        """, values)

        conn.commit()
    except Exception as exc:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"message": "Save failed", "error": str(exc)}), 500

    cur.close()
    conn.close()

    try:
        recalculate_warehouse_item(data.get("warehouse"), data.get("description"))

    except:
        pass

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

    try:
        recalculate_warehouse_item(data.get("out_warehouse"), data.get("out_description"))
    except:
        pass

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

    report_type = (request.args.get("type") or request.args.get("kind") or "inward").lower()
    year_value = request.args.get("year")
    year = int(year_value) if year_value and year_value.isdigit() else None
    limit_value = request.args.get("limit") or request.args.get("page_size") or "100"
    offset_value = request.args.get("offset")
    page_value = request.args.get("page")
    search_term = request.args.get("search", "")
    search_field = request.args.get("field", "all")
    category = request.args.get("category", "")
    sub_category = request.args.get("sub_category", "")
    material = request.args.get("material", "")

    try:
        limit = max(1, min(200, int(limit_value)))
    except ValueError:
        limit = 100

    if offset_value is not None:
        try:
            offset = max(0, int(offset_value))
        except ValueError:
            offset = 0
    else:
        try:
            page_number = max(1, int(page_value or "1"))
        except ValueError:
            page_number = 1
        offset = (page_number - 1) * limit

    rows, total_count = get_report_page(
        report_type=report_type,
        year=year,
        limit=limit,
        offset=offset,
        search_term=search_term,
        search_field=search_field,
        category=category,
        sub_category=sub_category,
        material=material
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


@app.route("/report-data-export")
def report_data_export():
    """Return ALL matching records for Excel/CSV export (no pagination cap)."""
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    report_type = (request.args.get("type") or "inward").lower()
    year_value = request.args.get("year")
    year = int(year_value) if year_value and year_value.isdigit() else None
    search_term = request.args.get("search", "")
    search_field = request.args.get("field", "all")
    category = request.args.get("category", "")
    sub_category = request.args.get("sub_category", "")
    material = request.args.get("material", "")

    rows, total_count = get_report_page(
        report_type=report_type,
        year=year,
        limit=999999,
        offset=0,
        search_term=search_term,
        search_field=search_field,
        category=category,
        sub_category=sub_category,
        material=material
    )

    if report_type == "outward":
        data = [prepare_outward_record(record) for record in rows]
    else:
        data = [prepare_inward_record(record) for record in rows]

    return jsonify({
        "data": data,
        "total_count": total_count
    })


@app.route("/upload-report-document", methods=["POST"])
def upload_report_document():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return auth_redirect

    redirect_target = request.form.get("redirect_to") or request.args.get("redirect_to") or "report"
    redirect_base = "/report-documents" if redirect_target == "documents" else "/report"
    report_type = normalize_report_type(request.form.get("type", "inward"))
    file = request.files.get("document")
    if not file or not file.filename:
        return redirect(f"{redirect_base}?doc_status=missing&type={report_type}")

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return redirect(f"{redirect_base}?doc_status=too_large&type={report_type}")

    safe_name = secure_filename(file.filename)
    filename = f"report_auto_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    relative_path = save_document_upload(file, filename)
    absolute_path = existing_upload_path(relative_path)
    scanned_text = clean_db_text(extract_document_text(absolute_path, file.filename))
    matched_report_ids, matched_terms = find_matching_report_entries(report_type, scanned_text, file.filename)
    if not matched_report_ids:
        alternate_type = "outward" if report_type == "inward" else "inward"
        alternate_report_ids, alternate_terms = find_matching_report_entries(alternate_type, scanned_text, file.filename)
        if alternate_report_ids:
            report_type = alternate_type
            matched_report_ids = alternate_report_ids
            matched_terms = alternate_terms

    if not matched_report_ids:
        return redirect(f"{redirect_base}?doc_status=no_match&type={report_type}&scan_chars={len(scanned_text.strip())}")

    conn = get_conn()
    cur = conn.cursor()
    try:
        ensure_report_documents_table(cur)
        for matched_report_id in matched_report_ids:
            cur.execute(
                """
                INSERT INTO report_documents (
                    report_type, report_id, file_path, original_filename, uploaded_by, scanned_text, matched_terms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    report_type,
                    int(matched_report_id),
                    relative_path,
                    clean_db_text(file.filename, 255),
                    get_current_user_id(default=1),
                    clean_db_text(scanned_text, 8000),
                    clean_db_text(", ".join(matched_terms), 1000)
                )
            )
        conn.commit()
    except Exception:
        conn.rollback()
        delete_upload_file(relative_path)
        raise
    finally:
        cur.close()
        conn.close()

    return redirect(f"{redirect_base}?doc_status=matched&matched_count={len(matched_report_ids)}&type={report_type}")


@app.route("/report-years")
def report_years():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    report_type = request.args.get("type", "inward").lower()
    return jsonify(get_report_years(report_type))


@app.route("/delete-report-entry", methods=["POST"])
def delete_report_entry():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return auth_redirect

    entry_id = request.form.get("id")
    report_type = request.form.get("type", "inward").lower()
    if not entry_id or not str(entry_id).isdigit():
        return redirect("/report")

    table_name = "outward_info" if report_type == "outward" else "basic_info"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"DELETE FROM {table_name} WHERE id = %s", (int(entry_id),))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return redirect("/report")


@app.route("/delete-report-document", methods=["POST"])
def delete_report_document():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return auth_redirect

    doc_id = request.form.get("id")
    report_type = normalize_report_type(request.form.get("type", "inward"))
    report_id = request.form.get("report_id")
    if not doc_id or not str(doc_id).isdigit() or not report_id or not str(report_id).isdigit():
        return redirect("/report")

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT file_path FROM report_documents WHERE id = %s AND report_type = %s AND report_id = %s",
            (int(doc_id), report_type, int(report_id))
        )
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM report_documents WHERE id = %s", (int(doc_id),))
            cur.execute("SELECT COUNT(*) FROM report_documents WHERE file_path = %s", (row[0],))
            remaining_refs = cur.fetchone()[0]
            conn.commit()
            if remaining_refs == 0:
                delete_upload_file(row[0])
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    redirect_target = request.form.get("redirect_to")
    if redirect_target == "hub":
        return redirect("/report-documents")
    return redirect(f"/report-documents/{report_type}/{int(report_id)}")


@app.route("/delete-multiple-report-documents", methods=["POST"])
def delete_multiple_report_documents():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return auth_redirect

    doc_ids = request.form.getlist("doc_ids")
    if not doc_ids:
        return redirect("/report-documents")

    conn = get_conn()
    cur = conn.cursor()
    try:
        # Fetch file paths to delete physical files
        placeholders = ", ".join(["%s"] * len(doc_ids))
        cur.execute(
            f"SELECT file_path FROM report_documents WHERE id IN ({placeholders})",
            [int(i) for i in doc_ids]
        )
        rows = cur.fetchall()
        
        # Delete from DB
        cur.execute(
            f"DELETE FROM report_documents WHERE id IN ({placeholders})",
            [int(i) for i in doc_ids]
        )
        conn.commit()
        
        # Delete physical files if no other references exist
        for row in rows:
            file_path = row[0]
            if file_path:
                cur.execute("SELECT COUNT(*) FROM report_documents WHERE file_path = %s", (file_path,))
                remaining_refs = cur.fetchone()[0]
                if remaining_refs == 0:
                    delete_upload_file(file_path)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return redirect("/report-documents?doc_status=bulk_deleted")


@app.route("/warehouse-inventory-data")
def warehouse_inventory_data():
    if require_login() or session.get("role") not in ["admin", "ground"]:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    payload = get_warehouse_inventory_payload()
    try:
        payload["categories"] = load_material_category_map()
    except Exception as e:
        payload["categories"] = {}
        
    return jsonify(payload)


@app.route("/material-categories")
def material_categories():
    if require_login() or session.get("role") not in ["admin", "ground"]:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    try:
        return jsonify(load_material_category_map())
    except Exception:
        return jsonify({})

@app.route("/dashboard-data")
def dashboard_data():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    return jsonify(get_dashboard_payload())


def get_dashboard_raw_payload():
    bootstrap_real_data()
    inventory_payload = get_warehouse_inventory_payload()
    inventory_rows = inventory_payload.get("rows", [])
    material_categories = load_material_category_map()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT 'inward' AS entry_type, challan_date AS movement_date, warehouse AS warehouse_name, description, qty AS qty_value, dc_no AS document_no
        FROM basic_info WHERE challan_date IS NOT NULL
        UNION ALL
        SELECT 'outward' AS entry_type, out_dc_date AS movement_date, out_warehouse AS warehouse_name, out_description AS description, out_qty AS qty_value, out_dc_no AS document_no
        FROM outward_info WHERE out_dc_date IS NOT NULL
        ORDER BY movement_date DESC
        """
    )
    raw_movements = cur.fetchall()

    cur.close()
    conn.close()

    movements = [
        {
            "type": row[0],
            "date": row[1].isoformat() if row[1] else "",
            "warehouse": row[2] or "-",
            "description": row[3] or "-",
            "qty": float(row[4].replace(",", "")) if row[4] and row[4].replace(",", "").replace(".", "").replace("-", "").replace("+", "").isdigit() else 0,
            "document_no": row[5] or "-"
        }
        for row in raw_movements
    ]

    return {
        "inventory": inventory_rows,
        "movements": movements,
        "categories": material_categories
    }


@app.route("/dashboard-raw-data")
def dashboard_raw_data():
    auth_redirect = require_role("admin")
    if auth_redirect:
        return jsonify({"error": "Authentication required", "redirect": "/"}), 401

    return jsonify(get_dashboard_raw_payload())


def parse_datetime_value(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    
    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("a.m.", "AM").replace("p.m.", "PM").replace("a.m", "AM").replace("p.m", "PM")
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%B %d, %Y, %I:%M %p", "%b %d, %Y, %I:%M %p", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(normalized, pattern)
            return dt
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    return None



@app.route("/api", methods=["GET"])
def api_health_check():
    return jsonify({"status": "success", "msg": "ERP Backend Active", "db_ready": True}), 200

@app.route("/api/surveys", methods=["POST"])
@app.route("/api/upload_survey", methods=["POST"])
def api_upload_survey():
    conn = None
    cur = None
    try:
        if request.is_json:
            data = request.json
        else:
            data = request.form

        user_id = data.get("user_id") or data.get("userId") or get_current_user_id(default=1)
        warehouse_name = data.get("warehouse_name", "")
        latitude = parse_float_value(data.get("latitude") or data.get("lat"))
        longitude = parse_float_value(data.get("longitude") or data.get("lng"))
        gps_accuracy = parse_float_value(data.get("gps_accuracy_meters") or data.get("gps_accuracy") or 0)
        address_line = data.get("address_line") or data.get("address", "")
        pincode = data.get("pincode", "")
        district = data.get("district", "")
        taluka = data.get("taluka", "")
        
        # Use full datetime instead of just date to fix the "12:00 AM" issue
        captured_at = parse_datetime_value(data.get("captured_at")) or datetime.now()
        
        # Support both JSON list and encoded string
        materials_raw = data.get("materials") or data.get("material_items") or data.get("items")
        if isinstance(materials_raw, list):
            material_items = materials_raw
        else:
            material_items = collect_survey_material_items(data)
        
        photo_path = ""
        uploaded_file = request.files.get("photo")
        if uploaded_file and uploaded_file.filename:
            filename = f"survey_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(uploaded_file.filename)}"
            relative_path = f"images/{filename}"
            absolute_path = os.path.join(UPLOADS_BASE, "images", filename)
            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
            uploaded_file.save(absolute_path)
            photo_path = relative_path
            
        conn = get_conn()
        cur = conn.cursor()
        ensure_user_survey_table(cur)
        cur.execute(
            """
            INSERT INTO survey_submissions (
                user_id, warehouse_name, latitude, longitude, gps_accuracy_meters,
                address_line, pincode, district, taluka, captured_at, photo_path
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id, warehouse_name, latitude, longitude, gps_accuracy,
                address_line, pincode, district, taluka, captured_at, photo_path
            )
        )
        survey_id = cur.fetchone()[0]

        for index, item in enumerate(material_items):
            cur.execute(
                """
                INSERT INTO survey_material_items (
                    survey_id, item_index, category, sub_category, quantity, unit, description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    survey_id,
                    item.get("item_index") or index + 1,
                    item.get("category", ""),
                    item.get("sub_category", ""),
                    item.get("quantity", ""),
                    item.get("unit", ""),
                    item.get("description", "")
                )
            )

        conn.commit()
        print(f"[DEBUG] Survey Created: ID={survey_id}, CapturedAt={captured_at}")
        
        return jsonify({
            "message": "Survey submitted successfully",
            "status": "success",
            "survey_id": survey_id,
            "item_count": len(material_items)
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"message": str(e), "status": "error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/api/upload", methods=["POST"])
@app.route("/api/upload_raw", methods=["POST"])
def api_upload_media():
    print("\n--- [DEBUG] API MEDIA UPLOAD START ---")
    try:
        def safe_form_get(name):
            content_type = request.content_type or ""
            if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
                return request.form.get(name)
            return None

        # Support both form data, query parameters, AND headers for robustness
        # Raw binary uploads send metadata in headers. Avoid request.form unless
        # the request is actually form encoded; otherwise Werkzeug can raise a
        # BadRequest before the stream is saved.
        raw_user_id = (request.headers.get("X-UserId") or
                       request.args.get("userId") or request.args.get("user_id") or
                       safe_form_get("userId") or safe_form_get("user_id"))
        
        media_type = (request.headers.get("X-Type") or request.args.get("type") or
                      safe_form_get("type") or "Photo")
        
        raw_survey_id = (request.headers.get("X-SurveyId") or
                         request.args.get("surveyId") or request.args.get("survey_id") or
                         safe_form_get("surveyId") or safe_form_get("survey_id"))

        lat = (request.headers.get("X-Lat") or request.args.get("lat") or safe_form_get("lat"))
        lng = (request.headers.get("X-Lng") or request.args.get("lng") or safe_form_get("lng"))
        
        user_id = int(raw_user_id) if raw_user_id and str(raw_user_id).isdigit() else get_current_user_id(default=1)
        
        # Clean survey_id (it might come with 'work-' prefix or as a string)
        survey_id = None
        if raw_survey_id:
            cleaned_sid = str(raw_survey_id).replace("work-", "").strip()
            if cleaned_sid.isdigit():
                survey_id = int(cleaned_sid)

        print(f"[DEBUG] Params: User={user_id}, Type={media_type}, Survey={survey_id} (Raw: {raw_survey_id})")
        
        # Determine filename and paths
        if 'multipart/form-data' in (request.content_type or ''):
            uploaded_file = request.files.get("file") or request.files.get("photo")
            if not uploaded_file or not uploaded_file.filename:
                print("[DEBUG] Error: No file in multipart")
                return jsonify({"status": "error", "message": "No file uploaded"}), 400
            orig_filename = secure_filename(uploaded_file.filename)
        else:
            orig_filename = request.headers.get('X-Filename') or f"upload_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            orig_filename = secure_filename(orig_filename)

        # Use LAT/LNG in filename if available
        if lat and lng:
            filename = f"LAT_{lat}_LNG_{lng}_{uuid4().hex[:8]}{Path(orig_filename).suffix or '.jpg'}"
        else:
            filename = f"{media_type.lower()}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{orig_filename}"
            
        relative_path = f"images/{filename}"
        
        # Use absolute path for saving to the correct folder
        uploads_dir = os.path.join(UPLOADS_BASE, "images")
        os.makedirs(uploads_dir, exist_ok=True)
        absolute_path = os.path.join(uploads_dir, filename)
        
        if 'multipart/form-data' in (request.content_type or ''):
            uploaded_file.save(absolute_path)
            file_size = os.path.getsize(absolute_path)
            print(f"[DEBUG] Saved Multipart: {absolute_path} ({file_size} bytes)")
        else:
            # For streamed uploads, read the raw stream in chunks
            file_size = 0
            with open(absolute_path, 'wb') as f:
                while True:
                    chunk = request.stream.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    file_size += len(chunk)
            
            if file_size == 0:
                print("[DEBUG] Error: No data received in stream")
                if os.path.exists(absolute_path):
                    os.remove(absolute_path)
                return jsonify({"status": "error", "message": "Empty file data"}), 400
            
            print(f"[DEBUG] Saved Streamed: {absolute_path} ({file_size} bytes)")
            
        # Update Database
        conn = get_conn()
        cur = conn.cursor()
        
        # FALLBACK: If survey_id is missing, try to find the user's latest survey from the last 2 minutes
        if not survey_id and user_id:
            print("[DEBUG] survey_id missing, attempting fallback for user_id:", user_id)
            cur.execute("""
                SELECT id FROM survey_submissions 
                WHERE user_id = %s 
                AND created_at > NOW() - INTERVAL '2 minutes'
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            res = cur.fetchone()
            if res:
                survey_id = res[0]
                print(f"[DEBUG] Fallback found survey_id: {survey_id}")

        if survey_id:
            print(f"[DEBUG] Updating DB: linking media to survey_id={survey_id}")
            # Insert into media_registry for multiple photo support
            cur.execute(
                "INSERT INTO media_registry (user_id, file_path, media_type, latitude, longitude, survey_id) VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, relative_path, media_type, lat, lng, survey_id),
            )
            
            # Also update the primary photo path in survey_submissions
            cur.execute("UPDATE survey_submissions SET photo_path = %s WHERE id = %s", (relative_path, survey_id))
            conn.commit()
            print("[DEBUG] DB Update Success")
        else:
            print("[DEBUG] Warning: No valid survey_id found to link this photo")
            
        cur.close()
        conn.close()
            
        return jsonify({
            "status": "success",
            "message": "Media uploaded successfully",
            "path": relative_path,
            "survey_id": survey_id
        }), 201
    except Exception as e:
        print(f"[DEBUG] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        print("--- [DEBUG] API MEDIA UPLOAD END ---\n")

@app.route("/api/upload_document", methods=["POST"])
def api_upload_document():
    try:
        user_id = request.form.get("userId") or request.form.get("user_id") or get_current_user_id(default=1)
        uploaded_file = request.files.get("file") or request.files.get("document")
        
        if not uploaded_file or not uploaded_file.filename:
            return jsonify({"status": "error", "message": "No file uploaded"}), 400
            
        filename = f"doc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(uploaded_file.filename)}"
        relative_path = f"documents/{filename}"
        absolute_path = os.path.join(UPLOADS_BASE, "documents", filename)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        uploaded_file.save(absolute_path)
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO documents (user_id, file_path) VALUES (%s, %s)", (user_id, relative_path))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": "Document uploaded successfully",
            "path": relative_path
        }), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/media", methods=["POST", "GET"])
def api_media_handler():
    if request.method == "GET":
        user_id = request.args.get("userId") or request.args.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Missing userId"}), 400
            
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, COALESCE(photo_path, (SELECT file_path FROM media_registry WHERE survey_id = survey_submissions.id LIMIT 1)), warehouse_name, captured_at FROM survey_submissions WHERE user_id = %s AND COALESCE(photo_path, (SELECT file_path FROM media_registry WHERE survey_id = survey_submissions.id LIMIT 1), '') != ''", (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        data = [
            {"id": r[0], "path": r[1], "warehouse": r[2], "date": r[3].isoformat() if r[3] else ""}
            for r in rows
        ]
        return jsonify({"status": "success", "data": data})
        
    data = request.json or {}
    user_id = data.get("userId") or data.get("user_id")
    file_path = data.get("path")
    
    if not user_id or not file_path:
        return jsonify({"status": "error", "message": "Missing data"}), 400
        
    return jsonify({"status": "success", "message": "Media metadata recorded"}), 201


@app.route("/api/documents", methods=["GET"])
def api_get_documents():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT d.id, d.file_path, TO_CHAR(d.created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at, 
                   COALESCE(u.name, u.username, 'Admin') AS uploader
            FROM documents d
            LEFT JOIN users u ON u.id = d.user_id
            ORDER BY d.created_at DESC
        """)
        rows = cur.fetchall()
        
        data = [
            {
                "id": r[0],
                "file_path": r[1],
                "created_at": r[2],
                "uploader": r[3]
            }
            for r in rows
        ]
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()


@app.route("/user-survey-data")
def user_survey_data():
    if require_role("admin"):
        return redirect("/")
        
    bootstrap_real_data()
    
    warehouse_filter = request.args.get("warehouse", "").strip()
    category_filter = request.args.get("category", "").strip()
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Base query
    query = """
        SELECT
            s.id,
            TO_CHAR(s.captured_at, 'DD Mon YYYY, HH12:MI AM') AS captured_at,
            s.user_id,
            s.warehouse_name,
            s.address_line,
            s.pincode,
            s.district,
            s.taluka,
            s.latitude,
            s.longitude,
            s.gps_accuracy_meters,
            COALESCE(s.photo_path, (SELECT file_path FROM media_registry WHERE survey_id = s.id LIMIT 1)) AS photo_path,
            m.item_index,
            m.category,
            m.sub_category,
            m.quantity,
            m.unit,
            m.description
        FROM survey_submissions s
        LEFT JOIN survey_material_items m ON m.survey_id = s.id
        WHERE 1=1
    """
    params = []
    
    if warehouse_filter:
        query += " AND s.warehouse_name = %s"
        params.append(warehouse_filter)
        
    if category_filter:
        query += " AND m.category = %s"
        params.append(category_filter)
        
    query += " ORDER BY s.captured_at DESC, s.id DESC, m.item_index ASC"
    
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    
    # Calculate total material count
    material_count = len([r for r in rows if r[12] is not None]) # Count rows where m.item_index is not null
    
    # Fetch filter options
    cur.execute("SELECT DISTINCT warehouse_name FROM survey_submissions WHERE warehouse_name IS NOT NULL AND warehouse_name != '' ORDER BY warehouse_name")
    warehouses = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT DISTINCT category FROM survey_material_items WHERE category IS NOT NULL AND category != '' ORDER BY category")
    categories = [r[0] for r in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    surveys = [
        {
            "id": r[0],
            "created_at": r[1],
            "user_id": r[2],
            "warehouse": r[3] or "-",
            "address": r[4] or "",
            "pincode": r[5] or "",
            "district": r[6] or "",
            "taluka": r[7] or "",
            "lat": r[8],
            "lon": r[9],
            "accuracy": r[10],
            "photo_path": r[11],
            "item_index": r[12],
            "category": r[13] or "-",
            "item": r[14] or "-",
            "qty": r[15] or "-",
            "unit": r[16] or "",
            "desc": r[17] or ""
        }
        for r in rows
    ]
    
    return render_page(
        "user_survey_data.html", 
        "User Survey Data", 
        "user_survey_data", 
        surveys=surveys,
        warehouses=warehouses,
        categories=categories,
        selected_warehouse=warehouse_filter,
        selected_category=category_filter,
        material_count=material_count
    )


@app.route("/delete-survey", methods=["POST"])
def delete_survey():
    print("\n--- DELETE SURVEY START ---")
    if require_role("admin"):
        print("Access Denied: User is not an admin")
        return jsonify({"error": "Unauthorized"}), 403
        
    survey_id_raw = request.form.get("id") or request.args.get("id")
    print(f"ID received: {survey_id_raw}")
    
    if not survey_id_raw:
        return redirect("/user-survey-data")
        
    try:
        survey_id = int(survey_id_raw)
    except ValueError:
        return redirect("/user-survey-data?error=invalid_id")
        
    conn = get_conn()
    cur = conn.cursor()
    
    photo_to_delete = None
    try:
        # 1. Fetch photo path first so we know what to delete later
        cur.execute("SELECT photo_path FROM survey_submissions WHERE id = %s", (survey_id,))
        row = cur.fetchone()
        if row:
            photo_to_delete = row[0]
            print(f"Photo path found: {photo_to_delete}")
                
        # 2. Delete child records
        print(f"Deleting material items for survey {survey_id}")
        cur.execute("DELETE FROM survey_material_items WHERE survey_id = %s", (survey_id,))
        
        # 3. Delete parent record
        print(f"Deleting survey record {survey_id}")
        cur.execute("DELETE FROM survey_submissions WHERE id = %s", (survey_id,))
        
        # 4. Commit database changes first
        conn.commit()
        print("Database transaction committed successfully")
        
        # 5. Only now try to delete the physical file
        if photo_to_delete:
            delete_upload_file(photo_to_delete)
                
    except Exception as e:
        conn.rollback()
        print(f"CRITICAL DATABASE ERROR: {e}")
    finally:
        cur.close()
        conn.close()
        
    print("--- DELETE SURVEY END ---\n")
    return redirect("/user-survey-data?deleted=1")


@app.route("/test-db")
def test_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, name, designation, photo_name, photo_path FROM users")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)


@app.route("/fix-report-template")
def fix_report_template():
    import re
    file_path = os.path.join(BASE_DIR, "templates", "report.html")
    with open(file_path, "rb") as f:
        content = f.read()

    # Find the orphaned code block between the new downloadReport closing brace and showReportDocMessage
    pattern = rb'(\n    \}\r?\n)\r?\n\s+lines\.push.*?(\r?\n    showReportDocMessage)'
    replacement = rb'\1\2'
    new_content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)

    if new_content == content:
        return "No changes needed or pattern not found"

    with open(file_path, "wb") as f:
        f.write(new_content)

    return "Fixed! Orphaned lines removed from report.html"




# ================= COMMON PAGES (FIX) =================

# ================= COMMON PAGES (FIX) =================

@app.route("/my-account", methods=["GET", "POST"])
def my_account():
    if require_login():
        return redirect("/")

    role = session.get("role", "admin")

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
            absolute_path = os.path.join(UPLOADS_BASE, "images", filename)
            uploaded_file.save(absolute_path)
            profile["photo_name"] = uploaded_file.filename
            profile["photo_path"] = relative_path

        session["profile"] = profile
        session.modified = True
        save_profile(session.get("user"), profile)
        return redirect("/my-account?saved=1")

    template_name = "my_account_ground.html" if role == "ground" else "my_account.html"
    return render_page(
        template_name,
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


@app.route("/uploads/<path:filename>")
def serve_uploads(filename):
    return send_from_directory(UPLOADS_BASE, filename)

# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
