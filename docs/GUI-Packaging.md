# MaaAssistPCR GUI 开发包

当前只提供 Windows x64 的 GUI 基础验证。开发包固定使用 MFAAvalonia **v2.16.4** 和 MaaFramework **v5.16.1**，不包含可用的公会战或登录任务。

## 启动和验证

1. 安装 Windows x64 版 [.NET 10 Runtime](https://dotnet.microsoft.com/download/dotnet/10.0)，完整解压开发包并运行 `MFAAvalonia.exe`。
2. 确认窗口显示 **MaaAssistPCR**，任务列表有 **GUI 冒烟测试（不操作游戏）**。不要单独把 EXE 移出目录。
3. 若要验证任务调度，打开带 ADB 的模拟器，或连接已授权的 Android 设备。在 GUI 里选择 **安卓（ADB）** 和设备，再勾选并运行冒烟任务。预期任务成功结束，不启动游戏、不点按设备、不运行 OCR。没有 ADB 设备时，只能验证界面加载。

## 从源码组装

在 Windows x64 上准备 Python 3.12 和 `curl.exe`，在仓库根目录运行：

```powershell
python .\install.py
```

输出在 `install/MaaAssistPCR-win-x64/`。脚本从官方发布下载 ZIP 到 `deps/`，下载过的文件会复用；每次都校验 SHA-256。若缓存文件损坏，移走该文件再重试。脚本不会覆盖既有输出；需要并排保留旧包时可指定新目录：

```powershell
python .\install.py --output .\install\MaaAssistPCR-win-x64-test
```

包根目录放置 `interface.json`（Project Interface V2）和 `resource/`；`runtimes/win-x64/native/` 使用独立 MaaFramework 发布包的 DLL，不混用 GUI 自带的旧原生库。构建不需要 OCR 子模块，也不打包模板的 Python Agent。旧 B 服启动原型归档到 `docs/legacy/bilibili-startup.json`，不会被加载。

## CI 与开发者检查

GitHub Actions 的 **GUI development package** 工作流只产出 `MaaAssistPCR-win-x64-dev` 测试产物，可手动触发；不发布 GitHub Release。验证程序从打包目录加载原生库，核对和 `requirements-dev.txt` 的版本一致，再通过无设备控制器读取资源和运行冒烟任务。它不替代在 GUI 内连接 ADB 的实际测试。

如需在本地复跑打包检查，先按项目的 MaaFramework 开发环境准备 `.venv`，再执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_gui_smoke.py
```

使用自定义输出时，将 `MAA_GUI_PACKAGE` 设为实际输出目录。升级依赖时，同步修改 `install.py` 中的版本和校验值；升级 MaaFramework 时也更新 `requirements-dev.txt`，再重跑检查。

## 上游组件

上游许可随包放在 `licenses/`，Android 辅助程序的许可在 `MaaAgentBinary/`。对应版本源码：[MFAAvalonia v2.16.4](https://github.com/MaaXYZ/MFAAvalonia/tree/v2.16.4)、[MaaFramework v5.16.1](https://github.com/MaaXYZ/MaaFramework/tree/v5.16.1)。
