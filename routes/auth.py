# -*- coding: utf-8 -*-
# 软件库系统 - 认证路由

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import query_db, execute_db
from utils.decorators import login_required, rate_limit, csrf_protect
from utils.crypto import sha256_hash
import re
import secrets

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET'])
def login_page():
    """登录页面"""
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET'])
def register_page():
    """注册页面"""
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    allow_register = query_db("SELECT config_value FROM system_config WHERE config_key='allow_register'", one=True)
    if allow_register and allow_register['config_value'] == '0':
        flash('当前暂停新用户注册', 'warning')
        return redirect(url_for('auth.login_page'))
    return render_template('register.html')


@auth_bp.route('/api/login', methods=['POST'])
@rate_limit(max_requests=10, window=60)
def api_login():
    """登录API"""
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'success': False, 'message': '请输入用户名和密码'})

    user = query_db('SELECT * FROM users WHERE username = ?', (username,), one=True)
    if not user:
        return jsonify({'success': False, 'message': '用户名或密码错误'})

    if not user['is_active']:
        return jsonify({'success': False, 'message': '账号已被禁用'})

    if user['is_banned']:
        return jsonify({'success': False, 'message': f'账号已被封禁: {user["ban_reason"] or "违反用户协议"}'})

    if not check_password_hash(user['password_hash'], password):
        # 记录失败尝试
        execute_db(
            'INSERT INTO security_logs (event_type, ip_address, details, severity) VALUES (?, ?, ?, ?)',
            ('login_failed', request.remote_addr, f'用户: {username}', 'warning')
        )
        return jsonify({'success': False, 'message': '用户名或密码错误'})

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['csrf_token'] = secrets.token_hex(32)
    session['bound_ip'] = request.remote_addr

    execute_db(
        "UPDATE users SET last_login = datetime('now', 'localtime'), login_ip = ? WHERE id = ?",
        (request.remote_addr, user['id'])
    )

    return jsonify({
        'success': True,
        'message': '登录成功',
        'data': {
            'user_id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'redirect': url_for('main.index') if user['role'] != 'admin' else url_for('admin.dashboard')
        }
    })


@auth_bp.route('/api/register', methods=['POST'])
@rate_limit(max_requests=5, window=300)
def api_register():
    """注册API"""
    allow_register = query_db("SELECT config_value FROM system_config WHERE config_key='allow_register'", one=True)
    if allow_register and allow_register['config_value'] == '0':
        return jsonify({'success': False, 'message': '当前暂停新用户注册'})

    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip()
    machine_code = (data.get('machine_code') or '').strip()
    invite_code = (data.get('invite_code') or '').strip()

    if not invite_code:
        return jsonify({'success': False, 'message': '需要邀请码才能注册'})

    card = query_db(
        "SELECT * FROM card_keys WHERE card_key = ? AND card_type = 'register' AND status = 'unused'",
        (invite_code,), one=True
    )
    if not card:
        return jsonify({'success': False, 'message': '邀请码无效或已被使用'})

    if not machine_code:
        return jsonify({'success': False, 'message': '请先获取设备机器码'})

    # 验证用户名
    if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]{3,20}$', username):
        return jsonify({'success': False, 'message': '用户名需3-20位，支持中英文、数字和下划线'})

    # 验证密码
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少6位'})

    # 验证邮箱
    if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({'success': False, 'message': '邮箱格式不正确'})

    # 检查用户名是否存在
    existing = query_db('SELECT id FROM users WHERE username = ?', (username,), one=True)
    if existing:
        return jsonify({'success': False, 'message': '用户名已存在'})

    # 检查邮箱是否存在
    if email:
        existing_email = query_db('SELECT id FROM users WHERE email = ?', (email,), one=True)
        if existing_email:
            return jsonify({'success': False, 'message': '邮箱已被注册'})

    password_hash = generate_password_hash(password, method='pbkdf2:sha256:600000')

    user_id = execute_db(
        'INSERT INTO users (username, password_hash, email, machine_code, machine_code_bound) VALUES (?, ?, ?, ?, ?)',
        (username, password_hash, email, machine_code, 1 if machine_code else 0)
    )

    execute_db(
        "UPDATE card_keys SET status = 'used', used_by = ?, used_at = datetime('now', 'localtime') WHERE card_key = ?",
        (user_id, invite_code)
    )

    return jsonify({
        'success': True,
        'message': '注册成功，请登录',
        'data': {'user_id': user_id}
    })


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    """登出"""
    session.clear()
    return jsonify({'success': True, 'message': '已退出登录'})


@auth_bp.route('/api/user/info', methods=['GET'])
def api_user_info():
    """获取当前用户信息"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user = query_db('SELECT id, username, email, role, vip_level, vip_expire_time, points, machine_code_bound, created_at, last_login FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    return jsonify({
        'success': True,
        'data': dict(user)
    })


@auth_bp.route('/api/user/change_password', methods=['POST'])
@login_required
@csrf_protect
def api_change_password():
    """修改密码"""
    data = request.get_json() or {}
    old_password = data.get('old_password') or ''
    new_password = data.get('new_password') or ''

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码至少6位'})

    user = query_db('SELECT * FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not check_password_hash(user['password_hash'], old_password):
        return jsonify({'success': False, 'message': '原密码错误'})

    new_hash = generate_password_hash(new_password, method='pbkdf2:sha256:600000')
    execute_db('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, session['user_id']))

    return jsonify({'success': True, 'message': '密码修改成功'})


@auth_bp.route('/api/user/bind_machine', methods=['POST'])
@login_required
@csrf_protect
def api_bind_machine():
    """绑定机器码"""
    data = request.get_json() or {}
    machine_code = (data.get('machine_code') or '').strip()

    if not machine_code:
        return jsonify({'success': False, 'message': '机器码不能为空'})

    user = query_db('SELECT * FROM users WHERE id = ?', (session['user_id'],), one=True)
    if user['machine_code_bound'] and user['machine_code']:
        return jsonify({'success': False, 'message': '已绑定机器码，无法更改'})

    execute_db(
        'UPDATE users SET machine_code = ?, machine_code_bound = 1 WHERE id = ?',
        (machine_code, session['user_id'])
    )
    return jsonify({'success': True, 'message': '机器码绑定成功'})