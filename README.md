# 微信聊天摘要工具 0.9.0

vibe coding试水作

一个 MIT 开源的本地运行微信聊天记录摘要桌面工具。桌面版默认使用 DeepSeek API 生成中文摘要，也可以切换到 `local` 模式只在本机处理聊天内容。

如果只想运行 Windows 程序，请在 GitHub Release 中下载 `WeChatChatSummarizer-0.9.0-win64.zip`。GitHub 自动生成的 Source code 压缩包是源码包，不包含已打包好的 EXE。

## 功能

- 自动识别 `utf-8-sig`、`utf-8`、`gb18030`、`utf-16` 等常见文本编码
- 解析多种常见聊天文本格式
- 合并同一条消息的多行内容
- 统计消息数量、时间范围、活跃成员
- 按日期生成时间线
- 提取高频主题词
- 识别待办/跟进、问题、决定/结论、风险/阻塞
- 按“聊天时间范围、参与人物、主要事件、核心摘要、原文依据”生成报告
- 输出 Markdown 或 JSON 摘要报告
- 支持按日期和成员筛选
- 可选接入 DeepSeek API 生成自然语言摘要
- 可选接入 `wechat-cli`，直接从本机微信会话导出指定条数后总结

## 开源许可

本项目使用 MIT License 开源，详见 `LICENSE`。

## 支持的输入格式

推荐先把微信聊天记录整理或导出为文本文件。当前支持这几类行格式：

```text
2026-06-01 09:12:03 张三: 今天把需求文档发我一下
[2026/06/01 10:20] 王五：会议改到明天上午
李四 2026年6月1日 11:00:00 我来确认，今晚前给结论
2026-06-01 12:00:00 | 赵六 | 接口字段采用 version 和 status
```

同一条消息的后续换行会被当作上一条消息的内容继续合并。

## 使用

### 桌面界面

如果使用已经打包好的单文件程序，先从 GitHub Release 下载并解压 `WeChatChatSummarizer-0.9.0-win64.zip`，然后双击运行：

```text
WeChatChatSummarizer.exe
```

单文件程序会直接打开桌面窗口，不会启动浏览器，也不会弹出终端窗口。

如果使用源码或便携版目录，双击运行：

```text
run_app.bat
```

从终端启动桌面版：

```powershell
python wxchat_desktop.py
```

界面采用来源、摘要预览、筛选与引擎设置三栏布局。选择聊天记录后设置筛选范围并点击“生成摘要”，生成结果可以复制或导出。

桌面摘要默认使用格式化阅读视图，可切换到 Markdown 源码；复制和导出始终保留原始 Markdown/JSON。微信会话下拉支持搜索，日期提供“全部 / 最近 7 天 / 最近 30 天”快捷范围。DeepSeek 设置支持显示或隐藏 API Key，并可发送极小请求测试连接。

桌面设置会自动保存到：

```text
%LOCALAPPDATA%\WeChatChatSummarizer\settings.json
```

API Key 使用 Windows DPAPI 按当前用户加密后保存，配置文件和便携包中都不会出现明文密钥。聊天文件路径、微信会话选择和生成结果不会保存。

### 入口维护范围

当前版本只维护桌面 exe 和 `wxchat_desktop.py` 源码入口。旧浏览器 Web UI 已删除，不再提供 `wxchat_webapp.py`、`wxchat_app/webapp.py` 或 `web/` 静态资源。

桌面版默认选择 DeepSeek。填入 API Key 后会自动安全保存，当前固定使用 `deepseek-v4-pro`，默认开启思考模式，思考深度为“中”。选择 DeepSeek 后，筛选后的聊天内容会发送到 DeepSeek API。

为了提高 DeepSeek 上下文缓存命中率，程序发送给 DeepSeek 的输入会保持稳定提示结构，并且不会把“生成时间”这类每次变化的字段发送给模型。长聊天超过发送上限时会保留聊天开头和结尾，避免只发送前半段而漏掉后续结论。

### 直接读取微信会话

当前集成的是外部工具 `wechat-cli`。首次使用需要安装并初始化：

```powershell
python -m pip install git+https://github.com/huohuoer/wechat-cli.git
wechat-cli init
```

初始化时请保持微信电脑版已登录。`wechat-cli init` 会读取本机微信进程和数据库信息，只用于本地解密查询。

在界面里：

```text
记录来源 -> 微信会话
检测
刷新会话
选择群聊/会话
设置导出条数
导出并生成摘要
```

如果 `刷新会话` 提示“未找到微信数据目录”，先在终端运行：

```powershell
wechat-cli init
```

如果命令不可用，请确认安装 Python 时已把 Scripts 目录加入 `PATH`，然后重新打开终端。

### 命令行

生成 Markdown 报告：

```powershell
python wxchat_summarizer.py sample_chat.txt -o summary.md
```

查看控制台摘要：

```powershell
python wxchat_summarizer.py sample_chat.txt
```

输出 JSON：

```powershell
python wxchat_summarizer.py sample_chat.txt --format json -o summary.json
```

使用 DeepSeek API：

```powershell
python wxchat_summarizer.py sample_chat.txt --engine deepseek --deepseek-api-key sk-你的Key -o summary.md
```

也可以先设置环境变量，避免每次在命令里写 Key：

```powershell
$env:DEEPSEEK_API_KEY="sk-你的Key"
python wxchat_summarizer.py sample_chat.txt --engine deepseek -o summary.md
```

开启思考并使用中等深度：

```powershell
python wxchat_summarizer.py sample_chat.txt --engine deepseek --deepseek-thinking --deepseek-reasoning-effort medium -o summary.md
```

只总结某一天：

```powershell
python wxchat_summarizer.py sample_chat.txt --date-from 2026-06-02 --date-to 2026-06-02
```

只看某个成员：

```powershell
python wxchat_summarizer.py sample_chat.txt --speaker 张三
```

## 参数

```text
python wxchat_summarizer.py INPUT [-o OUTPUT] [--top-messages N] [--encoding auto]
                               [--date-from DATE] [--date-to DATE]
                               [--speaker NAME] [--format markdown|json]
```

- `INPUT`: 聊天文本路径
- `-o, --output`: 输出路径
- `--top-messages`: 每类摘录最多保留多少条，默认 8
- `--encoding`: 输入文件编码，默认 `auto`
- `--date-from`: 起始日期或时间
- `--date-to`: 结束日期或时间
- `--speaker`: 只保留指定成员，可重复传入
- `--format`: 输出格式，默认 `markdown`
- `--engine`: 摘要引擎，`local` 或 `deepseek`
- `--deepseek-api-key`: DeepSeek API Key；不传时读取 `DEEPSEEK_API_KEY`
- `--deepseek-model`: 兼容保留参数；当前程序固定使用 `deepseek-v4-pro`
- `--deepseek-base-url`: DeepSeek API 地址，默认 `https://api.deepseek.com`
- `--deepseek-thinking`: 开启 DeepSeek thinking mode
- `--deepseek-reasoning-effort`: 思考深度，默认 `medium`
- `--max-input-chars`: 发送给 DeepSeek 的聊天文本最大字符数，默认 `60000`

## 测试

```powershell
python -m unittest discover -s tests
python -m py_compile wxchat_summarizer.py wechat_cli_bridge.py wxchat_desktop.py wxchat_app\__init__.py wxchat_app\version.py wxchat_app\summarizer.py wxchat_app\wechat_cli_bridge.py wxchat_app\service.py wxchat_app\cli.py wxchat_app\desktop.py
```

## 封装

生成便携版文件夹和 zip：

```powershell
powershell -ExecutionPolicy Bypass -File package_portable.ps1
```

输出位置：

```text
dist\WeChatChatSummarizerPortable
dist\WeChatChatSummarizerPortable.zip
```

如果你想生成单个桌面版 `.exe`，运行：

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

这个脚本会在项目内创建 `.venv-build`，安装 `pyinstaller`，然后生成：

```text
dist\WeChatChatSummarizer.exe
```

`build/`、`dist/`、`.venv-build/`、`__pycache__/`、`release/` 属于构建产物或本地发布产物，已经写入 `.gitignore`。现有产物不会自动删除；需要重新发布时再运行打包脚本覆盖生成。

### 生成 0.9.0 正式试用包

```powershell
powershell -ExecutionPolicy Bypass -File release.ps1
```

发布脚本会运行测试、语法检查、EXE 构建、Windows Defender 扫描、版本和运行库校验、敏感内容检查、SHA256 生成及 ZIP 解压复核。输出位置：

Windows Defender 自定义扫描需要管理员权限。若只需要验证其他发布步骤，可使用 `-SkipDefenderScan`；对外分发前仍应使用管理员 PowerShell 完整运行一次。

```text
release\WeChatChatSummarizer-0.9.0-win64
release\WeChatChatSummarizer-0.9.0-win64.zip
```

公开仓库只提交源码、测试、脚本、发布文档和样例文件。不要提交本地交接记录、构建缓存、临时日志、虚拟环境或生成的发布目录。

## 隐私建议

聊天记录通常包含个人信息。桌面版默认使用 `deepseek`，筛选后的聊天内容会发送到 DeepSeek API；建议先按日期或成员筛选，必要时手动脱敏。如需完全本机处理，请把摘要引擎切换为 `local`。
