@echo off
chcp 65001 >nul
title 多市场订单簿重构工具

echo ====================================
echo  多市场订单簿重构工具 v2.0
echo  Python Web 服务版
echo ====================================
echo.

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.9+
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/2] 检查并安装依赖...
pip install fastapi "uvicorn[standard]" python-multipart "ccxt[pro]" --quiet
if errorlevel 1 (
    echo [警告] 部分依赖安装失败，加密货币功能可能不可用
    echo 可手动运行：pip install fastapi uvicorn python-multipart "ccxt[pro]"
)

echo [2/2] 启动服务...
echo.
echo  服务地址: http://localhost:8765
echo  浏览器将自动打开
echo.
echo  按 Ctrl+C 停止服务
echo ====================================

python server.py
pause

