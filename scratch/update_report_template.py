import os

path = r'd:\enterprise resource\templates\report.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add CSS
css_to_add = """
    .btn-delete-report {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 8px;
        background: #fee2e2;
        color: #ef4444;
        border: 1px solid #fecaca;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .btn-delete-report:hover {
        background: #fecaca;
        color: #dc2626;
        transform: scale(1.1);
    }
"""
if '.btn-delete-report' not in content:
    content = content.replace('</style>', css_to_add + '</style>')

# Add groups and headers
content = content.replace('{ name: "Approvals", count: 2 }', '{ name: "Approvals", count: 2 },\n                { name: "Actions", count: 1 }')
content = content.replace('{ key: "approved_tpa", label: "Approved by TPA" }', '{ key: "approved_tpa", label: "Approved by TPA" },\n                { key: "actions", label: "Action" }')

content = content.replace('{ name: "Other", count: 2 }', '{ name: "Other", count: 2 },\n                { name: "Actions", count: 1 }')
content = content.replace('{ key: "out_frt", label: "FRT" }', '{ key: "out_frt", label: "FRT" },\n                { key: "actions", label: "Action" }')

# Update renderReportTable
old_render = """        rows.forEach((row) => {
            const tr = document.createElement("tr");
            config.headers.forEach((header) => {
                const td = document.createElement("td");
                td.textContent = safeValue(row[header.key]);
                tr.appendChild(td);
            });
            fragment.appendChild(tr);
        });"""

new_render = """        rows.forEach((row) => {
            const tr = document.createElement("tr");
            config.headers.forEach((header) => {
                const td = document.createElement("td");
                if (header.key === "actions") {
                    td.innerHTML = `
                        <form action="/delete-report-entry" method="POST" onsubmit="return confirm('Delete this record?');">
                            <input type="hidden" name="id" value="${row.id}">
                            <input type="hidden" name="type" value="${type}">
                            <button type="submit" class="btn-delete-report" title="Delete Entry">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                </svg>
                            </button>
                        </form>
                    `;
                } else {
                    td.textContent = safeValue(row[header.key]);
                }
                tr.appendChild(td);
            });
            fragment.appendChild(tr);
        });"""

if old_render in content:
    content = content.replace(old_render, new_render)
else:
    # Try with a more generic match if exact match fails
    print("Exact match for render loop failed, trying fallback")
    content = content.replace('td.textContent = safeValue(row[header.key]);', 
                              'if (header.key === "actions") { td.innerHTML = `<form action="/delete-report-entry" method="POST" onsubmit="return confirm(\'Delete this record?\');"><input type="hidden" name="id" value="${row.id}"><input type="hidden" name="type" value="${type}"><button type="submit" class="btn-delete-report" title="Delete Entry"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button></form>`; } else { td.textContent = safeValue(row[header.key]); }')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
