# -*- coding: utf-8 -*-
# 杞欢搴撶郴缁?- REST API璺敱锛堜緵鎵嬫満绔拰鐢佃剳绔皟鐢級

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


# ==================== 杞欢鐩稿叧API ====================

@api_bp.route('/software/list')
def api_software_list():
    """鑾峰彇杞欢鍒楄〃"""
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
    """鑾峰彇杞欢璇︽儏"""
    software = query_db(
        'SELECT s.*, c.name as category_name FROM software s '
        'LEFT JOIN categories c ON s.category_id = c.id '
        'WHERE s.id = ? AND s.is_active = 1',
        (software_id,), one=True
    )
    if not software:
        return jsonify({'success': False, 'message': '杞欢涓嶅瓨鍦?}), 404

    execute_db('UPDATE software SET view_count = view_count + 1 WHERE id = ?', (software_id,))

    return jsonify({
        'success': True,
        'data': dict(software)
    })


@api_bp.route('/software/search')
def api_software_search():
    """鎼滅储杞欢"""
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category_id', 0, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE

    if not q:
        return jsonify({'success': False, 'message': '璇疯緭鍏ユ悳绱㈠叧閿瘝'})

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
    """涓嬭浇杞欢 - 闇€瑕佺櫥褰曚笖鏈夋潈闄?""
    software = query_db('SELECT * FROM software WHERE id = ? AND is_active = 1', (software_id,), one=True)
    if not software:
        return jsonify({'success': False, 'message': '杞欢涓嶅瓨鍦?}), 404

    user = query_db('SELECT * FROM users WHERE id = ?', (session['user_id'],), one=True)

    data = request.get_json(silent=True) or {}
    app_signature = request.headers.get('X-App-Signature', '')
    app_token = request.headers.get('X-App-Token', '')
    device_id = request.headers.get('X-Device-Id', '')
    user_agent = request.headers.get('User-Agent', '')

    if app_signature and data:
        sig_params = {k: str(v) for k, v in data.items() if k != 'signature'}
        if not verify_request_signature(sig_params, app_signature):
            return jsonify({'success': False, 'message': '璇锋眰绛惧悕楠岃瘉澶辫触'}), 403

    if app_token:
        if not verify_app_token(app_token, session['user_id'], device_id):
            return jsonify({'success': False, 'message': '浠ょ墝鏃犳晥鎴栧凡杩囨湡'}), 403

    if device_id or user_agent:
        emu_indicators = check_emulator(device_id, user_agent)
        if emu_indicators:
            execute_db(
                "INSERT INTO security_logs (event_type, ip_address, details, severity) VALUES (?, ?, ?, ?)",
                ('emulator_detected', request.remote_addr, f'妯℃嫙鍣ㄧ幆澧? {emu_indicators}', 'warning')
            )

    # 闈炲厤璐硅蒋浠讹細鏍￠獙鏄惁閫氳繃閭€璇风爜娉ㄥ唽
    if not software['is_free']:
        invite_check = query_db(
            "SELECT * FROM card_keys WHERE used_by = ? AND card_type = 'register' AND status = 'used'",
            (session['user_id'],), one=True
        )
        if not invite_check:
            return jsonify({'success': False, 'message': '姝よ祫婧愰渶瑕佽喘涔伴個璇风爜鎵嶈兘涓嬭浇锛岃鍏堣喘涔伴個璇风爜娉ㄥ唽'}), 403

    # 妫€鏌IP瑕佹眰
    if software['require_vip']:
        if user['vip_level'] < 1:
            return jsonify({'success': False, 'message': '姝よ蒋浠堕渶瑕乂IP浼氬憳鎵嶈兘涓嬭浇锛岃鍏堝厬鎹IP鍗″瘑'}), 403
        if user['vip_expire_time']:
            from datetime import datetime
            expire = datetime.strptime(user['vip_expire_time'], '%Y-%m-%d %H:%M:%S')
            if expire < datetime.now():
                return jsonify({'success': False, 'message': '鎮ㄧ殑VIP宸茶繃鏈燂紝璇风画璐?}), 403

    # 妫€鏌ユ満鍣ㄧ爜缁戝畾锛堥潪鍏嶈垂杞欢闇€瑕佹牎楠屾満鍣ㄧ爜锛?    if not software['is_free']:
        data = request.get_json(silent=True) or {}
        req_machine_code = (data.get('machine_code') or '').strip()
        if user['machine_code'] and req_machine_code != user['machine_code']:
            return jsonify({'success': False, 'message': '鏈哄櫒鐮佷笉鍖归厤锛岃鍦ㄧ粦瀹氱殑璁惧涓婁笅杞?}), 403

    # 妫€鏌ユ瘡鏃ユ渶澶т笅杞芥鏁?    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    today_downloads = query_db(
        "SELECT COUNT(*) as cnt FROM download_logs WHERE user_id = ? AND date(downloaded_at) = ?",
        (session['user_id'], today), one=True
    )
    max_daily = int(get_config('max_downloads_per_day') or 50)
    if today_downloads and today_downloads['cnt'] >= max_daily:
        return jsonify({'success': False, 'message': f'浠婃棩涓嬭浇娆℃暟宸茶揪涓婇檺({max_daily}娆?'}), 429

    # 妫€鏌ヤ笅杞介棿闅?    last_download = query_db(
        'SELECT downloaded_at FROM download_logs WHERE user_id = ? ORDER BY downloaded_at DESC LIMIT 1',
        (session['user_id'],), one=True
    )
    if last_download:
        interval = int(get_config('download_interval') or 30)
        last_time = datetime.strptime(last_download['downloaded_at'], '%Y-%m-%d %H:%M:%S')
        elapsed = (datetime.now() - last_time).total_seconds()
        if elapsed < interval:
            remaining = interval - int(elapsed)
            return jsonify({'success': False, 'message': f'涓嬭浇杩囦簬棰戠箒锛岃{remaining}绉掑悗鍐嶈瘯'}), 429

    # 妫€鏌ョН鍒嗚姹?    if software['require_points'] and software['require_points'] > 0:
        if user['points'] < software['require_points']:
            return jsonify({'success': False, 'message': f'闇€瑕亄software["require_points"]}绉垎鎵嶈兘涓嬭浇'}), 403

    # 鐢熸垚鍔犲瘑涓嬭浇閾炬帴锛堜竴娆℃€oken锛?    download_token = aes_encrypt(f"{software_id}:{session['user_id']}:{int(time.time())}")

    # token鐢熸垚鎴愬姛鍚庢墸闄ょН鍒?    if software['require_points'] and software['require_points'] > 0:
        execute_db('UPDATE users SET points = points - ? WHERE id = ?',
                   (software['require_points'], session['user_id']))

    # 璁板綍涓嬭浇
    execute_db('UPDATE software SET download_count = download_count + 1 WHERE id = ?', (software_id,))
    execute_db(
        'INSERT INTO download_logs (user_id, software_id, software_name, ip_address, machine_code) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], software_id, software['name'], request.remote_addr, user['machine_code'])
    )

    return jsonify({
        'success': True,
        'message': '鑾峰彇涓嬭浇閾炬帴鎴愬姛',
        'data': {
            'download_url': f"/api/software/do_download/{download_token}",
            'file_name': software['name'],
            'file_size': software['file_size']
        }
    })


@api_bp.route('/software/do_download/<token>')
def api_do_download(token):
    """瀹為檯涓嬭浇鏂囦欢 - 楠岃瘉token"""
    decrypted = aes_decrypt(token)
    if not decrypted:
        return jsonify({'success': False, 'message': '涓嬭浇閾炬帴鏃犳晥鎴栧凡杩囨湡'}), 403

    try:
        software_id, user_id, ts = decrypted.split(':')
        if int(time.time()) - int(ts) > 300:  # 5鍒嗛挓鏈夋晥鏈?            return jsonify({'success': False, 'message': '涓嬭浇閾炬帴宸茶繃鏈?}), 403
    except Exception:
        return jsonify({'success': False, 'message': '涓嬭浇閾炬帴鏃犳晥'}), 403

    software = query_db('SELECT * FROM software WHERE id = ?', (software_id,), one=True)
    if not software:
        return jsonify({'success': False, 'message': '杞欢涓嶅瓨鍦?}), 404

    from flask import send_from_directory
    import os
    file_path = software['file_path']
    if file_path and os.path.exists(file_path):
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        return send_from_directory(directory, filename, as_attachment=True,
                                   download_name=filename)
    return jsonify({'success': False, 'message': '鏂囦欢涓嶅瓨鍦?}), 404


# ==================== 鍒嗙被API ====================

@api_bp.route('/categories')
def api_categories():
    """鑾峰彇鎵€鏈夊垎绫?""
    categories = query_db(
        'SELECT c.*, COUNT(s.id) as software_count FROM categories c '
        'LEFT JOIN software s ON s.category_id = c.id AND s.is_active = 1 '
        'WHERE c.is_active = 1 GROUP BY c.id ORDER BY c.sort_order'
    )
    return jsonify({
        'success': True,
        'data': [dict(row) for row in categories]
    })


# ==================== 鍗″瘑API ====================

@api_bp.route('/card/redeem', methods=['POST'])
@login_required
@rate_limit(max_requests=5, window=300)
@csrf_protect
def api_card_redeem():
    """鍏戞崲鍗″瘑"""
    data = request.get_json() or {}
    card_key = (data.get('card_key') or '').strip().upper()
    machine_code = (data.get('machine_code') or '').strip()

    if not card_key:
        return jsonify({'success': False, 'message': '璇疯緭鍏ュ崱瀵?})

    # 楠岃瘉鍗″瘑瀹屾暣鎬?    if not verify_card_key_integrity(card_key):
        return jsonify({'success': False, 'message': '鍗″瘑鏍煎紡鏃犳晥'})

    # 鑾峰彇鏁版嵁搴撹繛鎺ワ紝寮€鍚簨鍔?    db = get_db()
    try:
        # 鏌ユ壘鍗″瘑
        clean_key = card_key.replace('-', '')
        card = db.execute(
            'SELECT * FROM card_keys WHERE REPLACE(card_key, "-", "") = ?',
            (clean_key,)
        ).fetchone()

        if not card:
            return jsonify({'success': False, 'message': '鍗″瘑涓嶅瓨鍦?})

        if card['status'] == 'used':
            return jsonify({'success': False, 'message': '璇ュ崱瀵嗗凡琚娇鐢?})

        if card['status'] == 'disabled':
            return jsonify({'success': False, 'message': '璇ュ崱瀵嗗凡琚鐢?})

        # 鎵ц鍏戞崲
        user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

        if card['card_type'] == 'vip':
            # VIP鍗″瘑
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
            # 绉垎鍗″瘑
            db.execute(
                'UPDATE users SET points = points + ? WHERE id = ?',
                (card['points'], session['user_id'])
            )

        # 鏇存柊鍗″瘑鐘舵€?        db.execute(
            "UPDATE card_keys SET status = 'used', used_by = ?, used_at = datetime('now', 'localtime'), bound_machine_code = ? WHERE id = ?",
            (session['user_id'], machine_code, card['id'])
        )

        # 鍐欏叆瀹夊叏鏃ュ織
        db.execute(
            "INSERT INTO security_logs (event_type, ip_address, details, severity) VALUES (?, ?, ?, ?)",
            ('card_redeem', request.remote_addr,
             f'鐢ㄦ埛ID:{session["user_id"]} 鍏戞崲浜唟card["card_type"]}鍗″瘑(ID:{card["id"]})',
             'info')
        )

        # 鎻愪氦浜嬪姟
        db.commit()

        return jsonify({
            'success': True,
            'message': f'鍏戞崲鎴愬姛锛? + (
                f'VIP鏃堕暱澧炲姞{card["vip_days"]}澶? if card['card_type'] == 'vip'
                else f'鑾峰緱{card["points"]}绉垎'
            )
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': '鍏戞崲澶辫触锛岀郴缁熼敊璇紝璇烽噸璇?})
    finally:
        db.close()


@api_bp.route('/card/list', methods=['GET'])
@login_required
def api_card_list():
    """鑾峰彇鐢ㄦ埛鐨勫崱瀵嗕娇鐢ㄨ褰?""
    records = query_db(
        'SELECT * FROM card_keys WHERE used_by = ? ORDER BY used_at DESC LIMIT 20',
        (session['user_id'],)
    )
    return jsonify({
        'success': True,
        'data': [dict(row) for row in records]
    })


# ==================== 鍏憡API ====================

@api_bp.route('/announcements')
def api_announcements():
    """鑾峰彇鍏憡鍒楄〃"""
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


# ==================== 鍙嶉API ====================

@api_bp.route('/feedback/submit', methods=['POST'])
@login_required
@rate_limit(max_requests=3, window=300)
@csrf_protect
def api_feedback_submit():
    """鎻愪氦鍙嶉"""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    feedback_type = data.get('type', 'suggestion')

    if not title or not content:
        return jsonify({'success': False, 'message': '璇峰～鍐欐爣棰樺拰鍐呭'})

    if len(content) < 5:
        return jsonify({'success': False, 'message': '鍐呭鑷冲皯5涓瓧'})

    execute_db(
        'INSERT INTO feedback (user_id, username, title, content, type) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], session.get('username', ''), title, content, feedback_type)
    )

    return jsonify({'success': True, 'message': '鍙嶉鎻愪氦鎴愬姛锛屾劅璋㈡偍鐨勫弽棣堬紒'})


@api_bp.route('/feedback/list', methods=['GET'])
@login_required
def api_feedback_list():
    """鑾峰彇鐢ㄦ埛鐨勫弽棣堝垪琛?""
    records = query_db(
        'SELECT * FROM feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT 20',
        (session['user_id'],)
    )
    return jsonify({
        'success': True,
        'data': [dict(row) for row in records]
    })


# ==================== 缁熻API ====================

@api_bp.route('/stats/overview')
def api_stats_overview():
    """鑾峰彇绔欑偣缁熻姒傝"""
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


# ==================== 骞垮憡API ====================

@api_bp.route('/ads/<position>')
def api_ads(position):
    """鑾峰彇骞垮憡浣嶅唴瀹?""
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
    """骞垮憡鐐瑰嚮缁熻"""
    execute_db('UPDATE ad_slots SET click_count = click_count + 1 WHERE id = ?', (ad_id,))
    return jsonify({'success': True})


# ==================== 绛惧埌API ====================

@api_bp.route('/checkin', methods=['POST'])
@login_required
def api_checkin():
    """姣忔棩绛惧埌"""
    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')

    # 妫€鏌ヤ粖鏃ユ槸鍚﹀凡绛惧埌
    existing = query_db(
        'SELECT * FROM checkin_logs WHERE user_id = ? AND checkin_date = ?',
        (session['user_id'], today), one=True
    )
    if existing:
        return jsonify({'success': False, 'message': '浠婃棩宸茬鍒?})

    # 璁＄畻杩炵画绛惧埌澶╂暟
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_log = query_db(
        'SELECT consecutive_days FROM checkin_logs WHERE user_id = ? AND checkin_date = ?',
        (session['user_id'], yesterday), one=True
    )
    consecutive = (yesterday_log['consecutive_days'] if yesterday_log else 0) + 1

    # 鏍规嵁绛夌骇璁＄畻鍩虹绉垎
    user = query_db('SELECT points, double_points_expire FROM users WHERE id = ?', (session['user_id'],), one=True)
    level_info = _calc_level(user['points'])
    base_points = 10 + (level_info['level'] - 1) * 2  # Lv.1=10, Lv.2=12, Lv.3=14...

    # 杩炵画绛惧埌濂栧姳
    bonus = 0
    if consecutive % 7 == 0:
        bonus = 50
    elif consecutive % 3 == 0:
        bonus = 15

    total_earned = base_points + bonus

    # 鍙屽€嶇Н鍒嗘娴?    is_double = False
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

    # 鑾峰彇鐢ㄦ埛鏈€鏂颁俊鎭?    user = query_db('SELECT points, vip_level, vip_expire_time FROM users WHERE id = ?', (session['user_id'],), one=True)
    level_info = _calc_level(user['points'])

    msg = f'绛惧埌鎴愬姛锛佽幏寰梴total_earned}绉垎'
    if bonus:
        msg += f'锛堝惈杩炵画{consecutive}澶╁鍔眥bonus}绉垎锛?
    if is_double:
        msg += '锛堝弻鍊嶇Н鍒嗗崱鐢熸晥涓級'

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
    """鑾峰彇绛惧埌鐘舵€?""
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

    # 鑾峰彇鏈€杩?澶╃鍒拌褰?    week_logs = query_db(
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


# ==================== 绛夌骇API ====================

def _calc_level(total_points):
    """璁＄畻绛夌骇"""
    levels = [
        (0, 100, 1, '鍏ラ棬'),
        (100, 300, 2, '鍒濈骇'),
        (300, 600, 3, '杩涢樁'),
        (600, 1000, 4, '鐔熺粌'),
        (1000, 2000, 5, '绮鹃€?),
        (2000, 4000, 6, '涓撳'),
        (4000, 8000, 7, '璧勬繁'),
        (8000, float('inf'), 8, '棣栧腑'),
    ]
    for low, high, lv, name in levels:
        if total_points < high:
            progress = int((total_points - low) / (high - low) * 100) if high != float('inf') else 100
            return {'level': lv, 'name': name, 'progress': max(0, min(100, progress)), 'next': high if high != float('inf') else 0, 'current': total_points}
    return {'level': 8, 'name': '棣栧腑', 'progress': 100, 'next': 0, 'current': total_points}


@api_bp.route('/user/level', methods=['GET'])
@login_required
def api_user_level():
    """鑾峰彇鐢ㄦ埛绛夌骇淇℃伅"""
    user = query_db('SELECT points, vip_level, vip_expire_time, machine_code_bound FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not user:
        return jsonify({'success': False, 'message': '鐢ㄦ埛涓嶅瓨鍦?}), 404
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


# ==================== 涓嬭浇璁板綍API ====================

@api_bp.route('/user/downloads', methods=['GET'])
@login_required
def api_user_downloads():
    """鑾峰彇褰撳墠鐢ㄦ埛鐨勪笅杞借褰?""
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


# ==================== 绛夌骇鏉冪泭API ====================

LEVEL_BENEFITS = [
    {'level': 1, 'name': '鍏ラ棬', 'min_points': 0, 'benefits': ['鍩虹涓嬭浇鏉冮檺', '姣忔棩绛惧埌+10绉垎']},
    {'level': 2, 'name': '鍒濈骇', 'min_points': 100, 'benefits': ['姣忔棩绛惧埌+12绉垎', '鍙笅杞?0绉垎浠ヤ笅杞欢']},
    {'level': 3, 'name': '杩涢樁', 'min_points': 300, 'benefits': ['姣忔棩绛惧埌+14绉垎', '鍙笅杞?0绉垎浠ヤ笅杞欢', '绉垎鍟嗗搧9.5鎶?]},
    {'level': 4, 'name': '鐔熺粌', 'min_points': 600, 'benefits': ['姣忔棩绛惧埌+16绉垎', '鍙笅杞?0绉垎浠ヤ笅杞欢', '绉垎鍟嗗搧9鎶?]},
    {'level': 5, 'name': '绮鹃€?, 'min_points': 1000, 'benefits': ['姣忔棩绛惧埌+18绉垎', '鍙笅杞芥墍鏈夌Н鍒嗚蒋浠?, '绉垎鍟嗗搧8.5鎶?]},
    {'level': 6, 'name': '涓撳', 'min_points': 2000, 'benefits': ['姣忔棩绛惧埌+20绉垎', 'VIP鍏戞崲9鎶?, '绉垎鍟嗗搧8鎶?]},
    {'level': 7, 'name': '璧勬繁', 'min_points': 4000, 'benefits': ['姣忔棩绛惧埌+25绉垎', 'VIP鍏戞崲8鎶?, '绉垎鍟嗗搧7鎶?, '涓撳睘璧勬繁鏍囪瘑']},
    {'level': 8, 'name': '棣栧腑', 'min_points': 8000, 'benefits': ['姣忔棩绛惧埌+30绉垎', 'VIP鍏戞崲7鎶?, '绉垎鍟嗗搧6鎶?, '涓撳睘棣栧腑鏍囪瘑', '绠＄悊鍚庡彴棰勮鏉冮檺']},
]


@api_bp.route('/level/benefits', methods=['GET'])
def api_level_benefits():
    """鑾峰彇鎵€鏈夌瓑绾ф潈鐩?""
    return jsonify({'success': True, 'data': LEVEL_BENEFITS})


@api_bp.route('/user/level/benefits', methods=['GET'])
@login_required
def api_user_level_benefits():
    """鑾峰彇褰撳墠鐢ㄦ埛鐨勭瓑绾ф潈鐩?""
    user = query_db('SELECT points FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not user:
        return jsonify({'success': False, 'message': '鐢ㄦ埛涓嶅瓨鍦?}), 404
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


# ==================== 绉垎鍟嗗簵API ====================

SHOP_ITEMS = [
    {'id': 1, 'name': '7澶￢IP浣撻獙', 'description': '鑾峰緱7澶￢IP浼氬憳璧勬牸锛屽彲涓嬭浇VIP杞欢', 'price': 200, 'icon': '馃憫', 'type': 'vip_days', 'value': 7},
    {'id': 2, 'name': '30澶￢IP鐣呬韩', 'description': '鑾峰緱30澶￢IP浼氬憳璧勬牸锛岀晠浜墍鏈塚IP杞欢', 'price': 700, 'icon': '馃憫', 'type': 'vip_days', 'value': 30},
    {'id': 3, 'name': '涓嬭浇鍒?脳 1', 'description': '鑾峰緱1娆￠澶栦笅杞芥満浼氾紙涓嶅彈姣忔棩闄愬埗锛?, 'price': 20, 'icon': '馃摜', 'type': 'download_ticket', 'value': 1},
    {'id': 4, 'name': '涓嬭浇鍒?脳 5', 'description': '鑾峰緱5娆￠澶栦笅杞芥満浼?, 'price': 80, 'icon': '馃摜', 'type': 'download_ticket', 'value': 5},
    {'id': 5, 'name': '绉垎鍙屽€嶅崱锛?澶╋級', 'description': '7澶╁唴绛惧埌鑾峰緱鍙屽€嶇Н鍒?, 'price': 150, 'icon': '鈿?, 'type': 'double_points', 'value': 7},
    {'id': 6, 'name': '鏀瑰悕鍗?, 'description': '鑾峰緱涓€娆′慨鏀圭敤鎴峰悕鐨勬満浼?, 'price': 100, 'icon': '鉁忥笍', 'type': 'rename_card', 'value': 1},
]


@api_bp.route('/shop/items', methods=['GET'])
def api_shop_items():
    """鑾峰彇绉垎鍟嗗簵鍟嗗搧鍒楄〃"""
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
    """璐拱绉垎鍟嗗簵鍟嗗搧"""
    from datetime import datetime, timedelta
    data = request.get_json()
    item_id = data.get('item_id')
    if not item_id:
        return jsonify({'success': False, 'message': '璇烽€夋嫨鍟嗗搧'}), 400

    item = None
    for it in SHOP_ITEMS:
        if it['id'] == item_id:
            item = it
            break
    if not item:
        return jsonify({'success': False, 'message': '鍟嗗搧涓嶅瓨鍦?}), 404

    user = query_db('SELECT points, vip_level, vip_expire_time FROM users WHERE id = ?', (session['user_id'],), one=True)
    if not user:
        return jsonify({'success': False, 'message': '鐢ㄦ埛涓嶅瓨鍦?}), 404

    # 璁＄畻鎶樻墸
    level_info = _calc_level(user['points'])
    discount = 1.0
    for lb in LEVEL_BENEFITS:
        if lb['level'] == level_info['level']:
            for b in lb['benefits']:
                if '鎶? in b:
                    try:
                        discount = int(b.replace('绉垎鍟嗗搧', '').replace('鎶?, '')) / 10
                    except:
                        pass
            break

    final_price = int(item['price'] * discount)
    if user['points'] < final_price:
        return jsonify({'success': False, 'message': f'绉垎涓嶈冻锛岄渶瑕亄final_price}绉垎锛堝惈{int((1-discount)*100)}%绛夌骇鎶樻墸锛? if discount < 1 else f'绉垎涓嶈冻锛岄渶瑕亄final_price}绉垎'}), 400

    # 澶勭悊璐拱
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
        message = f'璐拱鎴愬姛锛乂IP鏈夋晥鏈熷欢闀胯嚦{new_expire.strftime("%Y-%m-%d")}'

    elif item['type'] == 'download_ticket':
        execute_db(
            'UPDATE users SET points = points - ?, extra_downloads = COALESCE(extra_downloads, 0) + ? WHERE id = ?',
            (final_price, item['value'], session['user_id'])
        )
        message = f'璐拱鎴愬姛锛佽幏寰梴item["value"]}寮犱笅杞藉埜'

    elif item['type'] == 'double_points':
        expire_time = (datetime.now() + timedelta(days=item['value'])).strftime('%Y-%m-%d %H:%M:%S')
        execute_db(
            'UPDATE users SET points = points - ?, double_points_expire = ? WHERE id = ?',
            (final_price, expire_time, session['user_id'])
        )
        message = f'璐拱鎴愬姛锛亄item["value"]}澶╁唴绛惧埌鑾峰緱鍙屽€嶇Н鍒?

    elif item['type'] == 'rename_card':
        execute_db(
            'UPDATE users SET points = points - ?, rename_available = COALESCE(rename_available, 0) + ? WHERE id = ?',
            (final_price, item['value'], session['user_id'])
        )
        message = f'璐拱鎴愬姛锛佽幏寰梴item["value"]}娆℃敼鍚嶆満浼?

    else:
        return jsonify({'success': False, 'message': '鍟嗗搧绫诲瀷涓嶆敮鎸?}), 400

    user_new = query_db('SELECT points FROM users WHERE id = ?', (session['user_id'],), one=True)
    return jsonify({
        'success': True,
        'message': message,
        'data': {'points': user_new['points'] if user_new else 0}
    })


# ==================== 鏀惰棌API ====================

@api_bp.route('/favorite/toggle/<int:software_id>', methods=['POST'])
@login_required
def api_favorite_toggle(software_id):
    """鍒囨崲鏀惰棌鐘舵€?""
    existing = query_db(
        'SELECT id FROM user_favorites WHERE user_id = ? AND software_id = ?',
        (session['user_id'], software_id), one=True
    )
    if existing:
        execute_db('DELETE FROM user_favorites WHERE id = ?', (existing['id'],))
        return jsonify({'success': True, 'message': '宸插彇娑堟敹钘?, 'data': {'favorited': False}})
    else:
        execute_db(
            'INSERT INTO user_favorites (user_id, software_id) VALUES (?, ?)',
            (session['user_id'], software_id)
        )
        return jsonify({'success': True, 'message': '鏀惰棌鎴愬姛', 'data': {'favorited': True}})


@api_bp.route('/favorite/list', methods=['GET'])
@login_required
def api_favorite_list():
    """鑾峰彇鏀惰棌鍒楄〃"""
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


# ==================== 鍏虫敞鏇存柊API ====================

@api_bp.route('/follow/toggle/<int:software_id>', methods=['POST'])
@login_required
def api_follow_toggle(software_id):
    """鍒囨崲鍏虫敞鐘舵€?""
    existing = query_db(
        'SELECT id FROM user_follows WHERE user_id = ? AND software_id = ?',
        (session['user_id'], software_id), one=True
    )
    if existing:
        execute_db('DELETE FROM user_follows WHERE id = ?', (existing['id'],))
        return jsonify({'success': True, 'message': '宸插彇娑堝叧娉?, 'data': {'followed': False}})
    else:
        execute_db(
            'INSERT INTO user_follows (user_id, software_id) VALUES (?, ?)',
            (session['user_id'], software_id)
        )
        return jsonify({'success': True, 'message': '鍏虫敞鎴愬姛锛屾湁鏂扮増鏈皢閫氱煡浣?, 'data': {'followed': True}})


@api_bp.route('/follow/list', methods=['GET'])
@login_required
def api_follow_list():
    """鑾峰彇鍏虫敞鍒楄〃"""
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
    """鑾峰彇鍏虫敞鐨勮蒋浠舵洿鏂版彁閱?""
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
    """鑾峰彇鐢ㄦ埛瀵规煇涓蒋浠剁殑鐘舵€侊紙鏄惁鏀惰棌/鍏虫敞锛?""
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


# ==================== 鐗堟湰鏍￠獙API ====================

@api_bp.route('/check-version')
def api_check_version():
    """鏍￠獙App鐗堟湰鏄惁鏈夋晥锛堢敤浜庣増鏈綔搴熸満鍒讹級"""
    version_code = request.args.get('version', '').strip()
    if not version_code:
        return jsonify({'valid': False, 'message': '缂哄皯鐗堟湰鍙?})

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
        'message': '姝ょ増鏈凡琚綔搴燂紝璇蜂笅杞芥渶鏂扮増鏈?,
        'latest_version': dict(latest) if latest else None
    })


# ==================== 鏁版嵁搴撲慨澶岮PI锛堜竴娆℃€т娇鐢紝鐢ㄥ畬璇峰垹闄わ級 ====================

@api_bp.route('/fix-database', methods=['POST'])
def api_fix_database():
    """淇鏁版嵁搴擄細灏?.0.1璁句负鏈夋晥锛?.0.0璁句负浣滃簾"""
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if token != 'arcane_fix_2024_db':
        return jsonify({'success': False, 'message': '鏃犳晥浠ょ墝'}), 403

    db = get_db()
    try:
        db.execute("INSERT OR IGNORE INTO app_versions (version_code, version_name, is_active) VALUES ('1.0.0', '鍒濆鐗堟湰(宸蹭綔搴?', 0)")
        db.execute("INSERT OR IGNORE INTO app_versions (version_code, version_name, is_active) VALUES ('1.0.1', '鏈€鏂扮増鏈?, 1)")
        db.execute("UPDATE app_versions SET is_active = 0 WHERE version_code = '1.0.0'")
        db.execute("UPDATE app_versions SET is_active = 1 WHERE version_code = '1.0.1'")
        db.commit()

        rows = db.execute("SELECT version_code, is_active FROM app_versions").fetchall()
        result = {r['version_code']: r['is_active'] for r in rows}
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()