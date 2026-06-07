"""Travel Agent 入口文件"""
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

ENV_FILES = [PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"]
loaded_env_path = None
if load_dotenv is not None:
    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=True)
            loaded_env_path = env_file
            break

from web.app import create_app


def main():
    """主入口"""
    app = create_app()

    env_status = str(loaded_env_path) if loaded_env_path else "未找到 .env 文件"
    dashscope_status = "已配置" if os.environ.get("DASHSCOPE_API_KEY") else "未配置"

    # 获取端口
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    use_reloader = os.environ.get("FLASK_RELOAD", "false").lower() == "true"

    print(f"""
    ====================================
       小途 AI 旅行规划 Agent
       正在启动服务...
    ====================================

    环境文件: {env_status}
    DASHSCOPE_API_KEY: {dashscope_status}
    访问地址: http://127.0.0.1:{port}
    调试模式: {'开启' if debug else '关闭'}
    自动重载: {'开启' if use_reloader else '关闭'}

    按 Ctrl+C 停止服务
    """)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=use_reloader,
    )


if __name__ == "__main__":
    main()
