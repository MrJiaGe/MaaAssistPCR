# MaaFramework 开发环境

本项目固定使用 MaaFramework **v5.16.1**。Python 开发依赖以 [`requirements-dev.txt`](../requirements-dev.txt) 为准，本地和资源检查 CI 使用同一个文件。

## 本地资源检查（Windows x64）

准备 Python 3.12，在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -c "from maa.library import Library; print(Library.version())"
.\.venv\Scripts\python.exe .\check_resource.py .\assets\resource
```

应输出 `v5.16.1`，资源检查应以 `All directories checked.` 结束。此检查加载资源包和 Pipeline，不启动游戏，不验证 OCR 推理或实际点击。

## 原生运行包

从 [v5.16.1 官方发布页](https://github.com/MaaXYZ/MaaFramework/releases/tag/v5.16.1) 下载 `MAA-win-x86_64-v5.16.1.zip`。使用 `Get-FileHash -Algorithm SHA256` 确认校验值为 `19588e6fda8d977496eb143cce157ce0c21890bee62aef8fdf1696930fe1286e`，再解压到 `deps/`。确认 `deps/bin/MaaFramework.dll` 和 `deps/share/MaaAgentBinary/` 存在。不要把新版解压覆盖旧版，也不要提交 `deps/`、`.venv/` 或安装输出。

执行 `configure.py` 或 `install.py` 前，需通过 `git submodule update --init --recursive` 准备仓库锁定的 `assets/MaaCommonAssets`，并确认 `assets/MaaCommonAssets/OCR` 存在。MaaPiCli 是独立客户端，不包含在此版本的原生运行包中。旧项目入口和客户端的端到端联调不属于上述资源检查。

以后升级时，同步更新 `requirements-dev.txt` 和本文记录的发布包版本、校验值，并重新运行资源检查。
