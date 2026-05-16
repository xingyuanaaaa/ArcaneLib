# -*- coding: utf-8 -*-
# Railway 启动脚本 - 读取 PORT 环境变量启动 gunicorn
import os
import subprocess
import sys

port = os.environ.get('PORT', '5000')
bind = f'0.0.0.0:{port}'

subprocess.call([
    sys.executable, '-m', 'gunicorn',
    'app:app',
    '--bind', bind,
    '--workers', '2',
    '--threads', '4',
    '--timeout', '120'
])