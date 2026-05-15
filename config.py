# -*- coding: utf-8 -*-
# 软件库系统 - 配置文件
import os
import secrets

# 基础路径
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 密钥配置 - 生产环境请务必修改这些密钥
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', secrets.token_hex(32))

# AES加密密钥 - 32字节用于AES-256
AES_KEY = os.environ.get('AES_KEY', secrets.token_hex(16)).encode('utf-8')[:32].ljust(32, b'\x00')

# 数据库配置
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'software_library.db')

# 文件上传配置
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
SOFTWARE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'software')
IMAGE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'images')
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 最大上传500MB
ALLOWED_SOFTWARE_EXTENSIONS = {'zip', 'rar', '7z', 'exe', 'msi', 'apk', 'dmg', 'tar', 'gz'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'ico'}

# 卡密配置
CARD_KEY_LENGTH = 20  # 卡密长度
CARD_KEY_SEGMENT_LENGTH = 4  # 每段长度

# 机器码配置
MACHINE_CODE_SALT = os.environ.get('MACHINE_SALT', secrets.token_hex(8))

# 会话配置
SESSION_COOKIE_SECURE = False  # 生产环境设为True(需要HTTPS)
SESSION_COOKIE_HTTPONLY = True
PERMANENT_SESSION_LIFETIME = 86400 * 7  # 7天

# 管理员配置
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = None  # 首次运行时自动创建

# 分页配置
ITEMS_PER_PAGE = 20

# 日志配置
LOG_LEVEL = 'INFO'
LOG_FILE = os.path.join(BASE_DIR, 'data', 'app.log')