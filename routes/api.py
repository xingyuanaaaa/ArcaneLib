# -*- coding: utf-8 -*-
# 软件库系统 - REST API路由（供手机端和电脑端调用）

from flask import Blueprint, request, jsonify, session
from models import query_db, execute_db, get_db, get_config
from utils.decorators import login_required, rate_limit, csrf_protect, admin_required
from utils.crypto import generate_card_key, verify_card_key_integrity, sha256_hash, aes_encrypt, aes_decrypt
from utils.machine_code import get_machine_code, verify_machine_code
from utils.api_security import verify_app_token, verify_request_signature, check_emulator
from config import ITEMS_PER_PAGE
import time
import hashlib

api_bp = Blueprint('api', __name__)


# ==================== 软件相关API ====================

@api_bp.route('/software/list')
def api_software_list():
    """获取软件列表"""
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category_id', 0, type=int)
    sort = request.args.get('sort', 'newest')
    offset = (page - 1) * ITEMS_PER_PAGE

    where = "WHERE s.is_active = 1"
    params = []

    if category_id > 0:
        where += " AND s.category_id = ?"
        params.append(category_id)

    order_map = {
        'newest': 's.created_at DESC',
        'popular': 's.download_count DESC',
        'rating': 's.rating DESC',
        'views': 's.view_count DESC',
    }
    order = order_map.get(sort, 's.created_at DESC')

    total = query_db(f'SELECT COUNT(*) as cnt FROM software s {where}', params, one=True)
    software_list = query_db(
        f'SELECT s.id, s.name, s.version, s.category_id, c.name as category_name, '
        f's.description, s.cover_image, s.file_size, s.platform, s.is_free, '
        f's.require_vip, s.download_count, s.view_count, s.rating, s.created_at '
        f'FROM software s LEFT JOIN categories c ON s.category_id = c.id '
        f'{where} ORDER BY {order} LIMIT ? OFFSET ?',
        params + [ITEMS_PER_PAGE, offset]
    )

    return jsonify({
        'success': True,
        'data': {
            'list': [dict(row) for row in software_list],
            'total': total['cnt'] if total else 0,
            'page': page,
            'total_pages': (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0
        }
    })


@api_bp.route('/software/detail/<int:software_id>')
def api_software_detail(software_id):
    """获取软件详情"""
    software = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.id = ? AND s.is_active = 1',
        (software_id,), one=True
    )
    if not software:
        return jsonify({'success': False, 'message': '软件不存在'}), 404

    execute_db('UPDATE software SET view_count = view_count + 1 WHERE id = ?', (software_id,))

    return jsonify({
        'success': True,
        'data': dict(software)
    })


@api_bp.route('/software/search')
def api_software_search():
    """搜索软件"""
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category_id', 0, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    if not q:
        return jsonify({'success': False, 'message': '请输入搜索关键词'})

    where = "WHERE s.is_active = 1 AND (s.name LIKE ? OR s.description LIKE ? OR s.tags LIKE ?)"
    params = [f'%{q}%', f'%{q}%', f'%{q}%']

    if category_id > 0:
        where += " AND s.category_id = ?"
        params.append(category_id)

    total = query_db(f'SELECT COUNT(*) as cnt FROM software s {where}', params, one=True)
    results = query_db(
        f'SELECT s.id, s.name, s.version, s.category_id, c.name as category_name, '
        f's.description, s.cover_image, s.file_size, s.platform, s.download_count, s.rating '
        f'FROM software s LEFT JOIN categories c ON s.category_id = c.id '
        f'{where} ORDER BY s.download_count DESC LIMIT ? OFFSET ?',
        params + [ITEMS_PER_PAGE, offset]
    )

    return jsonify({
        'success': True,
        'data': {
            'list': [dict(row) for row in results],
            'total': total['cnt'] if total else 0,
            'page': page,
            'total_pages': (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0
        }
    })


@api_bp.route('/software/download/<int:software_id>', methods=['POST'])
@login_required
@rate_limit(max_requests=30, window=60)
@csrf_protect
def api_software_download(software_id):
    """下载软件 - 需要登录且有权限"""
    software = query_db('SELECT * FROM software WHERE id = ? AND is_active = 1', (software_id,), one=True)
    if not software:
        return jsonify({'success': False, 'message': '软件不存在'}), 404

    user = query_db('SELECT * FROM users WHERE id = ?', (session['user_id'],), one=True)

    data = request.get_json(silent=True) or {}
    app_signature = request.headers.get('X-App-Signature', '')
    app_token = request.headers.get('X-App-Token', '')
    device_id = request.headers.get('X-Device-Id', '')
    user_agent = request.headers.get('User-Agent', '')

    if app_signature and data:
        sig_params = {k: str(v) for k, v in data.items() if k != 'signature'}
        if not verify_request_signature(sig_params, app_signature):
            return jsonify({'success': False, 'message': '请求签名验证失败'}), 403

    if app_token:
        if not verify_app_token(app_token, session['user_id'], device_id):
            return jsonify({'success': False, 'message': '令牌无效或已过期'}), 403

    if device_id or user_agent:
        emu_indicators = check_emulator(device_id, user_agent)
        if emu_indicators:
            execute_db(
                "INSERT INTO security_logs (event_type, ip_address, details, severity) VALUES (?, ?, ?, ?)",
                ('emulator_detected', request.remote_addr, f'模拟器环境: {emu_indicators}', 'warning')
            )

    # 非免费软件：校验是否通过邀请码注册
    if not software['is_free']:
        invite_check = query_db(
            "SELECT * FROM card_keys WHERE used_by = ? AND card_type = 'register' AND status = 'used'",
            (session['user_id'],), one=True
        )
        if not invite_check:
            return jsonify({'success': False, 'message': '此资源需要购买邀请码才能下载，请先购买邀请码注册'}), 403

    # 检查VIP要求
    if software['require_vip']:
        if user['vip_level'] < 1:
            return jsonify({'success': False, 'message': '此软件需要VIP会员才能下载，请先兑换VIP卡密'}), 403
        if user['vip_expire_time']:
            from datetime import datetime
            expire = datetime.strptime(user['vip_expire_time'], '%Y-%m-%d %H:%M:%S')
            if expire < datetime.now():
                return jsonify({'success': False, 'message': '您的VIP已过期，请续费'}), 403

    # 检查机器码绑定（非免费软件需要校验机器码）
    if not software['is_free']:
        data = request.get_json(silent=True) or {}
        req_machine_code = (data.get('machine_code') or '').strip()
        if user['machine_code'] and req_machine_code != user['machine_code']:
            return jsonify({'success': False, 'message': '机器码不匹配，请在绑定的设备上下载'}), 403

    # 检查每日最大下载次数
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    today_downloads = query_db(
        "SELECT COUNT(*) as cnt FROM download_logs WHERE user_id = ? AND date(downloaded_at) = ?",
        (session['user_id'], today), one=True
    )
    max_daily = int(get_config('max_downloads_per_day') or 50)
    if today_downloads and today_downloads['cnt'] >= max_daily:
        return jsonify({'success': False, 'message': f'今日下载次数已达上限({max_daily}次)'}), 429

    # 检查下载间隔
    last_download = query_db(
        'SELECT downloaded_at FROM download_logs WHERE user_id = ? ORDER BY downloaded_at DESC LIMIT 1',
        (session['user_id'],), one=True
    )
    if last_download:
        interval = int(get_config('download_interval') or 30)
        last_time = datetime.strptime(last_download['downloaded_at'], '%Y-%m-%d %H:%M:%S')
        elapsed = (datetime.now() - last_time).total_seconds()
        if elapsed < interval:
            remaining = interval - int(elapsed)
            return jsonify({'success': False, 'message': f'下载过于频繁，请{remaining}秒后再试'}), 429

    # 检查积分要求
    if software['require_points'] and software['require_points'] > 0:
        if user['points'] < software['require_points']:
            return jsonify({'success': False, 'message': f'需要{software["require_points"]}积分才能下载'}), 403

    # 生成加密下载链接（一次性token）
    download_token = aes_encrypt(f"{software_id}:{session['user_id']}:{int(time.time())}")

    # token生成成功后扣除积分
    if software['require_points'] and software['require_points'] > 0:
        execute_db('UPDATE users SET points = points - ? WHERE id = ?',
                   (software['require_points'], session['user_id']))

    # 记录下载
    execute_db('UPDATE software SET download_count = download_count + 1 WHERE id = ?', (software_id,))
    execute_db(
        'INSERT INTO download_logs (user_id, software_id, software_name, ip_address, machine_code) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], software_id, software['name'], request.remote_addr, user['machine_code'])
    )

    return jsonify({
        'success': True,
        'message': '获取下载链接成功',
        'data': {
            'download_url': f"/api/software/do_download/{download_token}",
            'file_name': software['name'],
            'file_size': software['file_size']
        }
    })


@api_bp.route('/software/do_download/<token>')
def api_do_download(token):
    """实际下载文件 - 验证token"""
    decrypted = aes_decrypt(token)
    if not decrypted:
        return jsonify({'success': False, 'message': '下载链接无效或已过期'}), 403

    try:
        software_id, user_id, ts = decrypted.split(':')
        if int(time.time()) - int(ts) > 300:  # 5分钟有效期
            return jsonify({'success': False, 'message': '下载链接已过期'}), 403
    except Exception:
        return jsonify({'success': False, 'message': '下载链接无效'}), 403

    software = query_db('SELECT * FROM software WHERE id = ?', (software_id,), one=True)
    if not software:
        return jsonify({'success': False, 'message': '软件不存在'}), 404

    from flask import send_from_directory
    import os
    file_path = software['file_path']
    if file_path and os.path.exists(file_path):
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        return send_from_directory(directory, filename, as_attachment=True,
                                   download_name=filename)
    return jsonify({'success': False, 'message': '文件不存在'}), 404


# ==================== 分类API ====================

@api_bp.route('/categories')
def api_categories():
    """获取所有分类"""
    categories = query_db(
        'SELECT c.*, COUNT(s.id) as software_count FROM categories c '
        'LEFT JOIN software s ON s.category_id = c.id AND s.is_active = 1 '
        'WHERE c.is_active = 1 GROUP BY c.id ORDER BY c.sort_order'
    )
    return jsonify({
        'success': True,
        'data': [dict(row) for row in categories]
    })


# ==================== 卡密API ====================

@api_bp.route('/card/redeem', methods=['POST'])
@login_required
@rate_limit(max_requests=5, window=300)
@csrf_protect
def api_card_redeem():
    """兑换卡密"""
    data = request.get_json() or {}
    card_key = (data.get('card_key') or '').strip().upper()
    machine_code = (data.get('machine_code') or '').strip()

    if not card_key:
        return jsonify({'success': False, 'message': '请输入卡密'})

    # 验证卡密完整性
    if not verify_card_key_integrity(card_key):
        return jsonify({'success': False, 'message': '卡密格式无效'})

    # 获取数据库连接，开启事务
    db = get_db()
    try:
        # 查找卡密
        clean_key = card_key.replace('-', '')
        card = db.execute(
            'SELECT * FROM card_keys WHERE REPLACE(card_key, "-", "") = ?',
            (clean_key,)
        ).fetchone()

        if not card:
            return jsonify({'success': False, 'message': '卡密不存在'})

        if card['status'] == 'used':
            return jsonify({'success': False, 'message': '该卡密已被使用'})

        if card['status'] == 'disabled':
            return jsonify({'success': False, 'message': '该卡密已被禁用'})

        # 执行兑换
        user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

        if card['card_type'] == 'vip':
            # VIP卡密
            from datetime import datetime, timedelta
            current_expire = user['vip_expire_time']
            if current_expire:
                expire_date = datetime.strptime(current_expire, '%Y-%m-%d %H:%M:%S')
            else:
                expire_date = datetime.now()
            if expire_date < datetime.now():
                expire_date = datetime.now()
            new_expire = expire_date + timedelta(days=card['vip_days'])
            new_expire_str = new_expire.strftime('%Y-%m-%d %H:%M:%S')

            db.execute(
                'UPDATE users SET vip_level = CASE WHEN vip_level < 1 THEN 1 ELSE vip_level END, vip_expire_time = ? WHERE id = ?',
                (new_expire_str, session['user_id'])
            )

        elif card['card_type'] == 'points':
            # 积分卡密
            db.execute(
                'UPDATE users SET points = points + ? WHERE id = ?',
                (card['points'], session['user_id'])
            )

        # 更新卡密状态
        db.execute(
            "UPDATE card_keys SET status = 'used', used_by = ?, used_at = datetime('now', 'localtime'), bound_machine_code = ? WHERE id = ?",
            (session['user_id'], machine_code, card['id'])
        )

        # 写入安全日志
        db.execute(
            "INSERT INTO security_logs (event_type, ip_address, details, severity) VALUES (?, ?, ?, ?)",
            ('card_redeem', request.remote_addr,
             f'用户ID:{session["user_id"]} 兑换了{card["card_type"]}卡密(ID:{card["id"]})',
             'info')
        )

        # 提交事务
        db.commit()

        return jsonify({
            'success': True,
            'message': f'兑换成功！' + (
                f'VIP时长增加{card["vip_days"]}天' if card['card_type'] == 'vip'
                else f'获得{card["points"]}积分'
            )
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': '兑换失败，系统错误，请重试'})
    finally:
        db.close()


@api_bp.route('/card/list', methods=['GET'])
@login_required
def api_card_list():
    """获取用户的卡密使用记录"""
    records = query_db(
        'SELECT * FROM card_keys WHERE used_by = ? ORDER BY used_at DESC LIMIT 20',
        (session['user_id'],)
    )
    return jsonify({
        'success': True,
        'data': [dict(row) for row in records]
    })


# ==================== 公告API ====================

@api_bp.route('/announcements')
def api_announcements():
    """获取公告列表"""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    announcements = query_db(
        'SELECT id, title, content, type, priority, is_pinned, created_at '
        'FROM announcements WHERE is_active = 1 '
        'ORDER BY is_pinned DESC, priority DESC, created_at DESC LIMIT ? OFFSET ?',
        (ITEMS_PER_PAGE, offset)
    )

    total = query_db('SELECT COUNT(*) as cnt FROM announcements WHERE is_active = 1', one=True)

    return jsonify({
        'success': True,
        'data': {
            'list': [dict(row) for row in announcements],
            'total': total['cnt'] if total else 0,
            'page': page,
            'total_pages': (total['cnt'] + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total else 0
        }
    })


# ==================== 反馈API ====================

@api_bp.route('/feedback/submit', methods=['POST'])
@login_required
@rate_limit(max_requests=3, window=300)
@csrf_protect
def api_feedback_submit():
    """提交反馈"""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    feedback_type = data.get('type', 'suggestion')

    if not title or not content:
        return jsonify({'success': False, 'message': '请填写标题和内容'})

    if len(content) < 5:
        return jsonify({'success': False, 'message': '内容至少5个字'})

    execute_db(
        'INSERT INTO feedback (user_id, username, title, content, type) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], session.get('username', ''), title, content, feedback_type)
    )

    return jsonify({'success': True, 'message': '反馈提交成功，感谢您的反馈！'})


@api_bp.route('/feedback/list', methods=['GET'])
@login_required
def api_feedback_list():
    """获取用户的反馈列表"""
    records = query_db(
        'SELECT * FROM feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT 20',
        (session['user_id'],)
    )
    return jsonify({
        'success': True,
        'data': [dict(row) for row in records]
    })


# ==================== 统计API ====================

@api_bp.route('/stats/overview')
def api_stats_overview():
    """获取站点统计概览"""
    software_count = query_db('SELECT COUNT(*) as cnt FROM software WHERE is_active = 1', one=True)
    user_count = query_db('SELECT COUNT(*) as cnt FROM users', one=True)
    download_count = query_db('SELECT SUM(download_count) as cnt FROM software', one=True)

    return jsonify({
        'success': True,
        'data': {
            'software_count': software_count['cnt'] if software_count else 0,
            'user_count': user_count['cnt'] if user_count else 0,
            'download_count': download_count['cnt'] if download_count and download_count['cnt'] else 0
        }
    })


# ==================== 广告API ====================

@api_bp.route('/ads/<position>')
def api_ads(position):
    """获取广告位内容"""
    ads = query_db(
        'SELECT * FROM ad_slots WHERE is_active = 1 AND position = ? ORDER BY sort_order',
        (position,)
    )
    return jsonify({
        'success': True,
        'data': [dict(row) for row in ads]
    })


@api_bp.route('/ads/click/<int:ad_id>', methods=['POST'])
def api_ad_click(ad_id):
    """广告点击统计"""
    execute_db('UPDATE ad_slots SET click_count = click_count + 1 WHERE id = ?', (ad_id,))
    return jsonify({'success': True})


# ==================== 签到API ====================

@api_bp.route('/checkin', methods=['POST'])
@login_required
def api_checkin():
    """每日签到"""
    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')

    # 检查今日是否已签到
    existing = query_db(
        'SELECT * FROM checkin_logs WHERE user_id = ? AND checkin_date = ?',
        (session['user_id'], today), one=True
    )
    if existing:
        return jsonify({'success': False, 'message': '今日已签到'})

    # 计算连续签到天数
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_log = query_db(
        'SELECT consecutive_days FROM checkin_logs WHERE user_id = ? AND checkin_date = ?',
        (session['user_id'], yesterday), one=True
    )
    consecutive = (yesterday_log['consecutive_days'] if yesterday_log else 0) + 1

    # 根据等级计算基础积分
    user = query_db('SELECT points, double_points_expire FROM users WHERE id = ?', (session['user_id'],), one=True)
    level_info = _calc_level(user['points'])
    base_points = 10 + (level_info['level'] - 1) * 2  # Lv.1=10, Lv.2=12, Lv.3=14...

    # 连续签到奖励
    bonus = 0
    if consecutive % 7 == 0:
        bonus = 50
    elif consecutive % 3 == 0:
        bonus = 15

    total_earned = base_points + bonus

    # 双倍积分检测
    is_double = False
    if user['double_points_expire']:
        try:
            expire = datetime.strptime(user['double_points_expire'], '%Y-%m-%d %H:%M:%S')
            if expire > datetime.now():
                total_earned *= 2
                is_double = True
        except:
            pass

    execute_db(
        'INSERT INTO checkin_logs (user_id, checkin_date, points_earned, consecutive_days) VALUES (?, ?, ?, ?)',
        (session['user_id'], today, total_earned, consecutive)
    )
    execute_db('UPDATE users SET points = points + ? WHERE id = ?', (total_earned, session['user_id']))

    # 获取用户最新信息
    user = query_db('SELECT points, vip_level, vip_expire_time FROM users WHERE id = ?', (session['user_id'],), one=True)
    level_info = _calc_level(user['points'])

    msg = f'签到成功！获得{total_earned}积分'
    if bonus:
        msg += f'（含连续{consecutive}天奖励{bonus}积分）'
    if is_double:
        msg += '（双倍积分卡生效中）'

    return jsonify({
        'success': True,
        'message': msg,
        'data': {
            'points_earned': total_earned,
            'consecutive_days': consecutive,
            'total_points': user['points'],
            'level': level_info['level'],
            'level_name': level_info['name'],
            'next_level_points': level_info['next']
        }
    })


@api_bp.route('/checkin/status', methods=['GET'])
@login_required
def api_checkin_status():
    """获取签到状态"""
    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')

    today_log = query_db(
        'SELECT * FROM checkin_logs WHERE user_id = ? AND checkin_date = ?',
        (session['user_id'], today), one=True
    )

    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_log = query_db(
        'SELECT consecutive_days FROM checkin_logs WHERE user_id = ? AND checkin_date = ?',
        (session['user_id'], yesterday), one=True
    )

    # 获取最近7天签到记录
    week_logs = query_db(
        "SELECT checkin_date, points_earned FROM checkin_logs WHERE user_id = ? AND checkin_date >= date('now', '-6 days', 'localtime') ORDER BY checkin_date",
        (session['user_id'],)
    )

    return jsonify({
        'success': True,
        'data': {
            'checked_today': today_log is not None,
            'consecutive_days': yesterday_log['consecutive_days'] if yesterday_log else 0,
            'week_logs': [dict(row) for row in week_logs]
        }
    })


# ==================== 等级API ====================

def _calc_level(total_points):
    """计算等级"""
    levels = [
        (0, 100, 1, '入门'),
        (100, 300, 2, '初级'),
        (300, 600, 3, '进阶'),
        (600, 1000, 4, '熟练'),
        (1000, 2000, 5, '精通'),
        (2000, 4000, 6, '专家'),
        (4000, 8000, 7, '资深'),
        (8000, float('inf'), 8, '首席'),
    ]
    for low, high, lv, name in levels:
        if total_points < high:
            progress = int((total_points - low) / (high - low) * 100) if high != float('inf') else 100
            return {'level': lv, 'name': name, 'progress': max(0, min(100, progress)), 'next': high if high != float('inf') else 0, 'current': total_points}
    return {'level': 8, 'name': '首席', 'progress': 100, 'next': 0, 'current': total_points}


@api_bp.route('/user/level', methods=['GET'])
@login_required
def api_user_level():
    """获取用户等级信息"""
    user = query_db('SELECT points, vip_level, vip_expire_time, machine_code_bound FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    level_info = _calc_level(user['points'])

    fav_count = query_db('SELECT COUNT(*) as cnt FROM user_favorites WHERE user_id = ?', (session['user_id'],), one=True)['cnt']
    follow_count = query_db('SELECT COUNT(*) as cnt FROM user_follows WHERE user_id = ?', (session['user_id'],), one=True)['cnt']

    return jsonify({
        'success': True,
        'data': {
            'points': user['points'],
            'vip_level': user['vip_level'],
            'vip_expire_time': user['vip_expire_time'],
            'level': level_info['level'],
            'level_name': level_info['name'],
            'level_progress': level_info['progress'],
            'next_level_points': level_info['next'],
            'fav_count': fav_count,
            'follow_count': follow_count,
            'machine_code_bound': user['machine_code_bound']
        }
    })


# ==================== 下载记录API ====================

@api_bp.route('/user/downloads', methods=['GET'])
@login_required
def api_user_downloads():
    """获取当前用户的下载记录"""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * 20
    total = query_db(
        'SELECT COUNT(*) as cnt FROM download_logs WHERE user_id = ?',
        (session['user_id'],), one=True
    )
    records = query_db(
        'SELECT dl.*, s.cover_image, s.is_free, s.require_vip '
        'FROM download_logs dl LEFT JOIN software s ON dl.software_id = s.id '
        'WHERE dl.user_id = ? ORDER BY dl.downloaded_at DESC LIMIT ? OFFSET ?',
        (session['user_id'], 20, offset)
    )
    return jsonify({
        'success': True,
        'data': {
            'list': [dict(r) for r in records],
            'total': total['cnt'] if total else 0,
            'page': page,
            'total_pages': (total['cnt'] + 19) // 20 if total and total['cnt'] > 0 else 0
        }
    })


# ==================== 等级权益API ====================

LEVEL_BENEFITS = [
    {'level': 1, 'name': '入门', 'min_points': 0, 'benefits': ['基础下载权限', '每日签到+10积分']},
    {'level': 2, 'name': '初级', 'min_points': 100, 'benefits': ['每日签到+12积分', '可下载30积分以下软件']},
    {'level': 3, 'name': '进阶', 'min_points': 300, 'benefits': ['每日签到+14积分', '可下载50积分以下软件', '积分商品9.5折']},
    {'level': 4, 'name': '熟练', 'min_points': 600, 'benefits': ['每日签到+16积分', '可下载80积分以下软件', '积分商品9折']},
    {'level': 5, 'name': '精通', 'min_points': 1000, 'benefits': ['每日签到+18积分', '可下载所有积分软件', '积分商品8.5折']},
    {'level': 6, 'name': '专家', 'min_points': 2000, 'benefits': ['每日签到+20积分', 'VIP兑换9折', '积分商品8折']},
    {'level': 7, 'name': '资深', 'min_points': 4000, 'benefits': ['每日签到+25积分', 'VIP兑换8折', '积分商品7折', '专属资深标识']},
    {'level': 8, 'name': '首席', 'min_points': 8000, 'benefits': ['每日签到+30积分', 'VIP兑换7折', '积分商品6折', '专属首席标识', '管理后台预览权限']},
]


@api_bp.route('/level/benefits', methods=['GET'])
def api_level_benefits():
    """获取所有等级权益"""
    return jsonify({'success': True, 'data': LEVEL_BENEFITS})


@api_bp.route('/user/level/benefits', methods=['GET'])
@login_required
def api_user_level_benefits():
    """获取当前用户的等级权益"""
    user = query_db('SELECT points FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    level_info = _calc_level(user['points'])
    current_benefits = None
    next_benefits = None
    for i, lb in enumerate(LEVEL_BENEFITS):
        if lb['level'] == level_info['level']:
            current_benefits = lb
            if i + 1 < len(LEVEL_BENEFITS):
                next_benefits = LEVEL_BENEFITS[i + 1]
            break
    return jsonify({
        'success': True,
        'data': {
            'current_level': level_info['level'],
            'current_name': level_info['name'],
            'current_points': user['points'],
            'next_level_points': level_info['next'],
            'progress': level_info['progress'],
            'current_benefits': current_benefits,
            'next_benefits': next_benefits
        }
    })


# ==================== 积分商店API ====================

SHOP_ITEMS = [
    {'id': 1, 'name': '7天VIP体验', 'description': '获得7天VIP会员资格，可下载VIP软件', 'price': 200, 'icon': '👑', 'type': 'vip_days', 'value': 7},
    {'id': 2, 'name': '30天VIP畅享', 'description': '获得30天VIP会员资格，畅享所有VIP软件', 'price': 700, 'icon': '👑', 'type': 'vip_days', 'value': 30},
    {'id': 3, 'name': '下载券 × 1', 'description': '获得1次额外下载机会（不受每日限制）', 'price': 20, 'icon': '📥', 'type': 'download_ticket', 'value': 1},
    {'id': 4, 'name': '下载券 × 5', 'description': '获得5次额外下载机会', 'price': 80, 'icon': '📥', 'type': 'download_ticket', 'value': 5},
    {'id': 5, 'name': '积分双倍卡（7天）', 'description': '7天内签到获得双倍积分', 'price': 150, 'icon': '⚡', 'type': 'double_points', 'value': 7},
    {'id': 6, 'name': '改名卡', 'description': '获得一次修改用户名的机会', 'price': 100, 'icon': '✏️', 'type': 'rename_card', 'value': 1},
]


@api_bp.route('/shop/items', methods=['GET'])
def api_shop_items():
    """获取积分商店商品列表"""
    user_points = 0
    if 'user_id' in session:
        user = query_db('SELECT points FROM users WHERE id = ?', (session['user_id'],), one=True)
        if user:
            user_points = user['points']
    return jsonify({
        'success': True,
        'data': {
            'items': SHOP_ITEMS,
            'user_points': user_points
        }
    })


@api_bp.route('/shop/buy', methods=['POST'])
@login_required
def api_shop_buy():
    """购买积分商店商品"""
    from datetime import datetime, timedelta
    data = request.get_json()
    item_id = data.get('item_id')
    if not item_id:
        return jsonify({'success': False, 'message': '请选择商品'}), 400

    item = None
    for it in SHOP_ITEMS:
        if it['id'] == item_id:
            item = it
            break
    if not item:
        return jsonify({'success': False, 'message': '商品不存在'}), 404

    user = query_db('SELECT points, vip_level, vip_expire_time FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    # 计算折扣
    level_info = _calc_level(user['points'])
    discount = 1.0
    for lb in LEVEL_BENEFITS:
        if lb['level'] == level_info['level']:
            for b in lb['benefits']:
                if '折' in b:
                    try:
                        discount = int(b.replace('积分商品', '').replace('折', '')) / 10
                    except:
                        pass
            break

    final_price = int(item['price'] * discount)
    if user['points'] < final_price:
        return jsonify({'success': False, 'message': f'积分不足，需要{final_price}积分（含{int((1-discount)*100)}%等级折扣）' if discount < 1 else f'积分不足，需要{final_price}积分'}), 400

    # 处理购买
    if item['type'] == 'vip_days':
        now = datetime.now()
        if user['vip_level'] and user['vip_level'] > 0 and user['vip_expire_time']:
            try:
                old_expire = datetime.strptime(user['vip_expire_time'], '%Y-%m-%d %H:%M:%S')
                new_expire = old_expire + timedelta(days=item['value'])
            except:
                new_expire = now + timedelta(days=item['value'])
        else:
            new_expire = now + timedelta(days=item['value'])
        execute_db(
            'UPDATE users SET points = points - ?, vip_level = CASE WHEN vip_level < 1 THEN 1 ELSE vip_level END, vip_expire_time = ? WHERE id = ?',
            (final_price, new_expire.strftime('%Y-%m-%d %H:%M:%S'), session['user_id'])
        )
        message = f'购买成功！VIP有效期延长至{new_expire.strftime("%Y-%m-%d")}'

    elif item['type'] == 'download_ticket':
        execute_db(
            'UPDATE users SET points = points - ?, extra_downloads = COALESCE(extra_downloads, 0) + ? WHERE id = ?',
            (final_price, item['value'], session['user_id'])
        )
        message = f'购买成功！获得{item["value"]}张下载券'

    elif item['type'] == 'double_points':
        expire_time = (datetime.now() + timedelta(days=item['value'])).strftime('%Y-%m-%d %H:%M:%S')
        execute_db(
            'UPDATE users SET points = points - ?, double_points_expire = ? WHERE id = ?',
            (final_price, expire_time, session['user_id'])
        )
        message = f'购买成功！{item["value"]}天内签到获得双倍积分'

    elif item['type'] == 'rename_card':
        execute_db(
            'UPDATE users SET points = points - ?, rename_available = COALESCE(rename_available, 0) + ? WHERE id = ?',
            (final_price, item['value'], session['user_id'])
        )
        message = f'购买成功！获得{item["value"]}次改名机会'

    else:
        return jsonify({'success': False, 'message': '商品类型不支持'}), 400

    user_new = query_db('SELECT points FROM users WHERE id = ?', (session['user_id'],), one=True)
    return jsonify({
        'success': True,
        'message': message,
        'data': {'points': user_new['points'] if user_new else 0}
    })


# ==================== 收藏API ====================

@api_bp.route('/favorite/toggle/<int:software_id>', methods=['POST'])
@login_required
def api_favorite_toggle(software_id):
    """切换收藏状态"""
    existing = query_db(
        'SELECT id FROM user_favorites WHERE user_id = ? AND software_id = ?',
        (session['user_id'], software_id), one=True
    )
    if existing:
        execute_db('DELETE FROM user_favorites WHERE id = ?', (existing['id'],))
        return jsonify({'success': True, 'message': '已取消收藏', 'data': {'favorited': False}})
    else:
        execute_db(
            'INSERT INTO user_favorites (user_id, software_id) VALUES (?, ?)',
            (session['user_id'], software_id)
        )
        return jsonify({'success': True, 'message': '收藏成功', 'data': {'favorited': True}})


@api_bp.route('/favorite/list', methods=['GET'])
@login_required
def api_favorite_list():
    """获取收藏列表"""
    favs = query_db(
        'SELECT s.id, s.name, s.version, s.description, s.cover_image, s.platform, '
        's.download_count, s.rating, c.name as category_name, uf.created_at as fav_time '
        'FROM user_favorites uf '
        'JOIN software s ON uf.software_id = s.id '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE uf.user_id = ? AND s.is_active = 1 '
        'ORDER BY uf.created_at DESC',
        (session['user_id'],)
    )
    return jsonify({'success': True, 'data': [dict(row) for row in favs]})


# ==================== 关注更新API ====================

@api_bp.route('/follow/toggle/<int:software_id>', methods=['POST'])
@login_required
def api_follow_toggle(software_id):
    """切换关注状态"""
    existing = query_db(
        'SELECT id FROM user_follows WHERE user_id = ? AND software_id = ?',
        (session['user_id'], software_id), one=True
    )
    if existing:
        execute_db('DELETE FROM user_follows WHERE id = ?', (existing['id'],))
        return jsonify({'success': True, 'message': '已取消关注', 'data': {'followed': False}})
    else:
        execute_db(
            'INSERT INTO user_follows (user_id, software_id) VALUES (?, ?)',
            (session['user_id'], software_id)
        )
        return jsonify({'success': True, 'message': '关注成功，有新版本将通知你', 'data': {'followed': True}})


@api_bp.route('/follow/list', methods=['GET'])
@login_required
def api_follow_list():
    """获取关注列表"""
    follows = query_db(
        'SELECT s.id, s.name, s.version, s.description, s.cover_image, s.platform, '
        's.download_count, s.updated_at, c.name as category_name, uf.created_at as follow_time '
        'FROM user_follows uf '
        'JOIN software s ON uf.software_id = s.id '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE uf.user_id = ? AND s.is_active = 1 '
        'ORDER BY s.updated_at DESC',
        (session['user_id'],)
    )
    return jsonify({'success': True, 'data': [dict(row) for row in follows]})


@api_bp.route('/follow/updates', methods=['GET'])
@login_required
def api_follow_updates():
    """获取关注的软件更新提醒"""
    updates = query_db(
        'SELECT s.id, s.name, s.version, s.description, s.updated_at, c.name as category_name '
        'FROM user_follows uf '
        'JOIN software s ON uf.software_id = s.id '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE uf.user_id = ? AND uf.notify_update = 1 AND s.is_active = 1 '
        'ORDER BY s.updated_at DESC LIMIT 20',
        (session['user_id'],)
    )
    return jsonify({'success': True, 'data': [dict(row) for row in updates]})


@api_bp.route('/software/<int:software_id>/status', methods=['GET'])
@login_required
def api_software_user_status(software_id):
    """获取用户对某个软件的状态（是否收藏/关注）"""
    fav = query_db(
        'SELECT id FROM user_favorites WHERE user_id = ? AND software_id = ?',
        (session['user_id'], software_id), one=True
    )
    follow = query_db(
        'SELECT id FROM user_follows WHERE user_id = ? AND software_id = ?',
        (session['user_id'], software_id), one=True
    )
    return jsonify({
        'success': True,
        'data': {
            'favorited': fav is not None,
            'followed': follow is not None
        }
    })


# ==================== 版本校验API ====================

@api_bp.route('/check-version')
def api_check_version():
    """校验App版本是否有效（用于版本作废机制）"""
    version_code = request.args.get('version', '').strip()
    if not version_code:
        return jsonify({'valid': False, 'message': '缺少版本号'})

    version = query_db(
        'SELECT * FROM app_versions WHERE version_code = ?',
        (version_code,), one=True
    )

    if version and version['is_active']:
        return jsonify({'valid': True})

    latest = query_db(
        'SELECT version_code, version_name FROM app_versions WHERE is_active = 1 ORDER BY id DESC LIMIT 1',
        one=True
    )
    return jsonify({
        'valid': False,
        'message': '此版本已被作废，请下载最新版本',
        'latest_version': dict(latest) if latest else None
    })