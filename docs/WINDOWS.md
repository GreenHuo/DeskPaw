# DeskPaw Windows 版

## 使用

目标环境：Windows 10 / 11，x64。双击 `DeskPaw-Setup-x64.exe` 安装，完成后可从开始菜单运行，并能在 Windows“已安装的应用”中卸载。也可直接运行免安装的 `DeskPaw.exe`。两种方式都不需要安装 Python。

托盘爪印和宠物右键菜单都能打开宠物管理。支持任意位置拖放、窗口上沿自动吸附、全桌面小游戏、聊天和宠物性格设定。

设置、心情和位置保存在 `%APPDATA%\DeskPaw`，与程序文件分开；API Key 保存在当前用户的 Windows 凭据管理器，设置文件不包含密钥。自定义姓名、性格、背景和提示词会随聊天请求发送给选择的 AI 服务。

## 在 Windows 本地打包

1. 安装 Python 3.12 x64，安装时启用 Python Launcher；另需安装 [Inno Setup 6 或 7](https://jrsoftware.org/isinfo.php)。
2. 在项目目录打开 PowerShell，执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

脚本会创建 `.venv-win`、安装依赖、运行测试、生成单文件程序并检查启动，然后编译安装程序，在临时目录中实际安装、检查启动并卸载。启动检查还会让打包程序启动内置 Excel MCP 子进程，验证工具发现和中文表格读取，检查无控制台模式下的通信。

产物：

- `dist\DeskPaw-Setup-x64.exe`：当前用户安装程序，提供开始菜单入口、可选桌面快捷方式和卸载功能。
- `dist\DeskPaw.exe`：免安装的 Windows 可执行程序。
- `dist\DeskPaw-Windows-x64.zip`：程序与本说明。
- `dist\windows-self-test.json`：打包程序的启动检查报告。
- `dist\windows-installer-self-test.json`：安装后程序的启动检查报告。

应用图标、透明素材、Qt 运行库和窗口插件都包含在程序内。安装程序默认放在当前用户的 `%LOCALAPPDATA%\Programs\DeskPaw`，不要求管理员权限。配置与密钥分别留在 `%APPDATA%\DeskPaw` 和 Windows 凭据管理器，卸载时不会清除这些用户数据。安装程序目前未做代码签名，Windows 可能提示来源未知。

## 使用 GitHub Actions

项目包含 `.github/workflows/windows.yml`。推送到 `build/windows-*` 或 `codex/windows-*` 分支会自动构建；工作流进入主分支后，也可在仓库 Actions 页面选择 **Windows application → Run workflow**。完成后下载 **DeskPaw-Windows-x64** 产物，其中同时包含安装程序和免安装程序。工作流会在 Windows 2022 x64 环境中执行同一个打包脚本。

## 构建与验证边界

PyInstaller 的 Windows 程序需要在 Windows 环境构建，不能把 macOS 的产物改成 `.exe`。[PyInstaller 官方说明](https://pyinstaller.org/en/stable/usage.html)。安装程序由 [Inno Setup](https://jrsoftware.org/isinfo.php) 在同一 Windows 环境编译。

Windows 原生适配使用 [EnumWindows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows) 与 [DWM 窗口边界](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect)，并换算为 Qt 的显示器坐标；密钥使用 [Windows Credential Manager](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew)。

在 Windows 构建通过且打包程序启动检查成功前，不能把本机 macOS 的测试结果视为 Windows 原生运行验证。
