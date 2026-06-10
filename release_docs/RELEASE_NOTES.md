# WeChat Chat Summarizer 0.10.0

发布日期：2026-06-10

本项目已按 MIT License 开源。

## 主要功能

- 文本文件和可选微信会话摘要。
- DeepSeek V4 Pro、GPT-5.5 与本地规则摘要引擎。
- Markdown 阅读视图、源码视图、复制和导出。
- 日期、成员、编码和摘录数量筛选。
- DeepSeek Key 与 OpenAI Key 分别使用 Windows DPAPI 加密保存。
- GPT-5.5 Responses API、Strict Structured Outputs 和独立推理深度。
- DeepSeek/GPT 统一结构化摘要、长聊天自动分块、递归合并与原文证据编号。
- DeepSeek 空分歧字段可恢复处理，避免单个空占位项导致整份摘要失败。
- Markdown、TXT、JSON 三种真实导出格式。
- 单次生成后三格式即时切换，以及自定义基础名称的全部导出。
- 摘要章节顺序优化，主要参与者紧跟总体概览。
- 阅读预览增加与界面风格一致的细纵向滚动条。
- 微信会话搜索、连接测试和未识别行诊断。

## 已知限制

- 仅支持 64 位 Windows 10/11。
- 本试用版未进行代码签名，首次运行可能显示未知发布者。
- 微信会话直读需要用户自行安装并初始化 `wechat-cli`。
- AI 摘要仅供辅助阅读，不能替代对原始记录的核验。
- 如果只想运行 Windows 程序，请下载正式 Windows ZIP；GitHub 自动生成的 Source code 压缩包是源码包。
