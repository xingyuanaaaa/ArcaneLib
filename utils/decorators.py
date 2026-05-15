# -*- coding: utf-8 -*-
# 软件库系统 - 装饰器模块
# 提供登录验证、管理员验证、防刷等装饰器

from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify, g
from models import query_db, execute_db
import time


def login_required(f):
    """需要登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': '请先登录'}), 401
            flash('请先登录后再访问', 'warning')
            return redirect(url_for('auth.login_page'))
        g.user = query_db('SELECT * FROM users WHERE id = ?', (session['user_id'],), one=True)
        if not g.user or not g.user['is_active']:
            session.clear()
            return redirect(url_for('auth.login_page'))
        if g.user['is_banned']:
            session.clear()
            flash('您的账号已被封禁: ' + (g.user['ban_reason'] or '违反用户协议'), 'danger')
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """需要管理员权限的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': '请先登录'}), 401
            flash('请先登录', 'warning')
            return redirect(url_for('auth.login_page'))
        g.user = query_db('SELECT * FROM users WHERE id = ?', (session['user_id'],), one=True)
        if not g.user or g.user['role'] != 'admin':
            if request.is_json:
                return jsonify({'success': False, 'message': '权限不足'}), 403
            flash('权限不足', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def rate_limit(max_requests=10, window=60):
    """请求频率限制装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr
            endpoint = request.endpoint
            key = f"rate_limit:{ip}:{endpoint}"
            now = time.time()
            records = query_db(
                'SELECT COUNT(*) as cnt FROM access_logs WHERE ip_address = ? AND action = ? AND created_at > datetime(?, "unixepoch", "localtime")',
                (ip, endpoint, now - window),
                one=True
            )
            if records and records['cnt'] >= max_requests:
                return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def anti_bot(f):
    """防机器人装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_agent = request.headers.get('User-Agent', '')
        if not user_agent or len(user_agent) < 10:
            return jsonify({'success': False, 'message': '非法请求'}), 403
        return f(*args, **kwargs)
    return decorated_function


def csrf_protect(f):
    """CSRF保护装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            session_token = session.get('csrf_token')
            if not token or not session_token or token != session_token:
                if request.is_json:
                    return jsonify({'success': False, 'message': 'CSRF验证失败'}), 403
                flash('安全验证失败，请刷新页面重试', 'danger')
                return redirect(request.referrer or url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function