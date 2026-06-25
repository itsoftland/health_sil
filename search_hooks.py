import os
import sys

sys.path.insert(0, '/home/silpc-064/frappe-bench/apps/frappe')
sys.path.insert(0, '/home/silpc-064/frappe-bench/apps/erpnext')
sys.path.insert(0, '/home/silpc-064/frappe-bench/apps/health_sil')
sys.path.insert(0, '/home/silpc-064/frappe-bench/apps/healthcare')
sys.path.insert(0, '/home/silpc-064/frappe-bench/apps/hrms')
sys.path.insert(0, '/home/silpc-064/frappe-bench/apps/india_compliance')
sys.path.insert(0, '/home/silpc-064/frappe-bench/apps/payments')

import frappe

os.chdir('/home/silpc-064/frappe-bench/sites')

sites = ['demo.com', 'site1.local', 'site2.local']
for site in sites:
    print(f"--- SITE: {site} ---")
    try:
        frappe.init(site=site, sites_path='.')
        hooks = frappe.get_hooks()
        
        def search_dict(d, path=""):
            if isinstance(d, dict):
                for k, v in d.items():
                    search_dict(v, f"{path}.{k}" if path else k)
            elif isinstance(d, list):
                for i, v in enumerate(d):
                    search_dict(v, f"{path}[{i}]")
            elif isinstance(d, str):
                if 'sqlite_search' in d or 'sqlite' in d:
                    print(f"Found in hooks: {path} -> {d}")
            else:
                pass
        
        search_dict(hooks)
        frappe.destroy()
    except Exception as e:
        print(f"Error: {e}")
