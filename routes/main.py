# -*- coding: utf-8 -*-
# 软件库系统 - 主要页面路由

from flask import Blueprint, render_template, request, session, jsonify, redirect
from models import query_db, execute_db
from config import ITEMS_PER_PAGE

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """首页"""
    # 获取推荐软件
    featured = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.is_active = 1 AND s.is_featured = 1 '
        'ORDER BY s.sort_order, s.download_count DESC LIMIT 10'
    )

    # 获取最新软件
    latest = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.is_active = 1 '
        'ORDER BY s.created_at DESC LIMIT 12'
    )

    # 获取热门软件
    popular = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.is_active = 1 '
        'ORDER BY s.download_count DESC LIMIT 12'
    )

    # 获取各分类软件数量
    category_stats = query_db(
        'SELECT c.*, COUNT(s.id) as software_count FROM categories c '
        'LEFT JOIN software s ON s.category_id = c.id AND s.is_active = 1 '
        'WHERE c.is_active = 1 '
        'GROUP BY c.id ORDER BY c.sort_order'
    )

    # 公告
    announcements = query_db(
        'SELECT * FROM announcements WHERE is_active = 1 '
        'ORDER BY is_pinned DESC, priority DESC, created_at DESC LIMIT 5'
    )

    # 广告
    ads = query_db(
        "SELECT * FROM ad_slots WHERE is_active = 1 AND position = 'home_banner' "
        "ORDER BY sort_order LIMIT 5"
    )

    return render_template('index.html',
                           featured=featured,
                           latest=latest,
                           popular=popular,
                           category_stats=category_stats,
                           announcements=announcements,
                           ads=ads)


@main_bp.route('/category/<int:category_id>')
def category_view(category_id):
    """分类页面"""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    category = query_db('SELECT * FROM categories WHERE id = ? AND is_active = 1', (category_id,), one=True)
    if not category:
        return render_template('404.html'), 404

    software_list = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.category_id = ? AND s.is_active = 1 '
        'ORDER BY s.sort_order, s.download_count DESC LIMIT ? OFFSET ?',
        (category_id, ITEMS_PER_PAGE, offset)
    )

    total = query_db(
        'SELECT COUNT(*) as cnt FROM software WHERE category_id = ? AND is_active = 1',
        (category_id,), one=True
    )
    total_pages = (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0

    return render_template('category.html',
                           category=category,
                           software_list=software_list,
                           page=page,
                           total_pages=total_pages,
                           total=total['cnt'] if total else 0)


@main_bp.route('/free')
def free_zone():
    """免费专区 - 无需登录即可访问"""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    software_list = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.is_free = 1 AND s.is_active = 1 '
        'ORDER BY s.download_count DESC LIMIT ? OFFSET ?',
        (ITEMS_PER_PAGE, offset)
    )

    total = query_db(
        'SELECT COUNT(*) as cnt FROM software WHERE is_free = 1 AND is_active = 1',
        one=True
    )
    total_pages = (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0

    return render_template('free_zone.html',
                           software_list=software_list,
                           page=page,
                           total_pages=total_pages,
                           total=total['cnt'] if total else 0)


@main_bp.route('/software/<int:software_id>')
def software_detail(software_id):
    """软件详情页"""
    software = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.id = ? AND s.is_active = 1',
        (software_id,), one=True
    )
    if not software:
        return render_template('404.html'), 404

    # 非免费软件需要登录才能查看详情
    if not software['is_free'] and 'user_id' not in session:
        return redirect(url_for('auth.login_page', next=request.path))

    # 增加浏览次数
    execute_db('UPDATE software SET view_count = view_count + 1 WHERE id = ?', (software_id,))

    # 相关软件
    related = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.category_id = ? AND s.id != ? AND s.is_active = 1 '
        'ORDER BY s.download_count DESC LIMIT 6',
        (software['category_id'], software_id)
    )

    return render_template('software_detail.html', software=software, related=related)


@main_bp.route('/search')
def search():
    """搜索页面"""
    query = request.args.get('q', '').strip()
    category_id = request.args.get('category_id', 0, type=int)
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    if not query:
        return render_template('search.html', results=[], query='', page=1, total_pages=0, total=0)

    where_clause = "WHERE s.is_active = 1 AND (s.name LIKE ? OR s.description LIKE ? OR s.tags LIKE ?)"
    params = [f'%{query}%', f'%{query}%', f'%{query}%']

    if category_id > 0:
        where_clause += " AND s.category_id = ?"
        params.append(category_id)

    results = query_db(
        f'SELECT s.*, c.name as category_name FROM software s '
        f'LEFT JOIN categories c ON s.category_id = c.id '
        f'{where_clause} '
        f'ORDER BY s.download_count DESC LIMIT ? OFFSET ?',
        params + [ITEMS_PER_PAGE, offset]
    )

    total = query_db(
        f'SELECT COUNT(*) as cnt FROM software s {where_clause}',
        params, one=True
    )
    total_count = total['cnt'] if total else 0
    total_pages = (total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    return render_template('search.html',
                           results=results,
                           query=query,
                           category_id=category_id,
                           page=page,
                           total_pages=total_pages,
                           total=total_count)


@main_bp.route('/announcements')
def announcement_list():
    """公告列表页"""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    announcements = query_db(
        'SELECT * FROM announcements WHERE is_active = 1 '
        'ORDER BY is_pinned DESC, priority DESC, created_at DESC LIMIT ? OFFSET ?',
        (ITEMS_PER_PAGE, offset)
    )

    total = query_db('SELECT COUNT(*) as cnt FROM announcements WHERE is_active = 1', one=True)
    total_pages = (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0

    return render_template('announcements.html',
                           announcements=announcements,
                           page=page,
                           total_pages=total_pages)


@main_bp.route('/announcement/<int:announcement_id>')
def announcement_detail(announcement_id):
    """公告详情"""
    announcement = query_db(
        'SELECT * FROM announcements WHERE id = ? AND is_active = 1',
        (announcement_id,), one=True
    )
    if not announcement:
        return render_template('404.html'), 404
    return render_template('announcement_detail.html', announcement=announcement)


@main_bp.route('/card_redeem')
def card_redeem_page():
    """卡密兑换页面"""
    return render_template('card_redeem.html')


@main_bp.route('/feedback')
def feedback_page():
    """反馈页面"""
    return render_template('feedback.html')


@main_bp.route('/user_center')
def user_center():
    """用户中心"""
    if 'user_id' not in session:
        return render_template('login.html')
    return render_template('user_center.html')