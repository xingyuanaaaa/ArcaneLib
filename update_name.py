# -*- coding: utf-8 -*-
import sqlite3
conn = sqlite3.connect(r'd:\.SOLO Csde\项目1\software-library\data\software_library.db')
conn.execute("UPDATE system_config SET config_value=? WHERE config_key=?", ('Arcane库', 'site_name'))
conn.commit()
cur = conn.execute("SELECT config_value FROM system_config WHERE config_key='site_name'")
print('Updated:', cur.fetchone()[0])
conn.close()