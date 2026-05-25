import re

app_py_path = r"c:\Users\shraddha.more\Desktop\EPC\app.py"

with open(app_py_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update update_route_request_status
target_update = """    cur.execute("UPDATE route_requests SET status = %s, admin_note = %s WHERE id = %s", (status, admin_note, req_id))

    if status == 'Approved':
        cur.execute("SELECT transfer_id, source_warehouse, destination_warehouse, material_description, quantity FROM route_requests WHERE id = %s", (req_id,))
        row = cur.fetchone()
        if row:
            t_id, src, dst, desc, qty = row
            import datetime
            today_str = datetime.date.today().isoformat()
            
            cur.execute(\"\"\"
                INSERT INTO outward_info (out_dc_no, out_warehouse, out_description, out_qty, out_dc_date, out_remark, source_tag)
                VALUES (%s, %s, %s, %s, %s, %s, 'manual')
            \"\"\", (t_id, src, desc, qty, today_str, "Auto-deducted via Route Request: " + admin_note))

            cur.execute(\"\"\"
                INSERT INTO basic_info (dc_no, warehouse, description, qty, challan_date, wh_remark, source_tag)
                VALUES (%s, %s, %s, %s, %s, %s, 'manual')
            \"\"\", (t_id, dst, desc, qty, today_str, "Auto-added via Route Request: " + admin_note))
    conn.commit()
    cur.close()
    conn.close()
    
    if status == 'Approved' and row:
        try:
            recalculate_warehouse_item(src, desc)
            recalculate_warehouse_item(dst, desc)
        except:
            pass

    return jsonify({"message": "Status updated successfully"})"""

new_update = """    cur.execute("UPDATE route_requests SET status = %s, admin_note = %s WHERE id = %s", (status, admin_note, req_id))
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
    
    cur.execute(\"\"\"
        INSERT INTO outward_info (out_dc_no, out_warehouse, out_description, out_qty, out_dc_date, out_remark, source_tag)
        VALUES (%s, %s, %s, %s, %s, %s, 'manual')
    \"\"\", (t_id, src, desc, qty, today_str, "Auto-deducted via Route Request Fulfillment"))

    cur.execute(\"\"\"
        INSERT INTO basic_info (dc_no, warehouse, description, qty, challan_date, wh_remark, source_tag)
        VALUES (%s, %s, %s, %s, %s, %s, 'manual')
    \"\"\", (t_id, dst, desc, qty, today_str, "Auto-added via Route Request Fulfillment"))
    
    conn.commit()
    cur.close()
    conn.close()
    
    try:
        recalculate_warehouse_item(src, desc)
        recalculate_warehouse_item(dst, desc)
    except Exception as e:
        pass

    return jsonify({"message": "Request fulfilled successfully"})"""

if target_update in content:
    content = content.replace(target_update, new_update)
else:
    print("Could not find update_route_request_status target!")

# 2. Add incoming_requests route
incoming_route = """
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
"""
if "@app.route(\"/my-route-requests\")" in content and "def incoming_requests" not in content:
    content = content.replace("@app.route(\"/my-route-requests\")", incoming_route.strip() + "\n\n@app.route(\"/my-route-requests\")")

# 3. Update submit_route_request so admin submissions become 'Approved (Pending Fulfillment)'
target_submit = """    cur.execute(
        \"\"\"
        INSERT INTO route_requests (transfer_id, source_warehouse, destination_warehouse, material_description, quantity, vehicle_type, remarks)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        \"\"\",
        (
            payload.get("transfer_id"),
            payload.get("source_warehouse"),
            payload.get("destination_warehouse"),
            payload.get("material_description"),
            payload.get("quantity"),
            payload.get("vehicle_type"),
            payload.get("remarks", "")
        )
    )"""

new_submit = """    status = "Approved (Pending Fulfillment)" if session.get("role") == "admin" else "Pending"
    
    cur.execute(
        \"\"\"
        INSERT INTO route_requests (transfer_id, source_warehouse, destination_warehouse, material_description, quantity, vehicle_type, remarks, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        \"\"\",
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
    )"""

if target_submit in content:
    content = content.replace(target_submit, new_submit)
else:
    print("Could not find submit target!")

with open(app_py_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated app.py successfully!")
