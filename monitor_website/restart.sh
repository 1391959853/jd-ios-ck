#!/bin/bash
# 监控面板 - 重启脚本

cd /home/zxj/jd-ios-ck/monitor_website

# 停止旧进程
pkill -f "python3 monitor_server.py" 2>/dev/null
sleep 1

# 启动新进程
nohup python3 monitor_server.py > monitor.log 2>&1 &

echo "✅ 服务已启动"
echo "访问地址：http://127.0.0.1:5000"
echo ""
echo "日志：tail -f monitor.log"
