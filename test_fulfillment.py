import urllib.request
import urllib.parse
import urllib.error
import json
from http.cookiejar import CookieJar

cj = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
urllib.request.install_opener(opener)

# 1. Login as admin
data = urllib.parse.urlencode({"username": "admin", "password": "password123"}).encode()
req = urllib.request.Request("http://localhost:5000/login", data=data)
urllib.request.urlopen(req)

# 2. Submit route request
req_data = json.dumps({
    "transfer_id": "TEST-TR-999",
    "source_warehouse": "PUNE YARD",
    "destination_warehouse": "MUMBAI SITE",
    "material_description": "11kV Cable",
    "quantity": "500",
    "vehicle_type": "Truck",
    "remarks": "Urgent transfer"
}).encode()
req = urllib.request.Request("http://localhost:5000/submit-route-request", data=req_data, headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req)
print("Admin Submit:", res.read().decode())

from app import get_conn
conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT id FROM route_requests WHERE transfer_id = 'TEST-TR-999' ORDER BY id DESC LIMIT 1")
req_id = cur.fetchone()[0]
cur.close()
conn.close()

print(f"Created request ID: {req_id}")

urllib.request.urlopen("http://localhost:5000/logout")

# 3. Login as ground
data = urllib.parse.urlencode({"username": "PUNE YARD", "password": "password123"}).encode()
req = urllib.request.Request("http://localhost:5000/login", data=data)
urllib.request.urlopen(req)

# 4. Fulfil
fulfil_data = json.dumps({"id": req_id}).encode()
req = urllib.request.Request("http://localhost:5000/fulfil-route-request", data=fulfil_data, headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req)
print("Ground Fulfil:", res.read().decode())
