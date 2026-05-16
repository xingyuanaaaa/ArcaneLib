# -*- coding: utf-8 -*-
# 软件库系统 - 后台管理路由

import os
import uuid
import hashlib
from flask import Blueprint, render_template, request, session, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from models import query_db, execute_db
from utils.decorators import admin_required, csrf_protect
from utils.crypto import generate_card_key, verify_card_key_integrity
from config import (
    SOFTWARE_UPLOAD_FOLDER, IMAGE_UPLOAD_FOLDER,
    ALLOWED_SOFTWARE_EXTENSIONS, ALLOWED_IMAGE_EXTENSIONS,
    ITEMS_PER_PAGE
)

admin_bp = Blueprint('admin', __name__)


def _allowed_file(filename, allowed_set):
    """检查文件扩展名"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def _save_upload(file, folder, allowed_set):
    """保存上传文件"""
    if file and _allowed_file(file.filename, allowed_set):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(folder, filename)
        file.save(filepath)
        return filepath, filename
    return None, None


@admin_bp.route('/')
@admin_required
def dashboard():
    """管理后台首页"""
    # 统计数据
    stats = {
        'software_count': query_db('SELECT COUNT(*) as cnt FROM software', one=True)['cnt'],
        'user_count': query_db('SELECT COUNT(*) as cnt FROM users', one=True)['cnt'],
        'normal_user_count': query_db("SELECT COUNT(*) as cnt FROM users WHERE is_banned=0 AND is_active=1", one=True)['cnt'],
        'vip_user_count': query_db("SELECT COUNT(*) as cnt FROM users WHERE vip_level>0", one=True)['cnt'],
        'card_count': query_db("SELECT COUNT(*) as cnt FROM card_keys WHERE status='unused'", one=True)['cnt'],
        'download_total': query_db('SELECT COALESCE(SUM(download_count),0) as cnt FROM software', one=True)['cnt'],
        'today_downloads': query_db(
            "SELECT COUNT(*) as cnt FROM download_logs WHERE date(downloaded_at) = date('now', 'localtime')",
            one=True
        )['cnt'],
        'feedback_pending': query_db("SELECT COUNT(*) as cnt FROM feedback WHERE status='pending'", one=True)['cnt'],
    }
    # 最近下载
    recent_downloads = query_db(
        'SELECT dl.*, u.username FROM download_logs dl '
        'LEFT JOIN users u ON dl.user_id = u.id '
        'ORDER BY dl.downloaded_at DESC LIMIT 20'
    )
    return render_template('admin/dashboard.html', stats=stats, recent_downloads=recent_downloads)


# ==================== 软件管理 ====================

@admin_bp.route('/software')
@admin_required
def software_manage():
    """软件管理页面"""
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category_id', 0, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    where = ""
    params = []
    if category_id > 0:
        where = "WHERE s.category_id = ?"
        params.append(category_id)

    software_list = query_db(
        f'SELECT s.*, c.name as category_name FROM software s '
        f'LEFT JOIN categories c ON s.category_id = c.id {where} '
        f'ORDER BY s.created_at DESC LIMIT ? OFFSET ?',
        params + [ITEMS_PER_PAGE, offset]
    )

    total = query_db(f'SELECT COUNT(*) as cnt FROM software s {where}', params, one=True)
    total_pages = (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0

    categories = query_db('SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order')
    return render_template('admin/software_manage.html',
                           software_list=software_list,
                           categories=categories,
                           page=page,
                           total_pages=total_pages,
                           category_id=category_id)


@admin_bp.route('/api/software/add', methods=['POST'])
@admin_required
@csrf_protect
def api_software_add():
    """添加软件"""
    name = request.form.get('name', '').strip()
    version = request.form.get('version', '').strip()
    category_id = request.form.get('category_id', 0, type=int)
    description = request.form.get('description', '').strip()
    long_description = request.form.get('long_description', '').strip()
    platform = request.form.get('platform', 'Windows').strip()
    tags = request.form.get('tags', '').strip()
    is_free = request.form.get('is_free', 0, type=int)
    require_vip = request.form.get('require_vip', 0, type=int)
    require_points = request.form.get('require_points', 0, type=int)
    is_featured = request.form.get('is_featured', 0, type=int)

    if not name:
        return jsonify({'success': False, 'message': '请输入软件名称'})

    # 处理封面图片
    cover_image = None
    if 'cover_image' in request.files:
        file = request.files['cover_image']
        _, cover_image = _save_upload(file, IMAGE_UPLOAD_FOLDER, ALLOWED_IMAGE_EXTENSIONS)

    # 处理软件文件
    file_path = None
    file_size = 0
    file_hash = None
    if 'software_file' in request.files:
        file = request.files['software_file']
        full_path, filename = _save_upload(file, SOFTWARE_UPLOAD_FOLDER, ALLOWED_SOFTWARE_EXTENSIONS)
        if full_path:
            file_path = full_path
            file_size = os.path.getsize(full_path)
            with open(full_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

    software_id = execute_db(
        'INSERT INTO software (name, version, category_id, description, long_description, '
        'cover_image, file_path, file_size, file_hash, platform, tags, is_free, require_vip, '
        'require_points, is_featured) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (name, version, category_id, description, long_description, cover_image,
         file_path, file_size, file_hash, platform, tags, is_free, require_vip,
         require_points, is_featured)
    )

    return jsonify({'success': True, 'message': '软件添加成功', 'data': {'id': software_id}})


@admin_bp.route('/api/software/edit/<int:software_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_software_edit(software_id):
    """编辑软件"""
    software = query_db('SELECT * FROM software WHERE id = ?', (software_id,), one=True)
    if not software:
        return jsonify({'success': False, 'message': '软件不存在'}), 404

    name = request.form.get('name', '').strip()
    version = request.form.get('version', '').strip()
    category_id = request.form.get('category_id', 0, type=int)
    description = request.form.get('description', '').strip()
    long_description = request.form.get('long_description', '').strip()
    platform = request.form.get('platform', 'Windows').strip()
    tags = request.form.get('tags', '').strip()
    is_free = request.form.get('is_free', 0, type=int)
    require_vip = request.form.get('require_vip', 0, type=int)
    require_points = request.form.get('require_points', 0, type=int)
    is_featured = request.form.get('is_featured', 0, type=int)
    is_active = request.form.get('is_active', 1, type=int)

    if not name:
        return jsonify({'success': False, 'message': '请输入软件名称'})

    # 处理封面图片
    cover_image = software['cover_image']
    if 'cover_image' in request.files and request.files['cover_image'].filename:
        file = request.files['cover_image']
        _, cover_image = _save_upload(file, IMAGE_UPLOAD_FOLDER, ALLOWED_IMAGE_EXTENSIONS)

    # 处理软件文件
    file_path = software['file_path']
    file_size = software['file_size']
    file_hash = software['file_hash']
    if 'software_file' in request.files and request.files['software_file'].filename:
        file = request.files['software_file']
        full_path, filename = _save_upload(file, SOFTWARE_UPLOAD_FOLDER, ALLOWED_SOFTWARE_EXTENSIONS)
        if full_path:
            # 删除旧文件
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            file_path = full_path
            file_size = os.path.getsize(full_path)
            with open(full_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

    execute_db(
        'UPDATE software SET name=?, version=?, category_id=?, description=?, long_description=?, '
        'cover_image=?, file_path=?, file_size=?, file_hash=?, platform=?, tags=?, is_free=?, '
        'require_vip=?, require_points=?, is_featured=?, is_active=?, '
        "updated_at=datetime('now', 'localtime') WHERE id=?",
        (name, version, category_id, description, long_description, cover_image,
         file_path, file_size, file_hash, platform, tags, is_free, require_vip,
         require_points, is_featured, is_active, software_id)
    )

    return jsonify({'success': True, 'message': '软件更新成功'})


@admin_bp.route('/api/software/delete/<int:software_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_software_delete(software_id):
    """删除软件"""
    software = query_db('SELECT * FROM software WHERE id = ?', (software_id,), one=True)
    if not software:
        return jsonify({'success': False, 'message': '软件不存在'}), 404

    # 删除文件
    if software['file_path'] and os.path.exists(software['file_path']):
        try:
            os.remove(software['file_path'])
        except Exception:
            pass

    execute_db('DELETE FROM software WHERE id = ?', (software_id,))
    return jsonify({'success': True, 'message': '软件已删除'})


# ==================== 分类管理 ====================

@admin_bp.route('/api/category/add', methods=['POST'])
@admin_required
@csrf_protect
def api_category_add():
    """添加分类"""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    sort_order = data.get('sort_order', 0)

    if not name:
        return jsonify({'success': False, 'message': '请输入分类名称'})

    existing = query_db('SELECT id FROM categories WHERE name = ?', (name,), one=True)
    if existing:
        return jsonify({'success': False, 'message': '分类名称已存在'})

    execute_db(
        'INSERT INTO categories (name, description, sort_order) VALUES (?, ?, ?)',
        (name, description, sort_order)
    )
    return jsonify({'success': True, 'message': '分类添加成功'})


@admin_bp.route('/api/category/edit/<int:category_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_category_edit(category_id):
    """编辑分类"""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    sort_order = data.get('sort_order', 0)
    is_active = data.get('is_active', 1)

    execute_db(
        'UPDATE categories SET name=?, description=?, sort_order=?, is_active=? WHERE id=?',
        (name, description, sort_order, is_active, category_id)
    )
    return jsonify({'success': True, 'message': '分类更新成功'})


@admin_bp.route('/api/category/delete/<int:category_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_category_delete(category_id):
    """删除分类"""
    execute_db('UPDATE software SET category_id = NULL WHERE category_id = ?', (category_id,))
    execute_db('DELETE FROM categories WHERE id = ?', (category_id,))
    return jsonify({'success': True, 'message': '分类已删除'})


# ==================== 邀请码管理 ====================

@admin_bp.route('/cards')
@admin_required
def card_manage():
    """邀请码管理页面"""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    cards = query_db(
        'SELECT ck.*, u.username as used_username FROM card_keys ck '
        'LEFT JOIN users u ON ck.used_by = u.id '
        'ORDER BY ck.created_at DESC LIMIT ? OFFSET ?',
        (ITEMS_PER_PAGE, offset)
    )

    total = query_db('SELECT COUNT(*) as cnt FROM card_keys', one=True)
    total_pages = (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0

    register_unused = query_db("SELECT COUNT(*) as cnt FROM card_keys WHERE status='unused' AND card_type='register'", one=True)['cnt']
    vip_unused = query_db("SELECT COUNT(*) as cnt FROM card_keys WHERE status='unused' AND card_type='vip'", one=True)['cnt']
    points_unused = query_db("SELECT COUNT(*) as cnt FROM card_keys WHERE status='unused' AND card_type='points'", one=True)['cnt']
    used_count = query_db("SELECT COUNT(*) as cnt FROM card_keys WHERE status='used'", one=True)['cnt']

    return render_template('admin/card_manage.html',
                           cards=cards,
                           page=page,
                           total_pages=total_pages,
                           register_unused_count=register_unused,
                           vip_unused_count=vip_unused,
                           points_unused_count=points_unused,
                           used_count=used_count)


@admin_bp.route('/api/card/generate', methods=['POST'])
@admin_required
@csrf_protect
def api_card_generate():
    """批量生成卡密"""
    data = request.get_json() or {}
    count = data.get('count', 1)
    card_type = data.get('card_type', 'vip')
    vip_days = data.get('vip_days', 30)
    points = data.get('points', 0)
    notes = data.get('notes', '').strip()
    batch_id = f"BATCH_{uuid.uuid4().hex[:8].upper()}"

    if count < 1 or count > 500:
        return jsonify({'success': False, 'message': '生成数量需在1-500之间'})

    generated = []
    for _ in range(count):
        card_key = generate_card_key()
        execute_db(
            'INSERT INTO card_keys (card_key, card_type, vip_days, points, generated_by, batch_id, notes) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (card_key, card_type, vip_days, points, session['user_id'], batch_id, notes)
        )
        generated.append(card_key)

    return jsonify({
        'success': True,
        'message': f'成功生成{count}张卡密',
        'data': {
            'batch_id': batch_id,
            'cards': generated
        }
    })


@admin_bp.route('/api/card/disable/<int:card_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_card_disable(card_id):
    """禁用卡密"""
    execute_db("UPDATE card_keys SET status='disabled' WHERE id=? AND status='unused'", (card_id,))
    return jsonify({'success': True, 'message': '卡密已禁用'})


@admin_bp.route('/api/card/delete/<int:card_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_card_delete(card_id):
    """删除卡密"""
    execute_db("DELETE FROM card_keys WHERE id=? AND status='unused'", (card_id,))
    return jsonify({'success': True, 'message': '卡密已删除'})


# ==================== 用户管理 ====================

@admin_bp.route('/users')
@admin_required
def user_manage():
    """用户管理页面"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    offset = (page - 1) * ITEMS_PER_PAGE

    where = ""
    params = []
    if search:
        where = "WHERE username LIKE ? OR email LIKE ?"
        params = [f'%{search}%', f'%{search}%']

    users = query_db(
        f'SELECT * FROM users {where} ORDER BY created_at DESC LIMIT ? OFFSET ?',
        params + [ITEMS_PER_PAGE, offset]
    )

    total = query_db(f'SELECT COUNT(*) as cnt FROM users {where}', params, one=True)
    total_pages = (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0

    return render_template('admin/user_manage.html',
                           users=users,
                           page=page,
                           total_pages=total_pages,
                           search=search)


@admin_bp.route('/api/user/edit/<int:user_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_user_edit(user_id):
    """编辑用户"""
    data = request.get_json() or {}
    vip_level = data.get('vip_level', 0, type=int)
    points = data.get('points', 0, type=int)
    is_active = data.get('is_active', 1, type=int)
    is_banned = data.get('is_banned', 0, type=int)
    ban_reason = (data.get('ban_reason') or '').strip()

    execute_db(
        'UPDATE users SET vip_level=?, points=?, is_active=?, is_banned=?, ban_reason=? WHERE id=?',
        (vip_level, points, is_active, is_banned, ban_reason, user_id)
    )
    return jsonify({'success': True, 'message': '用户信息已更新'})


# ==================== 公告管理 ====================

@admin_bp.route('/announcements')
@admin_required
def announcement_manage():
    """公告管理页面"""
    announcements = query_db(
        'SELECT * FROM announcements ORDER BY is_pinned DESC, priority DESC, created_at DESC'
    )
    return render_template('admin/announcement_manage.html', announcements=announcements)


@admin_bp.route('/api/announcement/add', methods=['POST'])
@admin_required
@csrf_protect
def api_announcement_add():
    """添加公告"""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    ann_type = data.get('type', 'info')
    priority = data.get('priority', 0, type=int)
    is_pinned = data.get('is_pinned', 0, type=int)

    if not title or not content:
        return jsonify({'success': False, 'message': '请填写标题和内容'})

    execute_db(
        'INSERT INTO announcements (title, content, type, priority, is_pinned, created_by) VALUES (?, ?, ?, ?, ?, ?)',
        (title, content, ann_type, priority, is_pinned, session['user_id'])
    )
    return jsonify({'success': True, 'message': '公告发布成功'})


@admin_bp.route('/api/announcement/edit/<int:ann_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_announcement_edit(ann_id):
    """编辑公告"""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    ann_type = data.get('type', 'info')
    priority = data.get('priority', 0, type=int)
    is_pinned = data.get('is_pinned', 0, type=int)
    is_active = data.get('is_active', 1, type=int)

    execute_db(
        'UPDATE announcements SET title=?, content=?, type=?, priority=?, is_pinned=?, is_active=?, '
        "updated_at=datetime('now', 'localtime') WHERE id=?",
        (title, content, ann_type, priority, is_pinned, is_active, ann_id)
    )
    return jsonify({'success': True, 'message': '公告已更新'})


@admin_bp.route('/api/announcement/delete/<int:ann_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_announcement_delete(ann_id):
    """删除公告"""
    execute_db('DELETE FROM announcements WHERE id = ?', (ann_id,))
    return jsonify({'success': True, 'message': '公告已删除'})


# ==================== 反馈管理 ====================

@admin_bp.route('/feedback')
@admin_required
def feedback_manage():
    """反馈管理页面"""
    status_filter = request.args.get('status', '')
    where = ""
    params = []
    if status_filter:
        where = "WHERE status = ?"
        params = [status_filter]

    feedbacks = query_db(
        f'SELECT * FROM feedback {where} ORDER BY created_at DESC LIMIT 100',
        params
    )
    return render_template('admin/feedback_manage.html', feedbacks=feedbacks, status_filter=status_filter)


@admin_bp.route('/api/feedback/reply/<int:fb_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_feedback_reply(fb_id):
    """回复反馈"""
    data = request.get_json() or {}
    reply = (data.get('reply') or '').strip()
    status = data.get('status', 'resolved')

    if not reply:
        return jsonify({'success': False, 'message': '请输入回复内容'})

    execute_db(
        'UPDATE feedback SET admin_reply=?, status=?, replied_by=?, '
        "replied_at=datetime('now', 'localtime') WHERE id=?",
        (reply, status, session['user_id'], fb_id)
    )
    return jsonify({'success': True, 'message': '回复成功'})


# ==================== 广告管理 ====================

@admin_bp.route('/ads')
@admin_required
def ad_manage():
    """广告管理页面"""
    ads = query_db('SELECT * FROM ad_slots ORDER BY position, sort_order')
    return render_template('admin/ad_manage.html', ads=ads)


@admin_bp.route('/api/ad/add', methods=['POST'])
@admin_required
@csrf_protect
def api_ad_add():
    """添加广告"""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    position = (data.get('position') or '').strip()
    ad_type = data.get('ad_type', 'image')
    image_url = (data.get('image_url') or '').strip()
    link_url = (data.get('link_url') or '').strip()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    sort_order = data.get('sort_order', 0)

    if not name:
        return jsonify({'success': False, 'message': '请输入广告名称'})

    execute_db(
        'INSERT INTO ad_slots (name, position, ad_type, image_url, link_url, title, description, sort_order) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (name, position, ad_type, image_url, link_url, title, description, sort_order)
    )
    return jsonify({'success': True, 'message': '广告添加成功'})


@admin_bp.route('/api/ad/edit/<int:ad_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_ad_edit(ad_id):
    """编辑广告"""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    position = (data.get('position') or '').strip()
    ad_type = data.get('ad_type', 'image')
    image_url = (data.get('image_url') or '').strip()
    link_url = (data.get('link_url') or '').strip()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    is_active = data.get('is_active', 1)
    sort_order = data.get('sort_order', 0)

    execute_db(
        'UPDATE ad_slots SET name=?, position=?, ad_type=?, image_url=?, link_url=?, '
        'title=?, description=?, is_active=?, sort_order=? WHERE id=?',
        (name, position, ad_type, image_url, link_url, title, description, is_active, sort_order, ad_id)
    )
    return jsonify({'success': True, 'message': '广告已更新'})


@admin_bp.route('/api/ad/detail/<int:ad_id>')
@admin_required
def api_ad_detail(ad_id):
    """获取广告详情"""
    ad = query_db('SELECT * FROM ad_slots WHERE id = ?', (ad_id,), one=True)
    if not ad:
        return jsonify({'success': False, 'message': '广告不存在'}), 404
    return jsonify({'success': True, 'data': dict(ad)})


@admin_bp.route('/api/ad/delete/<int:ad_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_ad_delete(ad_id):
    """删除广告"""
    execute_db('DELETE FROM ad_slots WHERE id = ?', (ad_id,))
    return jsonify({'success': True, 'message': '广告已删除'})


# ==================== 分类管理页面 ====================

@admin_bp.route('/categories')
@admin_required
def category_manage():
    """分类管理页面"""
    categories = query_db('SELECT c.*, (SELECT COUNT(*) FROM software WHERE category_id = c.id) as software_count FROM categories c ORDER BY c.sort_order')
    return render_template('admin/category_manage.html', categories=categories)


# ==================== 系统配置 ====================

@admin_bp.route('/settings')
@admin_required
def settings():
    """系统设置页面"""
    configs = query_db('SELECT * FROM system_config ORDER BY id')
    return render_template('admin/settings.html', configs=configs)


@admin_bp.route('/api/config/update', methods=['POST'])
@admin_required
@csrf_protect
def api_config_update():
    """更新系统配置"""
    data = request.get_json() or {}
    configs = data.get('configs', {})

    for key, value in configs.items():
        execute_db(
            "INSERT OR REPLACE INTO system_config (config_key, config_value, updated_at) VALUES (?, ?, datetime('now', 'localtime'))",
            (key, str(value))
        )

    return jsonify({'success': True, 'message': '配置已更新'})


# ==================== 下载统计 ====================

@admin_bp.route('/stats/downloads')
@admin_required
def download_stats():
    """下载统计页面"""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    logs = query_db(
        'SELECT dl.*, u.username FROM download_logs dl '
        'LEFT JOIN users u ON dl.user_id = u.id '
        'ORDER BY dl.downloaded_at DESC LIMIT ? OFFSET ?',
        (ITEMS_PER_PAGE, offset)
    )

    total = query_db('SELECT COUNT(*) as cnt FROM download_logs', one=True)
    total_pages = (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0

    # 热门软件排行
    top_software = query_db(
        'SELECT name, download_count FROM software WHERE is_active = 1 '
        'ORDER BY download_count DESC LIMIT 10'
    )

    return render_template('admin/download_stats.html',
                           logs=logs,
                           page=page,
                           total_pages=total_pages,
                           top_software=top_software)


# ==================== 版本管理 ====================

@admin_bp.route('/versions')
@admin_required
def version_management():
    """版本管理页面"""
    versions = query_db(
        'SELECT * FROM app_versions ORDER BY id DESC'
    )
    active_count = query_db(
        'SELECT COUNT(*) as cnt FROM app_versions WHERE is_active = 1', one=True
    )['cnt']
    disabled_count = query_db(
        'SELECT COUNT(*) as cnt FROM app_versions WHERE is_active = 0', one=True
    )['cnt']
    total_count = query_db(
        'SELECT COUNT(*) as cnt FROM app_versions', one=True
    )['cnt']
    return render_template('admin/versions.html', versions=versions,
                           active_count=active_count,
                           disabled_count=disabled_count,
                           total_count=total_count)


@admin_bp.route('/api/version/add', methods=['POST'])
@admin_required
@csrf_protect
def api_add_version():
    """添加新版本"""
    version_code = (request.form.get('version_code') or '').strip()
    version_name = (request.form.get('version_name') or '').strip()
    if not version_code:
        flash('请输入版本号', 'danger')
        return redirect(url_for('admin.version_management'))

    existing = query_db(
        'SELECT id FROM app_versions WHERE version_code = ?',
        (version_code,), one=True
    )
    if existing:
        flash('版本号已存在', 'danger')
        return redirect(url_for('admin.version_management'))

    execute_db(
        'INSERT INTO app_versions (version_code, version_name, is_active) VALUES (?, ?, ?)',
        (version_code, version_name, 1)
    )
    flash(f'版本 {version_code} 添加成功', 'success')
    return redirect(url_for('admin.version_management'))


@admin_bp.route('/api/version/toggle/<int:version_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_toggle_version(version_id):
    """切换版本有效/作废状态"""
    version = query_db('SELECT * FROM app_versions WHERE id = ?', (version_id,), one=True)
    if not version:
        flash('版本不存在', 'danger')
        return redirect(url_for('admin.version_management'))

    new_status = 0 if version['is_active'] else 1
    execute_db('UPDATE app_versions SET is_active = ? WHERE id = ?', (new_status, version_id))
    status_text = '已作废' if new_status == 0 else '已恢复'
    flash(f'版本 {version["version_code"]} {status_text}', 'success')
    return redirect(url_for('admin.version_management'))


@admin_bp.route('/api/version/delete/<int:version_id>', methods=['POST'])
@admin_required
@csrf_protect
def api_delete_version(version_id):
    """删除版本记录"""
    version = query_db('SELECT * FROM app_versions WHERE id = ?', (version_id,), one=True)
    if not version:
        flash('版本不存在', 'danger')
        return redirect(url_for('admin.version_management'))

    execute_db('DELETE FROM app_versions WHERE id = ?', (version_id,))
    flash(f'版本 {version["version_code"]} 已删除', 'success')
    return redirect(url_for('admin.version_management'))