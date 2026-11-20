# MaaAssistPCR

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 的《公主连结》公会战打轴工具。目前处于基础设施验证阶段，尚未实现打轴功能。

- [GUI 开发包](./docs/GUI-Packaging.md)：Windows x64 本地打包、GitHub Actions 产物和冒烟测试。
- [MaaFramework 开发环境](./docs/MaaFramework.md)：安装固定版本的开发依赖、检查 Pipeline 资源。
- [旧 B 服启动原型](./docs/legacy/bilibili-startup.json)：仅供参考，不随开发包加载。

GUI 开发包不依赖 OCR 子模块。后续开发需要 OCR 时，再初始化 `assets/MaaCommonAssets` 并运行 `configure.py`。
