#!/bin/bash
# 监控面板快速启动脚本

cd "$(dirname "$0")"

echo "============================================================"
echo "🖥️  服务健康监控面板"
echo "============================================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3"
    exit 1
fi

# 检查依赖
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 启动
echo "🚀 启动监控服务..."
echo ""
python3 monitor_server.py
