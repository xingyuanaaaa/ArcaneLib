# -*- coding: utf-8 -*-
# 软件库系统 - 数据库模型

import sqlite3
import os
import time
from datetime import datetime
from config import DATABASE_PATH, BASE_DIR


def get_db():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()

    # 用户表
    cursor.execute('''
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

    # 软件分类表
    cursor.execute('''
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

    # 软件表
    cursor.execute('''
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

    # 卡密表
    cursor.execute('''
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

    # 公告表
    cursor.execute('''
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

    # 用户反馈表
    cursor.execute('''
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

    # 下载记录表
    cursor.execute('''
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

    # 广告位表
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

    # 系统配置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT UNIQUE NOT NULL,
            config_value TEXT,
            description TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # 访问日志表
    cursor.execute('''
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

    # 安全日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            ip_address TEXT,
            details TEXT,
            severity TEXT DEFAULT 'info',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # IP黑名单表
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

    # 应用版本表（用于版本校验/作废机制）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_code TEXT NOT NULL,
            version_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(version_code)
        )
    ''')

    # 签到记录表
    cursor.execute('''
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

    # 收藏表
    cursor.execute('''
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

    # 关注更新表
    cursor.execute('''
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

    # 插入默认分类
    default_categories = [
        ('系统工具', '系统优化、驱动管理、系统修复等工具软件', 'fa-cog', 1),
        ('安全防护', '杀毒软件、防火墙、隐私保护等安全软件', 'fa-shield-alt', 2),
        ('办公软件', 'Office、PDF编辑、笔记等办公效率软件', 'fa-file-alt', 3),
        ('多媒体', '视频播放、音频编辑、图像处理等多媒体软件', 'fa-play-circle', 4),
        ('编程开发', 'IDE、编辑器、数据库工具等开发软件', 'fa-code', 5),
        ('网络工具', '浏览器、下载工具、远程控制等网络软件', 'fa-globe', 6),
        ('游戏相关', '游戏加速器、修改器、辅助工具等', 'fa-gamepad', 7),
        ('其他软件', '其他类型的软件工具', 'fa-ellipsis-h', 8),
    ]
    for cat in default_categories:
        cursor.execute(
            'INSERT OR IGNORE INTO categories (name, description, icon, sort_order) VALUES (?, ?, ?, ?)',
            cat
        )

    # 插入默认系统配置
    default_configs = [
        ('site_name', 'Arcane库', '网站名称'),
        ('site_description', '专业软件资源库', '网站描述'),
        ('site_keywords', '软件下载,软件库,免费软件', '网站关键词'),
        ('maintenance_mode', '0', '维护模式'),
        ('allow_register', '1', '是否允许注册'),
        ('download_interval', '30', '下载间隔(秒)'),
        ('max_downloads_per_day', '50', '每日最大下载次数'),
    ]
    for cfg in default_configs:
        cursor.execute(
            'INSERT OR IGNORE INTO system_config (config_key, config_value, description) VALUES (?, ?, ?)',
            cfg
        )

    # 插入默认应用版本
    default_versions = [
        ('1.0.0', '初始版本(已作废)', 0),
        ('1.0.1', '最新版本', 1),
    ]
    for ver in default_versions:
        cursor.execute(
            'INSERT OR IGNORE INTO app_versions (version_code, version_name, is_active) VALUES (?, ?, ?)',
            ver
        )

    conn.commit()
    conn.close()


def query_db(query, args=(), one=False):
    """执行查询"""
    conn = get_db()
    cur = conn.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    """执行修改"""
    conn = get_db()
    cur = conn.execute(query, args)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def get_config(key):
    """获取系统配置"""
    result = query_db('SELECT config_value FROM system_config WHERE config_key = ?', (key,), one=True)
    return result['config_value'] if result else None


def set_config(key, value):
    """设置系统配置"""
    execute_db(
        'INSERT OR REPLACE INTO system_config (config_key, config_value, updated_at) VALUES (?, ?, datetime("now", "localtime"))',
        (key, value)
    )