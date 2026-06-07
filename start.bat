@echo off
REM Travel Agent 启动脚本

echo ====================================
echo    小途 AI 旅行规划 Agent
echo ====================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.11+
    pause
    exit /b 1
)

REM 设置环境变量
set FLASK_APP=web.app
set FLASK_DEBUG=true

REM 检查依赖
echo 正在检查依赖...
pip show flask >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖...
    pip install -r requirements_agent.txt
)

REM 启动服务
echo.
echo 正在启动服务...
echo 访问地址: http://127.0.0.1:5000
echo.
python main.py

pause
