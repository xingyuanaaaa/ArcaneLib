# -*- coding: utf-8 -*-
# 软件库系统 - 启动脚本

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

if __name__ == '__main__':
    print("=" * 60)
    print("  软件库系统 v1.0")
    print("  手机端 + 电脑端 通用后端服务")
    print("=" * 60)
    print(f"  前端访问: http://127.0.0.1:5000")
    print(f"  管理后台: http://127.0.0.1:5000/admin")
    print(f"  API接口: http://127.0.0.1:5000/api")
    print(f"  默认管理员: admin / admin123456")
    print("=" * 60)

    # 使用waitress作为生产服务器（Windows友好）
    try:
        from waitress import serve
        print("  使用 Waitress 生产服务器启动...")
        serve(app, host='0.0.0.0', port=5000, threads=8)
    except ImportError:
        print("  使用 Flask 开发服务器启动...")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)