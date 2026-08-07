# 本目录同时是 app.static 子包（setup.py 用 package_dir 映射），
# 让静态页随 wheel 打包上云（百炼高代码部署只安装 Python 包）。
# 运行期 app/main.py 的 STATIC_DIR 优先用本目录（本地开发），
# 云端则从安装目录的 app/static 回退读取。
