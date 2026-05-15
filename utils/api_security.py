# -*- coding: utf-8 -*-
import hashlib
import hmac
import time
import secrets

API_KEY = 'AR23c@n3_53cuR3_4p!K3y_2026'

def generate_app_token(user_id, device_id=''):
    timestamp = int(time.time())
    raw = f"{user_id}:{device_id}:{timestamp}:{API_KEY}"
    token = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{token}:{timestamp}"

def verify_app_token(token, user_id, device_id='', max_age=3600):
    try:
        parts = token.split(':')
        if len(parts) != 2:
            return False
        token_hash, timestamp = parts
        timestamp = int(timestamp)
        if int(time.time()) - timestamp > max_age:
            return False
        raw = f"{user_id}:{device_id}:{timestamp}:{API_KEY}"
        expected = hashlib.sha256(raw.encode()).hexdigest()[:32]
        return hmac.compare_digest(token_hash, expected)
    except Exception:
        return False

def sign_request(params, secret=API_KEY):
    sorted_keys = sorted(params.keys())
    raw = '&'.join(f"{k}={params[k]}" for k in sorted_keys)
    raw += f"&secret={secret}"
    return hashlib.sha256(raw.encode()).hexdigest()

def verify_request_signature(params, signature, secret=API_KEY):
    if not signature:
        return False
    expected = sign_request(params, secret)
    return hmac.compare_digest(expected, signature)

def generate_device_challenge(device_id):
    raw = f"{device_id}:{int(time.time() // 300)}:{API_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def check_emulator(device_id='', user_agent=''):
    indicators = []
    if user_agent:
        emulator_agents = ['sdk_google', 'generic', 'emulator', 'android_studio', 'nox', 'bluestacks', 'mumu', 'memu', 'leidian', 'xiaoyao', 'genymotion']
        ua_lower = user_agent.lower()
        for ea in emulator_agents:
            if ea in ua_lower:
                indicators.append(f'ua:{ea}')
    if device_id:
        fake_ids = ['000000000000000', '0123456789abcdef', 'emulator', 'android_vm']
        did_lower = device_id.lower()
        for fid in fake_ids:
            if fid in did_lower:
                indicators.append(f'dev:{fid}')
    return indicators