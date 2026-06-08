# 微信聊天摘要工具 0.9.0

vibe coding试水作

面向 64 位 Windows 10/11 的个人工具试用版。

## 下载

请到 [Releases](https://github.com/concloud0/wechat-chat-summarizer/releases) 下载：

```text
WeChatChatSummarizer-0.9.0-win64.zip
```

不要下载 GitHub 自动生成的 `Source code (zip)` 或 `Source code (tar.gz)`，它们不是可运行程序包。

## 开始使用

1. 核对发布页和压缩包内 `SHA256SUMS.txt` 中的校验值。
2. 解压 `WeChatChatSummarizer-0.9.0-win64.zip`。
3. 双击 `WeChatChatSummarizer.exe`。
4. 选择文本聊天记录，设置筛选条件并生成摘要。

本版本未进行 Authenticode 代码签名。Windows 首次运行时可能显示“未知发布者”或 SmartScreen 提示。

## 摘要引擎

- `deepseek`：默认模式。筛选后的聊天内容会发送到所配置的 DeepSeek API。
- `local`：只在本机处理，不上传聊天内容，摘要能力相对基础。

API Key 使用 Windows DPAPI 当前用户作用域加密，保存在：

```text
%LOCALAPPDATA%\WeChatChatSummarizer\settings.json
```

删除 `%LOCALAPPDATA%\WeChatChatSummarizer` 文件夹可清除 API Key 和全部本地设置。

## 微信会话直读

文本文件摘要开箱即用，不需要 Python。

微信会话直读是可选高级功能，需要用户另行安装 Python 和 `wechat-cli`：

```powershell
python -m pip install git+https://github.com/huohuoer/wechat-cli.git
wechat-cli init
```

初始化时请保持微信电脑版已登录。若不安装该工具，仍可正常使用文本文件摘要。

## 隐私与风险

- DeepSeek 模式会上传筛选后的聊天内容；使用前请确认你有权上传相关内容。
- AI 摘要只能辅助阅读。重要结论、数字、时间和责任人必须回看原始聊天记录。
- 本试用版未进行代码签名，请从本仓库 Release 获取 ZIP，并核对 SHA256。

## 许可与源码边界

本软件当前不是开源项目。仓库只提供发布说明和试用版二进制包，具体使用边界见 `LICENSE`。
