# -*- coding: utf-8 -*-
# 杞欢搴撶郴缁?- 鏁版嵁搴撴ā鍨?
import sqlite3
import os
import time
from datetime import datetime
from config import DATABASE_PATH, BASE_DIR


def get_db():
    """鑾峰彇鏁版嵁搴撹繛鎺?""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """鍒濆鍖栨暟鎹簱琛?""
    conn = get_db()
    cursor = conn.cursor()

    # 鐢ㄦ埛琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE,
            role TEXT DEFAULT 'user',
            machine_code TEXT,
            machine_code_bound INTEGER DEFAULT 0,
            vip_level INTEGER DEFAULT 0,
            vip_expire_time TEXT,
            points INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            last_login TEXT,
            login_ip TEXT
        )
    ''')

    # 杞欢鍒嗙被琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            icon TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # 杞欢琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS software (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT,
            category_id INTEGER,
            description TEXT,
            long_description TEXT,
            cover_image TEXT,
            screenshots TEXT,
            file_path TEXT,
            file_size INTEGER DEFAULT 0,
            file_hash TEXT,
            download_url TEXT,
            official_url TEXT,
            platform TEXT DEFAULT 'Windows',
            tags TEXT,
            is_free INTEGER DEFAULT 0,
            require_vip INTEGER DEFAULT 0,
            require_points INTEGER DEFAULT 0,
            download_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            rating REAL DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_featured INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        )
    ''')

    # 鍗″瘑琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_key TEXT UNIQUE NOT NULL,
            card_type TEXT DEFAULT 'vip',
            vip_days INTEGER DEFAULT 30,
            points INTEGER DEFAULT 0,
            status TEXT DEFAULT 'unused',
            used_by INTEGER,
            used_at TEXT,
            bound_machine_code TEXT,
            generated_by INTEGER,
            batch_id TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (used_by) REFERENCES users(id),
            FOREIGN KEY (generated_by) REFERENCES users(id)
        )
    ''')

    # 鍏憡琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            priority INTEGER DEFAULT 0,
            is_pinned INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')

    # 鐢ㄦ埛鍙嶉琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            type TEXT DEFAULT 'suggestion',
            status TEXT DEFAULT 'pending',
            admin_reply TEXT,
            replied_by INTEGER,
            replied_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # 涓嬭浇璁板綍琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            software_id INTEGER,
            software_name TEXT,
            ip_address TEXT,
            machine_code TEXT,
            downloaded_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (software_id) REFERENCES software(id)
        )
    ''')

    # 骞垮憡浣嶈〃
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position TEXT NOT NULL,
            ad_type TEXT DEFAULT 'image',
            image_url TEXT,
            link_url TEXT,
            title TEXT,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            start_time TEXT,
            end_time TEXT,
            view_count INTEGER DEFAULT 0,
            click_count INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # 绯荤粺閰嶇疆琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT UNIQUE NOT NULL,
            config_value TEXT,
            description TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # 璁块棶鏃ュ織琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            ip_address TEXT,
            user_agent TEXT,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # 瀹夊叏鏃ュ織琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            ip_address TEXT,
            details TEXT,
            severity TEXT DEFAULT 'info',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # IP榛戝悕鍗曡〃
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ip_blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            reason TEXT,
            blocked_by INTEGER,
            expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # 搴旂敤鐗堟湰琛紙鐢ㄤ簬鐗堟湰鏍￠獙/浣滃簾鏈哄埗锛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_code TEXT NOT NULL,
            version_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(version_code)
        )
    ''')

    # 绛惧埌璁板綍琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            checkin_date TEXT NOT NULL,
            points_earned INTEGER DEFAULT 10,
            consecutive_days INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(user_id, checkin_date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # 鏀惰棌琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            software_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(user_id, software_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (software_id) REFERENCES software(id)
        )
    ''')

    # 鍏虫敞鏇存柊琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            software_id INTEGER NOT NULL,
            notify_update INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(user_id, software_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (software_id) REFERENCES software(id)
        )
    ''')

    # 鎻掑叆榛樿鍒嗙被
    default_categories = [
        ('绯荤粺宸ュ叿', '绯荤粺浼樺寲銆侀┍鍔ㄧ鐞嗐€佺郴缁熶慨澶嶇瓑宸ュ叿杞欢', 'fa-cog', 1),
        ('瀹夊叏闃叉姢', '鏉€姣掕蒋浠躲€侀槻鐏銆侀殣绉佷繚鎶ょ瓑瀹夊叏杞欢', 'fa-shield-alt', 2),
        ('鍔炲叕杞欢', 'Office銆丳DF缂栬緫銆佺瑪璁扮瓑鍔炲叕鏁堢巼杞欢', 'fa-file-alt', 3),
        ('澶氬獟浣?, '瑙嗛鎾斁銆侀煶棰戠紪杈戙€佸浘鍍忓鐞嗙瓑澶氬獟浣撹蒋浠?, 'fa-play-circle', 4),
        ('缂栫▼寮€鍙?, 'IDE銆佺紪杈戝櫒銆佹暟鎹簱宸ュ叿绛夊紑鍙戣蒋浠?, 'fa-code', 5),
        ('缃戠粶宸ュ叿', '娴忚鍣ㄣ€佷笅杞藉伐鍏枫€佽繙绋嬫帶鍒剁瓑缃戠粶杞欢', 'fa-globe', 6),
        ('娓告垙鐩稿叧', '娓告垙鍔犻€熷櫒銆佷慨鏀瑰櫒銆佽緟鍔╁伐鍏风瓑', 'fa-gamepad', 7),
        ('鍏朵粬杞欢', '鍏朵粬绫诲瀷鐨勮蒋浠跺伐鍏?, 'fa-ellipsis-h', 8),
    ]
    for cat in default_categories:
        cursor.execute(
            'INSERT OR IGNORE INTO categories (name, description, icon, sort_order) VALUES (?, ?, ?, ?)',
            cat
        )

    # 鎻掑叆榛樿绯荤粺閰嶇疆
    default_configs = [
        ('site_name', 'Arcane搴?, '缃戠珯鍚嶇О'),
        ('site_description', '涓撲笟杞欢璧勬簮搴?, '缃戠珯鎻忚堪'),
        ('site_keywords', '杞欢涓嬭浇,杞欢搴?鍏嶈垂杞欢', '缃戠珯鍏抽敭璇?),
        ('maintenance_mode', '0', '缁存姢妯″紡'),
        ('allow_register', '1', '鏄惁鍏佽娉ㄥ唽'),
        ('download_interval', '30', '涓嬭浇闂撮殧(绉?'),
        ('max_downloads_per_day', '50', '姣忔棩鏈€澶т笅杞芥鏁?),
    ]
    for cfg in default_configs:
        cursor.execute(
            'INSERT OR IGNORE INTO system_config (config_key, config_value, description) VALUES (?, ?, ?)',
            cfg
        )

    # 鎻掑叆榛樿搴旂敤鐗堟湰
    default_versions = [
        ('1.0.0', '鍒濆鐗堟湰(宸蹭綔搴?', 0),
        ('1.0.1', '鏈€鏂扮増鏈?, 1),
    ]
    for ver in default_versions:
        cursor.execute(
            'INSERT OR IGNORE INTO app_versions (version_code, version_name, is_active) VALUES (?, ?, ?)',
            ver
        )

    conn.commit()
    conn.close()


def query_db(query, args=(), one=False):
    """鎵ц鏌ヨ"""
    conn = get_db()
    cur = conn.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    """鎵ц淇敼"""
    conn = get_db()
    cur = conn.execute(query, args)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def get_config(key):
    """鑾峰彇绯荤粺閰嶇疆"""
    result = query_db('SELECT config_value FROM system_config WHERE config_key = ?', (key,), one=True)
    return result['config_value'] if result else None


def set_config(key, value):
    """璁剧疆绯荤粺閰嶇疆"""
    execute_db(
        'INSERT OR REPLACE INTO system_config (config_key, config_value, updated_at) VALUES (?, ?, datetime("now", "localtime"))',
        (key, value)
    )