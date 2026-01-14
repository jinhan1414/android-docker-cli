#!/bin/bash

# Android权限修复测试运行脚本

echo "=========================================="
echo "Android权限修复 - 测试套件"
echo "=========================================="
echo ""

# 运行属性测试和单元测试
echo "1. 运行属性测试和单元测试..."
python -m pytest tests/test_android_permissions.py -v

if [ $? -ne 0 ]; then
    echo "❌ 属性测试失败"
    exit 1
fi

echo ""
echo "✅ 所有属性测试通过"
echo ""

# 运行集成测试（可选，因为需要实际拉取镜像）
echo "2. 运行集成测试（可选）..."
echo "   注意：集成测试会拉取真实镜像，可能需要较长时间"
read -p "   是否运行集成测试？(y/N) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    python -m pytest tests/test_android_integration.py -v -s
    
    if [ $? -ne 0 ]; then
        echo "❌ 集成测试失败"
        exit 1
    fi
    
    echo ""
    echo "✅ 所有集成测试通过"
fi

echo ""
echo "=========================================="
echo "测试完成！"
echo "=========================================="
