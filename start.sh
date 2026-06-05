#!/bin/bash
# Travel Agent 启动脚本

echo "===================================="
echo "   小途 AI 旅行规划 Agent"
echo "===================================="
echo ""

# 检查Python
if ! command -v python &> /dev/null; then
    echo "错误: 未找到Python，请先安装Python 3.11+"
    exit 1
fi

# 设置环境变量
export FLASK_APP=web.app
export FLASK_DEBUG=true

# 检查依赖
echo "正在检查依赖..."
if ! pip show flask &> /dev/null; then
    echo "正在安装依赖..."
    pip install -r requirements_agent.txt
fi

# 启动服务
echo ""
echo "正在启动服务..."
echo "访问地址: http://127.0.0.1:5000"
echo ""
python main.py
