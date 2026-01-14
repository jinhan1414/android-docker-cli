@echo off
REM Android权限修复测试运行脚本 (Windows)

echo ==========================================
echo Android权限修复 - 测试套件
echo ==========================================
echo.

REM 运行属性测试和单元测试
echo 1. 运行属性测试和单元测试...
python -m pytest tests/test_android_permissions.py -v

if %ERRORLEVEL% NEQ 0 (
    echo ❌ 属性测试失败
    exit /b 1
)

echo.
echo ✅ 所有属性测试通过
echo.

REM 运行集成测试（可选）
echo 2. 运行集成测试（可选）...
echo    注意：集成测试会拉取真实镜像，可能需要较长时间
set /p REPLY="   是否运行集成测试？(y/N) "

if /i "%REPLY%"=="y" (
    python -m pytest tests/test_android_integration.py -v -s
    
    if %ERRORLEVEL% NEQ 0 (
        echo ❌ 集成测试失败
        exit /b 1
    )
    
    echo.
    echo ✅ 所有集成测试通过
)

echo.
echo ==========================================
echo 测试完成！
echo ==========================================
