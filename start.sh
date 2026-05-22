#!/bin/bash
echo "===================================="
echo " 多市场订单簿重构工具 Python后端"
echo "===================================="

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到python3，请先安装Python 3.9+"
    exit 1
fi

echo "[1/3] 安装依赖..."
pip3 install fastapi "uvicorn[standard]" "websockets>=12.0" "ccxt[pro]" -q

echo "[2/3] 依赖安装完成"
echo "[3/3] 启动服务..."
echo ""
echo " WebSocket: ws://localhost:8765"
echo " HTTP状态:  http://localhost:8766/status"
echo ""
echo " 请在浏览器中打开 orderbook-tool.html"
echo " 按 Ctrl+C 停止服务"
echo "===================================="

python3 server.py
