#!/bin/bash
# 自动化创建 GitHub Release 的脚本
# 使用方法: bash scripts/create_release.sh <version>
# 示例: bash scripts/create_release.sh v1.1.0

set -e

VERSION=$1

if [ -z "$VERSION" ]; then
    echo "错误: 请提供版本号"
    echo "使用方法: bash scripts/create_release.sh <version>"
    echo "示例: bash scripts/create_release.sh v1.1.0"
    exit 1
fi

# 确保版本号以 v 开头
if [[ ! $VERSION == v* ]]; then
    VERSION="v$VERSION"
fi

echo "📦 准备创建 Release: $VERSION"

# 检查是否有未提交的更改
if [[ -n $(git status --porcelain) ]]; then
    echo "⚠️  警告: 有未提交的更改"
    read -p "是否继续? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 0
    fi
fi

# 获取最近的提交记录
COMMITS=$(git log --oneline -n 5)
DATE=$(date +%Y-%m-%d)

# 创建 Release 说明
NOTES="## Android Docker CLI $VERSION

发布日期: $DATE

### 变更日志
$COMMITS

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
\`\`\`bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/$VERSION/scripts/install.sh | sh
\`\`\`"

# 创建 tag
echo "🏷️  创建 tag: $VERSION"
git tag -a "$VERSION" -m "Release $VERSION"

# 推送 tag
echo "⬆️  推送 tag 到 GitHub"
git push origin "$VERSION"

# 创建 Release
echo "🚀 创建 GitHub Release"
gh release create "$VERSION" --title "$VERSION" --notes "$NOTES"

echo ""
echo "✅ Release 创建成功!"
echo "🔗 https://github.com/jinhan1414/android-docker-cli/releases/tag/$VERSION"
