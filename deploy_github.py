# -*- coding: utf-8 -*-
# GitHub 仓库创建 + 代码上传脚本

import requests
import os
import json
import base64

import os
TOKEN = os.environ.get('GH_TOKEN', '')
REPO_NAME = 'ArcaneLib'
PROJECT_DIR = r'd:\.SOLO Csde\项目1\software-library'
PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
HEADERS = {
    'Authorization': 'Bearer ' + TOKEN,
    'Accept': 'application/vnd.github.v3+json'
}

# 需要上传的文件（排除不需要的）
EXCLUDE_DIRS = {'__pycache__', '.git', 'data', 'static/uploads'}
EXCLUDE_FILES = {'seed_data.py', 'tunnel.py', '.gitkeep', 'test_token.py', 'test_token2.py', 'test_token3.py', 'check_repo.py', 'ngrok.exe'}

def api_call(method, url, data=None):
    """调用 GitHub API"""
    if data:
        r = requests.request(method, url, headers=HEADERS, json=data, proxies=PROXIES, verify=False)
    else:
        r = requests.request(method, url, headers=HEADERS, proxies=PROXIES, verify=False)
    if r.status_code >= 400 and r.status_code != 404:
        print('  API错误:', r.status_code, r.text[:200])
    return r

# 1. 检查仓库是否已存在，不存在则创建
print('[*] 检查仓库 ' + REPO_NAME + '...')
r = api_call('GET', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME)
if r.status_code == 200:
    print('  ✅ 仓库已存在，直接上传...')
elif r.status_code == 404:
    print('  [*] 仓库不存在，尝试创建...')
    r = api_call('POST', 'https://api.github.com/user/repos', {
        'name': REPO_NAME,
        'description': 'Arcane库 - 软件库管理系统',
        'private': False,
        'auto_init': False
    })
    if r.status_code == 201:
        print('  ✅ 仓库创建成功')
    else:
        print('  ❌ 创建失败:', r.status_code, r.text[:200])
        exit(1)
else:
    print('  ❌ 检查仓库失败:', r.status_code, r.text[:200])
    exit(1)

# 获取仓库信息
repo_data = api_call('GET', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME).json()
default_branch = repo_data.get('default_branch', 'main')
print('  默认分支:', default_branch)

# 2. 获取所有需要上传的文件
def get_files(dir_path, base_path):
    files = []
    for root, dirs, filenames in os.walk(dir_path):
        # 跳过排除目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f in EXCLUDE_FILES:
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, base_path).replace('\\', '/')
            files.append((rel_path, full_path))
    return files

all_files = get_files(PROJECT_DIR, PROJECT_DIR)
print('  共 ' + str(len(all_files)) + ' 个文件')

# 3. 获取最新 commit 的 SHA（如果仓库不为空）
latest_sha = None
latest_tree_sha = None
r = api_call('GET', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/refs/heads/' + default_branch)
if r.status_code == 200:
    latest_sha = r.json()['object']['sha']
    # 获取对应的 tree SHA
    r_commit = api_call('GET', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/commits/' + latest_sha)
    if r_commit.status_code == 200:
        latest_tree_sha = r_commit.json()['tree']['sha']
    print('  仓库已有提交, SHA:', latest_sha[:8])
else:
    print('  仓库为空，通过 Contents API 创建初始提交...')
    init_content = base64.b64encode(b'Arcane Library\n').decode()
    r_init = requests.put(
        'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/contents/.gitkeep',
        headers=HEADERS,
        json={'message': 'Initial commit', 'content': init_content},
        proxies=PROXIES, verify=False
    )
    if r_init.status_code == 201:
        latest_sha = r_init.json()['commit']['sha']
        # 获取 tree SHA
        r_tree = api_call('GET', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/commits/' + latest_sha)
        if r_tree.status_code == 200:
            latest_tree_sha = r_tree.json()['tree']['sha']
        print('  初始提交创建成功, SHA:', latest_sha[:8])
    else:
        print('  ⚠️ 初始提交失败:', r_init.status_code, r_init.text[:200])
        exit(1)

# 4. 创建 Blob 和 Tree
blobs = []
for rel_path, full_path in all_files:
    with open(full_path, 'rb') as f:
        content = f.read()
    
    # 文本文件用 UTF-8 编码
    try:
        text = content.decode('utf-8')
        encoding = 'utf-8'
        content_b64 = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    except:
        encoding = 'base64'
        content_b64 = base64.b64encode(content).decode('utf-8')
    
    r = api_call('POST', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/blobs', {
        'content': content_b64,
        'encoding': 'base64'
    })
    
    if r.status_code == 201:
        blobs.append({
            'path': rel_path,
            'mode': '100644',
            'type': 'blob',
            'sha': r.json()['sha']
        })
        print('  📄 ' + rel_path)
    else:
        print('  ❌ 上传失败: ' + rel_path)

print('  已上传 ' + str(len(blobs)) + '/' + str(len(all_files)) + ' 个文件')

# 5. 创建 Tree
r = api_call('POST', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/trees', {
    'tree': blobs,
    'base_tree': latest_tree_sha
})

if r.status_code != 201:
    print('❌ Tree 创建失败:', r.status_code, r.text[:200])
    exit(1)

tree_sha = r.json()['sha']

# 6. 创建 Commit
commit_msg = '初始提交 - Arcane库 v1.0'
commit_data = {
    'message': commit_msg,
    'tree': tree_sha,
}
if latest_sha:
    commit_data['parents'] = [latest_sha]

r = api_call('POST', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/commits', commit_data)

if r.status_code != 201:
    print('❌ Commit 创建失败:', r.status_code, r.text[:200])
    exit(1)

commit_sha = r.json()['sha']
print('  ✅ Commit: ' + commit_sha[:8])

# 7. 更新分支引用
r = api_call('PATCH', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/refs/heads/' + default_branch, {
    'sha': commit_sha,
    'force': True
})

if r.status_code == 200:
    print('\n✅ 全部完成！')
    print('  仓库地址: https://github.com/xingyuanaaaa/' + REPO_NAME)
    print('  代码已成功推送到 GitHub！')
else:
    # 尝试创建分支
    r = api_call('POST', 'https://api.github.com/repos/xingyuanaaaa/' + REPO_NAME + '/git/refs', {
        'ref': 'refs/heads/' + default_branch,
        'sha': commit_sha
    })
    if r.status_code == 201:
        print('\n✅ 全部完成！')
        print('  仓库地址: https://github.com/xingyuanaaaa/' + REPO_NAME)
    else:
        print('❌ 分支更新失败:', r.status_code, r.text[:200])