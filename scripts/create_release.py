#!/usr/bin/env python3
"""
自动化创建 GitHub Release 的脚本
使用方法: python scripts/create_release.py <version> [--notes "release notes"]
示例: python scripts/create_release.py v1.1.0
"""

import subprocess
import sys
import argparse
from datetime import datetime


def run_command(cmd, check=True):
    """执行命令并返回输出"""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    if check and result.returncode != 0:
        print(f"错误: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def get_recent_commits(count=5):
    """获取最近的提交记录"""
    commits = run_command(f"git log --oneline -n {count}")
    return commits


def create_release_notes(version, custom_notes=None):
    """生成 Release 说明"""
    if custom_notes:
        return custom_notes
    
    commits = get_recent_commits()
    date = datetime.now().strftime("%Y-%m-%d")
    
    notes = f"""## Android Docker CLI {version}

发布日期: {date}

### 变更日志
{commits}

### 主要功能
- ✅ Docker 镜像拉取和缓存
- ✅ 容器生命周期管理（run, start, stop, restart, rm）
- ✅ Docker Compose 支持
- ✅ 持久化容器文件系统
- ✅ 私有仓库认证支持
- ✅ 卷挂载和环境变量注入

### 支持环境
- Android Termux
- Linux (Ubuntu/Debian)

### 安装方式
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/{version}/scripts/install.sh | sh
```
"""
    return notes


def main():
    parser = argparse.ArgumentParser(description='自动创建 GitHub Release')
    parser.add_argument('version', help='版本号 (例如: v1.1.0)')
    parser.add_argument('--notes', help='自定义 Release 说明', default=None)
    parser.add_argument('--draft', action='store_true', help='创建草稿 Release')
    parser.add_argument('--prerelease', action='store_true', help='标记为预发布版本')
    
    args = parser.parse_args()
    version = args.version
    
    # 确保版本号格式正确
    if not version.startswith('v'):
        version = f'v{version}'
    
    print(f"📦 准备创建 Release: {version}")
    
    # 检查是否有未提交的更改
    status = run_command("git status --porcelain", check=False)
    if status:
        print("⚠️  警告: 有未提交的更改")
        response = input("是否继续? (y/n): ")
        if response.lower() != 'y':
            print("已取消")
            sys.exit(0)
    
    # 创建 tag
    print(f"🏷️  创建 tag: {version}")
    run_command(f'git tag -a {version} -m "Release {version}"')
    
    # 推送 tag
    print(f"⬆️  推送 tag 到 GitHub")
    run_command(f'git push origin {version}')
    
    # 生成 Release 说明
    notes = create_release_notes(version, args.notes)
    
    # 创建 Release
    print(f"🚀 创建 GitHub Release")
    
    cmd = f'gh release create {version} --title "{version}" --notes "{notes}"'
    
    if args.draft:
        cmd += ' --draft'
    if args.prerelease:
        cmd += ' --prerelease'
    
    release_url = run_command(cmd)
    
    print(f"\n✅ Release 创建成功!")
    print(f"🔗 {release_url}")


if __name__ == '__main__':
    main()
