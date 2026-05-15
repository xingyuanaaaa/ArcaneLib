# -*- coding: utf-8 -*-
# 软件库系统 - 加密与安全模块
# 提供AES加密解密、卡密生成验证、代码完整性校验等功能

import os
import hashlib
import base64
import hmac
import struct
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
from config import AES_KEY


def _get_cipher(iv):
    """获取AES加密器"""
    return AES.new(AES_KEY, AES.MODE_CBC, iv)


def aes_encrypt(plain_text):
    """AES-256-CBC加密"""
    try:
        iv = get_random_bytes(16)
        cipher = _get_cipher(iv)
        encrypted = cipher.encrypt(pad(plain_text.encode('utf-8'), AES.block_size))
        return base64.b64encode(iv + encrypted).decode('utf-8')
    except Exception:
        return None


def aes_decrypt(cipher_text):
    """AES-256-CBC解密"""
    try:
        raw = base64.b64decode(cipher_text)
        iv = raw[:16]
        encrypted = raw[16:]
        cipher = _get_cipher(iv)
        decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
        return decrypted.decode('utf-8')
    except Exception:
        return None


def sha256_hash(text):
    """SHA256哈希"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def md5_hash(text):
    """MD5哈希"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def generate_hmac(key, message):
    """生成HMAC签名"""
    return hmac.new(key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()


def verify_hmac(key, message, signature):
    """验证HMAC签名"""
    expected = generate_hmac(key, message)
    return hmac.compare_digest(expected, signature)


def generate_token(user_id, secret):
    """生成带签名的令牌"""
    timestamp = int(time.time())
    payload = f"{user_id}:{timestamp}"
    signature = generate_hmac(secret, payload)
    token_data = f"{payload}:{signature}"
    return base64.b64encode(token_data.encode('utf-8')).decode('utf-8')


def verify_token(token, secret, max_age=86400):
    """验证令牌"""
    try:
        token_data = base64.b64decode(token).decode('utf-8')
        parts = token_data.split(':')
        if len(parts) != 3:
            return None
        user_id, timestamp_str, signature = parts
        timestamp = int(timestamp_str)
        if time.time() - timestamp > max_age:
            return None
        payload = f"{user_id}:{timestamp_str}"
        if verify_hmac(secret, payload, signature):
            return int(user_id)
    except Exception:
        pass
    return None


def generate_card_key(prefix='SW'):
    """生成卡密 - 格式: XXXX-XXXX-XXXX-XXXX-XXXX"""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    segments = []
    for _ in range(5):
        segment = ''.join(random.choice(chars) for _ in range(4))
        segments.append(segment)
    raw_key = ''.join(segments)
    checksum = md5_hash(raw_key + AES_KEY.decode('utf-8', errors='ignore'))[:4].upper()
    full_key = f"{prefix}{raw_key}{checksum}"
    formatted = '-'.join([full_key[i:i+4] for i in range(0, len(full_key), 4)])
    return formatted


def verify_card_key_integrity(card_key):
    """验证卡密完整性（校验和验证）"""
    clean_key = card_key.replace('-', '').upper()
    if len(clean_key) < 28:
        return False
    raw_part = clean_key[2:22]
    checksum = clean_key[22:26]
    expected = md5_hash(raw_part + AES_KEY.decode('utf-8', errors='ignore'))[:4].upper()
    return checksum == expected


def encrypt_file_data(file_data):
    """加密文件数据"""
    iv = get_random_bytes(16)
    cipher = _get_cipher(iv)
    encrypted = cipher.encrypt(pad(file_data, AES.block_size))
    return iv + encrypted


def decrypt_file_data(encrypted_data):
    """解密文件数据"""
    try:
        iv = encrypted_data[:16]
        encrypted = encrypted_data[16:]
        cipher = _get_cipher(iv)
        return unpad(cipher.decrypt(encrypted), AES.block_size)
    except Exception:
        return None


def obfuscate_string(s):
    """简单字符串混淆"""
    result = []
    for i, c in enumerate(s):
        result.append(chr(ord(c) ^ (i % 256)))
    return base64.b64encode(''.join(result).encode('utf-8')).decode('utf-8')


def deobfuscate_string(obfuscated):
    """解混淆"""
    try:
        decoded = base64.b64decode(obfuscated).decode('utf-8')
        result = []
        for i, c in enumerate(decoded):
            result.append(chr(ord(c) ^ (i % 256)))
        return ''.join(result)
    except Exception:
        return None


def generate_license_key(machine_code, product_id):
    """根据机器码生成许可证密钥"""
    combined = f"{machine_code}:{product_id}:{AES_KEY.decode('utf-8', errors='ignore')}"
    license_hash = sha256_hash(combined)
    segments = [license_hash[i:i+4].upper() for i in range(0, 16, 4)]
    return '-'.join(segments)


def verify_license_key(machine_code, product_id, license_key):
    """验证许可证密钥"""
    expected = generate_license_key(machine_code, product_id)
    return expected == license_key.upper()