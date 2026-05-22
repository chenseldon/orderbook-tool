@echo off
chcp 65001 >nul
title 多市场订单簿重构工具 - Python服务

echo ====================================
echo  多市场订单簿重构工具 Python后端
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

echo [1/3] 检查并安装依赖...
pip install fastapi "uvicorn[standard]" "websockets>=12.0" "ccxt[pro]" --quiet
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络或手动运行：
    echo   pip install fastapi uvicorn websockets "ccxt[pro]"
    pause
    exit /b 1
)

echo [2/3] 依赖安装完成
echo.
echo [3/3] 启动服务...
echo.
echo  WebSocket: ws://localhost:8765
echo  HTTP状态:  http://localhost:8766/status
echo.
echo  请在浏览器中打开 orderbook-tool.html
echo  在"实时数据接口"面板选择"本地Python服务"即可使用
echo.
echo  按 Ctrl+C 停止服务
echo ====================================

python server.py
pause
