#!/bin/bash
echo "===================================="
echo " 多市场订单簿重构工具 v2.0"
echo " Python Web 服务版"
echo "===================================="

if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到python3，请先安装Python 3.9+"
    exit 1
fi

echo "[1/2] 安装依赖..."
pip3 install fastapi "uvicorn[standard]" python-multipart "ccxt[pro]" -q

echo "[2/2] 启动服务..."
echo ""
echo " 服务地址: http://localhost:8765"
echo " 浏览器将自动打开"
echo " 按 Ctrl+C 停止服务"
echo "===================================="

python3 server.py
