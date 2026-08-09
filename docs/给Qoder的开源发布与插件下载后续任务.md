# 给 Qoder 的开源发布与插件下载后续任务

日期：2026-08-09

## 一、当前发布状态

代码和展示页已经推到同一个 GitHub 仓库：

- 仓库：`https://github.com/MrsFlower/math-a11y-demo`
- 代码分支：`main`
  - 当前提交：`03543af Checkpoint Qoder demo and plugin updates`
  - 含完整工程代码与此前本地提交历史。
- 展示分支：`gh-pages`
  - 当前基础提交：`9504f7c Publish GitHub Pages demo`
  - 后续我已追加“插件体验包下载入口”，见下一节。
- GitHub Pages 地址：
  - 首页：`https://mrsflower.github.io/math-a11y-demo/`
  - Demo：`https://mrsflower.github.io/math-a11y-demo/demo.html`

## 二、我刚做的新增工作

为了让评委/用户“体验网页的同时能直接下载插件”，我做了以下调整：

1. 用 `python scripts\make_user_package.py` 重新生成当前版本用户交付包。
2. 将生成包复制到 `gh_pages_upload\math-a11y-extension-user-package-20260809.zip`。
3. 在 Pages 首页 `index.html` 增加“下载浏览器插件体验包”按钮。
4. 在 Demo 页 `demo.html` 底部增加同一个下载链接。
5. 在 Pages 仓库 `README.md` 增加下载说明。
6. 检查 zip 内容：只包含 `extension/`、快速开始、读屏版安装指引、产品介绍、隐私政策、测试反馈表；不含 `app/`、`.env`、`photo/`、`dist/`、`build/`。

压缩包内文件数为 15 个，大小约 61 KB。

## 三、你接下来需要继续完善的事项

### 1. 把 Pages 新增下载入口提交并推送

在目录 `C:\Users\15866\Documents\codeheaven\小程序大赛\gh_pages_upload` 下检查：

```powershell
git status --short
```

应看到：

```text
 M README.md
 M demo.html
 M index.html
?? math-a11y-extension-user-package-20260809.zip
```

提交并推送：

```powershell
git add README.md demo.html index.html math-a11y-extension-user-package-20260809.zip
git commit -m "Add browser extension download to Pages"
git -c http.sslBackend=openssl push
```

推送后验证：

```powershell
curl.exe -k -L -sS -o NUL -w "%{http_code}" https://mrsflower.github.io/math-a11y-demo/
curl.exe -k -L -sS -o NUL -w "%{http_code}" https://mrsflower.github.io/math-a11y-demo/demo.html
curl.exe -k -L -sS -o NUL -w "%{http_code}" https://mrsflower.github.io/math-a11y-demo/math-a11y-extension-user-package-20260809.zip
```

三者都应为 `200`。

### 2. 页面和下载包体验复核

请用浏览器打开首页，确认：

- “立即体验网页版”能进入 `demo.html`。
- “下载浏览器插件体验包”能下载 zip，而不是打开乱码页。
- 下载包解压后目录结构为 `公式助手/extension/...`，安装时选择 `extension` 目录。
- Chrome/Edge 开发者模式加载该插件后，侧边栏可打开。
- 选中测试网页里的公式后，用 `Ctrl+Shift+M` 能触发插件。

### 3. 插件包版本与命名需要后续规范化

当前文件名包含日期：`math-a11y-extension-user-package-20260809.zip`。

后续建议改成同时带插件版本号，例如：

`math-a11y-extension-v0.7.5-20260809.zip`

这样页面、录屏、反馈表里的版本能对应上。若改名，需要同步改 `index.html`、`demo.html`、`README.md` 三处链接。

### 4. 开源仓库风险复核

当前开源仓库没有发现真实 `.env` 或百炼 `sk-...` 密钥，但完整历史会公开：

- 云端 API 地址；
- 客户端共享 Bearer token；
- 内部交付文档；
- 录屏和诊断脚本。

这是为了保留此前 commit 历史做出的选择。若比赛后要长期公开维护，建议另起一个“clean public”分支或新仓库，做一次正式开源清洗：

- 移除内部文档，如 `docs\交付待办.md`、录屏准备类文档、Qoder/Codex 交接类文档；
- 移除 `_diag_*.py`、`_rec_*.py` 等一次性脚本；
- 将云端 token 改为用户配置项或临时体验 token；
- 补 LICENSE；
- 重写 README，让它面向外部开发者，而不是比赛内部交付。

## 四、继续产品完善的重点

下一步不要只修单个 bug。现在已经进入“公开体验”阶段，重点应放在完整闭环：

1. 用户从 Pages 进入项目；
2. 先用网页版看到核心能力；
3. 下载插件体验包；
4. 按读屏版安装指引加载插件；
5. 在任意网页选中公式；
6. 快捷键触发；
7. 听到明确反馈、转译结果和兜底路径；
8. 失败时知道下一步该怎么办。

请优先检查这个闭环里每一步的提示文本、焦点位置、错误反馈和安装门槛，而不是继续堆更多功能按钮。
