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
    "approved_dpm", "approved_tpa",
    "task_id",
    "ch_invoice_no", "ch_invoice_date", "ch_submitted", "ch_remark"
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
    "pm_update_date", "pm_submit_date", "approved_dpm", "approved_tpa", "ch_invoice_date"
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
        db_scalar(record.get("approved_tpa"), is_date=True),
        db_scalar(record.get("task_id")),
        db_scalar(record.get("ch_invoice_no")),
        db_scalar(record.get("ch_invoice_date"), is_date=True),
        db_scalar(record.get("ch_submitted")),
        db_scalar(record.get("ch_remark"))
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
            out_frt TEXT
        )
        """
    )


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

    if REAL_DATA_BOOTSTRAPPED and not force:
        return

    seed_data = load_sample_report_data()
    conn = get_conn()
    cur = conn.cursor()

    try:
        ensure_outward_table(cur)

        for record in seed_data.get("inward", []):
            if inward_record_exists(cur, record):
                continue

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
                    approved_dpm, approved_tpa,
                    task_id,
                    ch_invoice_no, ch_invoice_date, ch_submitted, ch_remark
                )
                VALUES ({})
                """.format(", ".join(["%s"] * 61)),
                inward_db_values(record)
            )

        for record in seed_data.get("outward", []):
            if outward_record_exists(cur, record):
                continue

            cur.execute(
                """
                INSERT INTO outward_info (
                    out_sr_no, out_atn, out_month, out_warehouse, out_shipment_type, out_dispatch_type,
                    out_in_doc_no, out_dc_no, out_dc_date, out_vendor_name, out_gp_location, out_block, out_dist,
                    out_item_code, out_description, out_qty, out_physical_qty, out_unit, out_rate_per_unit,
                    out_total_value, out_taxable_value, out_tsc, out_discount, out_freight_charge, out_total,
                    out_cgst, out_sgst, out_grand_total, out_transport_name, out_vehicle_no, out_pkgs_qty,
                    out_dispatched_date, out_mode_of_delivery, out_reporting_time, out_loading_time, out_remark,
                    out_ug_aerial, out_frt
                )
                VALUES ({})
                """.format(", ".join(["%s"] * 38)),
                outward_db_values(record)
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


def get_inward_report_records(limit=None):
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
            approved_dpm, approved_tpa,
            task_id,
            ch_invoice_no, ch_invoice_date, ch_submitted, ch_remark
        FROM basic_info
        ORDER BY id DESC
    """

    if limit:
        query += " LIMIT %s"
        cur.execute(query, (limit,))
    else:
        cur.execute(query)

    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    cur.close()
    conn.close()

    return [dict(zip(columns, row)) for row in rows]


def get_outward_report_records(limit=None):
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
        ORDER BY id DESC
    """

    if limit:
        query += " LIMIT %s"
        cur.execute(query, (limit,))
    else:
        cur.execute(query)

    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    cur.close()
    conn.close()

    return [dict(zip(columns, row)) for row in rows]


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
        data.get("approved_tpa") or None,

        data.get("task_id"),

        data.get("ch_invoice_no"),
        data.get("ch_invoice_date") or None,
        data.get("ch_submitted"),
        data.get("ch_remark")
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
            approved_dpm, approved_tpa,
            task_id,
            ch_invoice_no, ch_invoice_date, ch_submitted, ch_remark
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

    return jsonify({"message": "Saved successfully"})


@app.route("/basic-info")
def get_basic_info():
    if require_role("admin"):
        return redirect("/")

    return jsonify([prepare_inward_record(record) for record in get_inward_report_records()])


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
                out_ug_aerial, out_frt
            )
            VALUES ({})
            """.format(", ".join(["%s"] * 38)),
            outward_db_values(data)
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

    return jsonify([prepare_outward_record(record) for record in get_outward_report_records()])


@app.route("/report-data")
def report_data():
    if require_role("admin"):
        return redirect("/")

    report_type = request.args.get("type", "inward").lower()

    if report_type == "outward":
        return jsonify([prepare_outward_record(record) for record in get_outward_report_records()])

    return jsonify([prepare_inward_record(record) for record in get_inward_report_records()])




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
