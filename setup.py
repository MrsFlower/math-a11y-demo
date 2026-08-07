"""百炼高代码应用打包脚本（结构对齐官方 modelstudio-agent-starter 示例包）。

打包：在本文件所在目录执行  python setup.py bdist_wheel
产物：dist/*.whl，上传到百炼控制台或 runtime-fc-deploy 部署。
"""
import os
import uuid

from setuptools import find_packages, setup

# 读取 requirements.txt 中的依赖（过滤注释与空行）
with open("requirements.txt", encoding="utf-8") as f:
    requirements = [
        line.strip()
        for line in f
        if line.strip() and not line.strip().startswith("#")
    ]


# 读取 deploy_starter/config.yml（与官方示例包相同的扁平 key: value 结构）
def read_config():
    config_path = os.path.join(os.path.dirname(__file__), "deploy_starter", "config.yml")
    config = {}
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if ":" in line:
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

setup_package_name = config.get("SETUP_PACKAGE_NAME", "app")
setup_module_name = config.get("SETUP_MODULE_NAME", "main")
setup_function_name = config.get("SETUP_FUNCTION_NAME", "run_app")
setup_command_name = config.get("SETUP_COMMAND_NAME", "math-a11y-assistant")

# 生成带 UUID 的包名（与官方示例一致，避免平台侧同名冲突）
base_name = config.get("SETUP_NAME", "math-a11y-assistant")
unique_name = f"{base_name}-{uuid.uuid4().hex[:8]}"

# app 及其全部子包（parser/knowledge 等，find_packages 自动发现，避免漏打包）；
# app.static 单独用 package_dir 映射到根目录 static/；
# deploy_starter 是云端部署入口包（平台固化启动命令指向它，包名不可改）
_packages = find_packages(include=["app", "app.*"])

setup(
    name=unique_name,
    version=config.get("SETUP_VERSION", "0.1.0"),
    description=config.get("SETUP_DESCRIPTION", "math-a11y-assistant"),
    long_description=config.get(
        "SETUP_LONG_DESCRIPTION",
        "数学公式无障碍学习助手后端（FastAPI）",
    ),
    packages=_packages + ["deploy_starter", f"{setup_package_name}.static"],
    package_dir={f"{setup_package_name}.static": "static"},
    install_requires=requirements,
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            f"{setup_command_name}=deploy_starter.{setup_module_name}:{setup_function_name}",
        ],
    },
    include_package_data=True,
    package_data={
        "deploy_starter": ["config.yml"],
        f"{setup_package_name}.static": ["*.html"],
    },
)
