import sys, secrets
sys.path.insert(0, r'd:\.SOLO Csde\项目1\software-library')
from models import get_db

db = get_db()

codes = []
for i in range(5):
    code = 'ARC-' + secrets.token_hex(6).upper()[:12]
    db.execute(
        "INSERT INTO card_keys (card_key, card_type, vip_days, points, status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (code, 'register', 0, 0, 'unused', '注册邀请码')
    )
    codes.append(code)

# 同时生成VIP和积分邀请码
vip1 = 'VIP-' + secrets.token_hex(6).upper()[:12]
vip2 = 'VIP-' + secrets.token_hex(6).upper()[:12]
pts1 = 'PTS-' + secrets.token_hex(6).upper()[:12]

db.execute(
    "INSERT INTO card_keys (card_key, card_type, vip_days, points, status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
    (vip1, 'vip', 30, 0, 'unused', 'VIP30天邀请码')
)
db.execute(
    "INSERT INTO card_keys (card_key, card_type, vip_days, points, status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
    (vip2, 'vip', 30, 0, 'unused', 'VIP30天邀请码')
)
db.execute(
    "INSERT INTO card_keys (card_key, card_type, vip_days, points, status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
    (pts1, 'points', 0, 500, 'unused', '500积分邀请码')
)

db.commit()
db.close()

for c in codes:
    print(f"注册邀请码: {c}")
print(f"VIP30天邀请码(1): {vip1}")
print(f"VIP30天邀请码(2): {vip2}")
print(f"500积分邀请码: {pts1}")