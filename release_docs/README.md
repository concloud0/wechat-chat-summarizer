# 微信聊天摘要工具 0.9.0

MIT 开源项目，面向 64 位 Windows 10/11 的个人工具试用版。

> 如果只想运行程序，请下载 `WeChatChatSummarizer-0.9.0-win64.zip`。GitHub 自动生成的 `Source code (zip)` / `Source code (tar.gz)` 是源码包，不包含已打包好的 EXE。

## 开始使用

1. 核对 `SHA256SUMS.txt` 中的 EXE 校验值。
2. 双击 `WeChatChatSummarizer.exe`。
3. 选择文本聊天记录，设置筛选条件并生成摘要。

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

## 常见问题

### 未知发布者

0.9.0 试用版未购买代码签名证书。请从可信来源获取 ZIP，并在运行前核对 SHA256。

### DeepSeek 无法连接

检查 API Key、API Base URL 和网络连接，可在应用内点击“测试连接”。

### 摘要内容不准确

AI 摘要只能辅助阅读。重要结论、数字、时间和责任人必须回看原始聊天记录。

## 隐私

请阅读 `隐私与风险说明.md`。不要在未获授权的情况下上传他人的敏感聊天内容。

## 开源许可

本项目使用 MIT License 开源，发布包内附带 `LICENSE`。
