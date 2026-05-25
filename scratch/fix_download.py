import re

file_path = r"d:\enterprise resource\templates\report.html"

with open(file_path, "rb") as f:
    content = f.read()

# Find the downloadReport function and replace it
old_func_pattern = rb'    function downloadReport\(\) \{.*?(?=\r?\n    showReportDocMessage)'

new_func = b'''    function downloadReport() {\r
        const type = document.getElementById("report_type").value;\r
        const config = reportConfigs[type];\r
        const searchTerm_dl = document.getElementById("report_search").value.trim();\r
        const searchField_dl = document.getElementById("report_search_field").value || "all";\r
        const category_dl = document.getElementById("report_category").value || "";\r
        const subCategory_dl = document.getElementById("report_sub_category").value || "";\r
        const material_dl = document.getElementById("report_material") ? document.getElementById("report_material").value : "";\r
\r
        var yearQ = selectedReportYear && selectedReportYear !== "all" ? "&year=" + selectedReportYear : "";\r
        var searchQ = searchTerm_dl ? "&search=" + encodeURIComponent(searchTerm_dl) + "&field=" + encodeURIComponent(searchField_dl) : "";\r
        var catQ = category_dl ? "&category=" + encodeURIComponent(category_dl) : "";\r
        var subCatQ = subCategory_dl ? "&sub_category=" + encodeURIComponent(subCategory_dl) : "";\r
        var matQ = material_dl ? "&material=" + encodeURIComponent(material_dl) : "";\r
\r
        var btn = document.querySelector(".download-btn");\r
        if (btn) {\r
            btn.disabled = true;\r
            btn.querySelector("span").textContent = "Preparing Download...";\r
        }\r
\r
        fetch("/report-data-export?type=" + type + yearQ + searchQ + catQ + subCatQ + matQ)\r
            .then(function(res) {\r
                if (!res.ok) throw new Error("Export failed");\r
                return res.json();\r
            })\r
            .then(function(payload) {\r
                var allRows = Array.isArray(payload.data) ? payload.data : [];\r
                var csvLines = [];\r
                var exportHeaders = config.headers.filter(function(h) { return h.key !== "actions"; });\r
\r
                csvLines.push(exportHeaders.map(function(h) { return \'"\' + h.label.replace(/"/g, \'""\') + \'"\'; }).join(","));\r
\r
                allRows.forEach(function(row) {\r
                    csvLines.push(exportHeaders.map(function(h) { return \'"\' + String(safeValue(row[h.key])).replace(/"/g, \'""\') + \'"\'; }).join(","));\r
                });\r
\r
                var blob = new Blob([csvLines.join("\\n")], { type: "text/csv;charset=utf-8;" });\r
                var dlUrl = URL.createObjectURL(blob);\r
                var link = document.createElement("a");\r
                var stamp = new Date().toISOString().split("T")[0];\r
                link.href = dlUrl;\r
                link.download = config.badge + "_Report_" + stamp + ".csv";\r
                document.body.appendChild(link);\r
                link.click();\r
                document.body.removeChild(link);\r
                URL.revokeObjectURL(dlUrl);\r
            })\r
            .catch(function(err) {\r
                console.error("Download error:", err);\r
                alert("Failed to download report. Please try again.");\r
            })\r
            .then(function() {\r
                if (btn) {\r
                    btn.disabled = false;\r
                    btn.querySelector("span").textContent = "Download Excel";\r
                }\r
            });\r
    }'''

result = re.sub(old_func_pattern, new_func, content, count=1, flags=re.DOTALL)

if result == content:
    print("ERROR: Pattern not matched!")
else:
    with open(file_path, "wb") as f:
        f.write(result)
    print("SUCCESS: downloadReport function replaced!")
    
    # Verify
    with open(file_path, "rb") as f:
        verify = f.read()
    if b"report-data-export" in verify:
        print("VERIFIED: New export endpoint reference found in file.")
    else:
        print("WARNING: Could not verify the replacement.")
