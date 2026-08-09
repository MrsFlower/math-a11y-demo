"""一键生成测试用户交付包（zip）。

用法（在项目根目录 math-a11y-assistant 下）：
    python scripts\\make_user_package.py

产物：dist/公式助手_用户交付包_YYYYMMDD.zip，内容：
    公式助手/
      extension/               插件本体（安装时选这个文件夹）
      快速开始.txt             纯文本上手步骤（读屏友好）
      插件安装指引（读屏版）.md
      产品介绍与使用指南.md
      隐私政策.md
      测试反馈表.md

注意：测试用户非开发者，本机模式（启动服务.bat）不进包；
本机模式仅在云服务不可用时由开发者远程协助整包部署。
插件已内置云端地址与鉴权（sidepanel.js 的 DEFAULT_API/DEFAULT_TOKEN），开箱即用。
"""
from __future__ import annotations

import datetime
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# 随包文档：docs 下源文件名 -> 包内相对路径
DOC_FILES = {
    "插件安装指引（读屏版）.md": "docs/插件安装指引（读屏版）.md",
    "产品介绍与使用指南.md": "docs/产品介绍与使用指南.md",
    "隐私政策.md": "docs/隐私政策.md",
    "测试反馈表.md": "docs/测试反馈表.md",
}

QUICK_START = """数学公式无障碍学习助手 - 快速开始
================================

第 1 步：安装插件
  打开「插件安装指引（读屏版）.md」，按里面的按键步骤操作，
  大约 10 分钟，装一次长期可用。

第 2 步：无需配置，开箱即用
  插件默认已连好开发者的云服务，你电脑上不需要装任何环境，
  装完插件直接进第 3 步。（万一提示「无法连接理解服务」，
  焦点会落在「恢复默认云端服务」按钮上，按回车一键恢复；
  还不行就联系开发者）

第 3 步：用起来
  在任意网页选中一段含公式的文字，按 Ctrl+Shift+M，几秒后听到转译结果。
  更多玩法见「产品介绍与使用指南.md」。

第 4 步：用完之后
  打开「测试反馈表.md」，把问题和想法写进去发回给开发者，
  不方便打字也可以口头反馈。

遇到问题随时找开发者。
"""


def main() -> None:
    DIST.mkdir(exist_ok=True)
    stamp = datetime.date.today().strftime("%Y%m%d")
    zip_path = DIST / f"公式助手_用户交付包_{stamp}.zip"
    top = "公式助手"

    missing = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 插件本体
        ext_dir = ROOT / "extension"
        for p in sorted(ext_dir.rglob("*")):
            if p.is_file():
                zf.write(p, f"{top}/extension/{p.relative_to(ext_dir).as_posix()}")

        # 快速开始
        zf.writestr(f"{top}/快速开始.txt", QUICK_START)

        # 文档
        for out_name, rel in DOC_FILES.items():
            src = ROOT / rel
            if src.exists():
                zf.write(src, f"{top}/{out_name}")
            else:
                missing.append(rel)

    size_kb = zip_path.stat().st_size / 1024
    print(f"已生成：{zip_path}（{size_kb:.0f} KB）")
    if missing:
        print("警告：以下文件缺失，未打入包内：")
        for m in missing:
            print("  -", m)


if __name__ == "__main__":
    main()
