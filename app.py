# -*- coding: utf-8 -*-
# 软件库系统 - 主应用入口
# 非公益软件库，包含卡密兑换、机器码绑定等商业化功能

import os
import sys
import secrets
import hashlib
import logging
from datetime import datetime
from flask import Flask, session, g, request, redirect, url_for, flash, render_template, jsonify, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from config import (
    BASE_DIR, SECRET_KEY, DATABASE_PATH, UPLOAD_FOLDER,
    SOFTWARE_UPLOAD_FOLDER, IMAGE_UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH, ADMIN_USERNAME, ADMIN_PASSWORD_HASH
)
from models import init_db, get_db, query_db, execute_db, get_config

# 确保必要目录存在
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
os.makedirs(SOFTWARE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)


def create_app():
    """创建Flask应用"""
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # 初始化数据库
    init_db()
    _init_admin_account()

    # 配置日志
    _setup_logging(app)

    # 注册蓝图
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')

    # 全局上下文
    @app.context_processor
    def inject_globals():
        categories = query_db('SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order')
        announcements = query_db(
            'SELECT * FROM announcements WHERE is_active = 1 ORDER BY is_pinned DESC, priority DESC, created_at DESC LIMIT 5'
        )
        site_name = get_config('site_name') or '软件库'
        return dict(
            categories=categories,
            announcements=announcements,
            site_name=site_name,
            now=datetime.now()
        )

    # 请求前处理
    @app.before_request
    def before_request():
        g.user = None

        # IP黑名单检查
        client_ip = request.remote_addr
        banned = query_db("SELECT * FROM ip_blacklist WHERE ip_address = ? AND (expires_at IS NULL OR expires_at > datetime('now', 'localtime'))", (client_ip,), one=True)
        if banned:
            return jsonify({'success': False, 'message': '访问被拒绝'}), 403

        # 会话IP绑定检查
        if 'user_id' in session:
            session_ip = session.get('bound_ip')
            if session_ip and session_ip != client_ip:
                session.clear()
                return redirect(url_for('auth.login_page'))

        if 'user_id' in session:
            g.user = query_db('SELECT * FROM users WHERE id = ?', (session['user_id'],), one=True)
            if g.user and g.user['is_banned']:
                session.clear()
                return render_template('403.html'), 403

        # 生成CSRF令牌
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)

        # 频率检测：1分钟内超过60次请求自动封IP
        if not request.path.startswith('/static/'):
            recent_count = query_db(
                "SELECT COUNT(*) as cnt FROM access_logs WHERE ip_address = ? AND created_at > datetime('now', 'localtime', '-60 seconds')",
                (client_ip,), one=True
            )
            if recent_count and recent_count['cnt'] > 60:
                execute_db(
                    "INSERT OR IGNORE INTO ip_blacklist (ip_address, reason, expires_at) VALUES (?, ?, datetime('now', 'localtime', '+1 hour'))",
                    (client_ip, '请求频率过高')
                )

        # 记录访问日志
        if not request.path.startswith('/static/'):
            try:
                execute_db(
                    'INSERT INTO access_logs (user_id, action, ip_address, user_agent) VALUES (?, ?, ?, ?)',
                    (session.get('user_id'), request.path, client_ip, request.headers.get('User-Agent', '')[:500])
                )
            except Exception:
                pass

    # 响应后添加安全头
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' http://127.0.0.1:* http://192.168.*:*; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers['Strict-Transport-Security'] = 'max-age=0'
        return response

    # 错误处理
    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('500.html'), 500

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    return app


def _init_admin_account():
    """初始化管理员账户"""
    admin = query_db('SELECT * FROM users WHERE username = ?', (ADMIN_USERNAME,), one=True)
    if not admin:
        password_hash = generate_password_hash('admin123456', method='pbkdf2:sha256:600000')
        execute_db(
            'INSERT INTO users (username, password_hash, email, role, vip_level) VALUES (?, ?, ?, ?, ?)',
            (ADMIN_USERNAME, password_hash, 'admin@localhost', 'admin', 99)
        )
        print(f"[系统] 管理员账户已创建: {ADMIN_USERNAME} / admin123456")
        print("[安全] 请立即登录后台修改管理员密码!")


def _setup_logging(app):
    """配置日志"""
    from config import LOG_LEVEL, LOG_FILE
    handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(getattr(logging, LOG_LEVEL))


app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("  软件库系统 v1.0 - 启动中...")
    print("=" * 60)
    print(f"  访问地址: http://127.0.0.1:5000")
    print(f"  管理后台: http://127.0.0.1:5000/admin")
    print(f"  默认管理员: admin / admin123456")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)