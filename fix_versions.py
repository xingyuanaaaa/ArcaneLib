# -*- coding: utf-8 -*-
import os
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

import requests, re

BASE = "https://web-production-90119.up.railway.app"
s = requests.Session()
s.verify = False
requests.packages.urllib3.disable_warnings()

# 登录
r = s.post(f"{BASE}/api/login", json={"username": "admin", "password": "admin123456"})
print("登录:", r.json().get("success"))

# 获取页面 + CSRF
r = s.get(f"{BASE}/admin/versions")
m = re.search(r'csrf_token" value="([^"]+)"', r.text)
csrf = m.group(1)
print(f"CSRF: {csrf[:16]}...")

# 作废 1.0.0 (ID=1)
r = s.post(f"{BASE}/admin/api/version/toggle/1", data={"csrf_token": csrf}, allow_redirects=False)
print(f"Toggle 1: {r.status_code}")

# 恢复 1.0.1 (ID=2)
r = s.get(f"{BASE}/admin/versions")
m = re.search(r'csrf_token" value="([^"]+)"', r.text)
csrf2 = m.group(1)
r = s.post(f"{BASE}/admin/api/version/toggle/2", data={"csrf_token": csrf2}, allow_redirects=False)
print(f"Toggle 2: {r.status_code}")

# 验证
r1 = s.get(f"{BASE}/api/check-version?version=1.0.0")
r2 = s.get(f"{BASE}/api/check-version?version=1.0.1")
print(f"1.0.0: {r1.json()}")
print(f"1.0.1: {r2.json()}")

if r1.json().get("valid") == False and r2.json().get("valid") == True:
    print("\n✅ 状态正确！1.0.0已作废，1.0.1有效")
else:
    print("\n❌ 状态不正确，重新尝试...")
    # 再试一次
    r = s.get(f"{BASE}/admin/versions")
    csrf3 = re.search(r'csrf_token" value="([^"]+)"', r.text).group(1)
    s.post(f"{BASE}/admin/api/version/toggle/1", data={"csrf_token": csrf3}, allow_redirects=False)
    
    r = s.get(f"{BASE}/admin/versions")
    csrf4 = re.search(r'csrf_token" value="([^"]+)"', r.text).group(1)
    s.post(f"{BASE}/admin/api/version/toggle/2", data={"csrf_token": csrf4}, allow_redirects=False)
    
    r1 = s.get(f"{BASE}/api/check-version?version=1.0.0")
    r2 = s.get(f"{BASE}/api/check-version?version=1.0.1")
    print(f"1.0.0: {r1.json()}")
    print(f"1.0.1: {r2.json()}")