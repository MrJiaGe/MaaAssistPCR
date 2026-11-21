# MaaAssistPCR

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 的《公主连结》公会战打轴工具。开发版支持图形化编辑战斗轴、按槽位检测 UB 后调整 SET，以及标题画面 OCR 点击。

- [公会战打轴](./docs/Battle-Timeline.md)
- [GUI 开发包](./docs/GUI-Packaging.md)：Windows x64 本地打包、GitHub Actions 产物和 OCR 演示。
- [MaaFramework 开发环境](./docs/MaaFramework.md)：安装固定版本的开发依赖、检查 Pipeline 资源。
- [旧 B 服启动原型](./docs/legacy/bilibili-startup.json)：仅供参考，不随开发包加载。

GUI 开发包会自动拉取和校验固定版本的简体中文 OCR 模型，不需要初始化子模块。
