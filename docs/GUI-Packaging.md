# MaaAssistPCR GUI 开发包

Windows x64 开发包含公会战打轴、GUI 冒烟测试和标题画面 OCR 点击演示。开发包固定使用 MFAAvalonia **v2.16.4** 和 MaaFramework **v5.16.1**。公会战操作详见 [战斗轴](./Battle-Timeline.md)。

## 启动和验证

1. 安装 Windows x64 版 [.NET 10 Runtime](https://dotnet.microsoft.com/download/dotnet/10.0)，完整解压开发包并运行 `MFAAvalonia.exe`。
2. 确认窗口显示 **MaaAssistPCR**，任务列表有 **GUI 冒烟测试（不操作游戏）**。不要单独把 EXE 移出目录。
3. 若要验证任务调度，打开带 ADB 的模拟器，或连接已授权的 Android 设备。在 GUI 里选择 **安卓（ADB）** 和设备，再勾选并运行冒烟任务。预期任务成功结束，不启动游戏、不点按设备、不运行 OCR。没有 ADB 设备时，只能验证界面加载。

## OCR 演示：点击开始游戏

1. 在 16:9 横屏模拟器里手动打开《公主连结》，停在显示「点击屏幕 开始游戏」的标题页。
2. 在 GUI 中连接该 ADB 设备，只勾选 **OCR 演示：点击开始游戏** 并运行。该任务默认不勾选。
3. 命中后点击文字框内一次，任务结束。若约 5 秒内未命中，任务以失败结束，不点击，也不会接管后续登录流程。

演示为纯 Pipeline：`TitleOcrDemo` 等待 `TitleOcrClick` 命中。控制器将截图短边缩放到 720；在 1280×720 的参考画面下，OCR 仅在底部中央的 `[460, 632, 360, 69]` 检测完整目标文字，允许两段之间没有空格。`Click` 的 `target: true` 使用此次 OCR 得到的实际文字框，而不是固定点击坐标。其他画面比例或标题页样式未验证。

## 从源码组装

在 Windows x64 上准备 Python 3.12 和 `curl.exe`，在仓库根目录运行：

```powershell
python -m pip install -r requirements-dev.txt
python .\install.py
```

输出在 `install/MaaAssistPCR-win-x64/`。脚本从官方发布下载 ZIP 到 `deps/`，下载过的文件会复用；每次都校验 SHA-256。若缓存文件损坏，移走该文件再重试。脚本不会覆盖既有输出；需要并排保留旧包时可指定新目录：

```powershell
python .\install.py --output .\install\MaaAssistPCR-win-x64-test
```

包根目录放置 `interface.json`（Project Interface V2）和 `resource/`；`runtimes/win-x64/native/` 使用独立 MaaFramework 发布包的 DLL，不混用 GUI 自带的旧原生库。构建自动下载并校验 MaaCommonAssets 的 PP-OCRv5 简体中文模型（`det.onnx`、`rec.onnx`、`keys.txt`），存放在包内的 `resource/model/ocr/`。构建也用 PyInstaller 打包战斗用的 Python Agent 和 Tk 编辑器，使用者可以从 MFAAvalonia 打开编辑器。旧 B 服启动原型归档到 `docs/legacy/bilibili-startup.json`，不会被加载。

## CI 与开发者检查

GitHub Actions 的 **GUI development package** 工作流只产出 `MaaAssistPCR-win-x64-dev` 测试产物，可手动触发；不发布 GitHub Release。验证程序从打包目录加载原生库，核对和 `requirements-dev.txt` 的版本一致，再通过无设备控制器检查冒烟任务无输入、OCR 命中只点击一次文字框、近似文字未命中不点击。CI 用合成图，不包含用户的游戏截图，也不能替代真实 ADB 验证。

如需在本地复跑打包检查，先按项目的 MaaFramework 开发环境准备 `.venv`，再执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

使用自定义输出时，将 `MAA_GUI_PACKAGE` 设为实际输出目录。如需额外回归本次用户提供的完整标题截图，将 `MAA_TITLE_SCREENSHOT` 设为本地原截图路径再运行同一命令；不要提交含玩家 ID 的截图。升级依赖时，同步修改 `install.py` 中的版本和校验值；升级 MaaFramework 时也更新 `requirements-dev.txt`，再重跑检查。

## 上游组件

上游许可随包放在 `licenses/`，Android 辅助程序的许可在 `MaaAgentBinary/`。对应版本源码：[MFAAvalonia v2.16.4](https://github.com/MaaXYZ/MFAAvalonia/tree/v2.16.4)、[MaaFramework v5.16.1](https://github.com/MaaXYZ/MaaFramework/tree/v5.16.1)。

OCR 模型来自 [MaaCommonAssets 固定提交的 PP-OCRv5 简体中文目录](https://github.com/MaaXYZ/MaaCommonAssets/tree/dabcd4681ac990dc4361de26416d986abd80e4aa/OCR/ppocr_v5/zh_cn)，包内附 MaaCommonAssets 和 PaddleOCR 许可证。
