# GitHub 发布与维护

仓库名称建议为 `label-editor`，公开源码；Windows 运行包放在 Releases 中。当前版本为 `v1.1.0`。

## 首次连接

安装 Git 与 [GitHub CLI](https://cli.github.com/)，在 PowerShell 中运行：

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

按提示在浏览器登录自己的 GitHub 账号，确认授权。不需要把密码或访问令牌发给其他人。插件连接和 CLI 登录是独立的授权通道；若插件缺少创建仓库或上传大文件的功能，使用 CLI 完成。

## 准备开发环境

使用 Windows 10 / 11 x64、Python 3.12，并确保系统有微软雅黑和 Arial（示例生成和相关测试使用这两种系统字体）。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
```

## 创建公开仓库并推送源码

在项目根目录执行下列命令。Git 姓名、邮箱按自己的账号设置；以下 `YOUR_ACCOUNT` 必须替换为实际 GitHub 账号。创建仓库前先确认同名仓库不存在。

```powershell
git init -b main
git add .
git commit -m "Release Label Editor 1.1.0"
gh repo create YOUR_ACCOUNT/label-editor --public --source . --remote origin --push --description "Windows PDF label editor with automatic original-font matching"
git tag v1.1.0
git push origin v1.1.0
```

`.gitignore` 排除了虚拟环境、构建产物、临时文件、工具目录与本地输出。提交前用 `git status` 查看文件清单，不要添加真实面单或账号凭据。

## 自动构建并发布

源码与版本标签推送后，在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/publish_release.ps1 -Repository YOUR_ACCOUNT/label-editor
```

脚本验证 GitHub 登录、干净的源码目录、版本号和远端标签对应的提交，然后运行测试、构建 Windows 程序、执行打包程序自检、制作 ZIP 和 SHA-256 校验文件，最后读取 `docs/releases/v1.1.0.md` 创建公开 Release 并上传附件。不会覆盖已有版本。

上传完成后，检查 Releases 页面能否下载 ZIP；完整解压到新目录运行 `LabelEditor.exe`。发布说明中的安装步骤、功能和限制均可直接供用户阅读。

若只想生成本地发行包：

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
.venv/Scripts/python.exe scripts/package_release.py
```

## 后续版本

修改 `label_editor/__init__.py` 中的版本号，更新 README、CHANGELOG 和对应的 `docs/releases/v版本号.md`。提交并推送源码，在同一提交上创建新版本标签并推送，然后再次运行发布脚本。当前脚本由维护者主动运行，不会在每次编辑文件后自动对外发布。

如果网络导致上传中断，先查看 GitHub 是否留下未完成草稿；确认附件情况后继续上传或处理草稿，不要重复创建或覆盖已发布的版本。

## 官方参考

- [浏览器授权登录](https://cli.github.com/manual/gh_auth_login)
- [创建仓库](https://cli.github.com/manual/gh_repo_create)
- [创建 Release 并上传附件](https://cli.github.com/manual/gh_release_create)
- [GitHub Release 管理](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
