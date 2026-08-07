"""百炼高代码应用云端部署入口。

包名必须是 deploy_starter：平台把启动命令固化为
  python3 /code/python/deploy_starter/main.py
（模板创建的应用不会重读我们 config.yml 里的 FC_RUN_CMD）。

host/端口只从同目录 config.yml 读取，**不要读环境变量**：
FC 运行时会注入 FC_SERVER_PORT=9000（FC 自定义运行时惯例），与平台
探活端口 8080 不一致，用了它会导致「health check failed on port 8080」
反复重启。官方 starter 的 main.py 也是只读 config.yml。

本地开发不走这个文件：双击「启动服务.bat」或
  uvicorn app.main:app --port 8321
"""
import os
import sys

# 云端运行时 /code/python 不一定在 sys.path（脚本目录是 deploy_starter/），
# 显式把安装根目录加进来，保证能 import app 包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import uvicorn  # noqa: E402


# 读取同目录 config.yml（与官方示例包相同的扁平 key: value 解析器）
def read_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    config = {}
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip("\"'")
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                config[key] = value
    return config


config = read_config()

HOST = config.get("FC_START_HOST", "0.0.0.0")
PORT = int(config.get("PORT", 8080))


def run_app():
    """setup.py console_scripts 入口；与直接 python main.py 等价。"""
    uvicorn.run("app.main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    run_app()
