# AutoRewarder Enhanced / AutoRewarder 增强版

English | [中文](#中文说明)

> A community-maintained derivative of [safarsin/AutoRewarder](https://github.com/safarsin/AutoRewarder). The original project is licensed under the MIT License; see [LICENSE](LICENSE).

## English

AutoRewarder Enhanced is a Windows-oriented desktop automation project for Microsoft Rewards. It extends the upstream AutoRewarder browser workflow with a separately controlled mobile-activity layer, stronger daily-task verification, per-account state, diagnostics, and tests.

### Main features

- PC and mobile Bing search workflows through Selenium Edge profiles.
- Daily Set and More Activities processing with DOM/RSC status checks, post-click verification, and bounded retries.
- Optional mobile check-in and Read to Earn activities through the Rewards activity API.
- Interactive OAuth authorization in the account's visible Edge profile; refresh tokens are protected with Windows DPAPI and access tokens stay in memory.
- Per-account `mobile_status.json` state with `completed`, `already_done`, `partial`, `unavailable`, `auth_required`, `failed`, and `stopped` outcomes.
- GUI controls for mobile-task settings and a diagnostic “Mobile tasks only” run.
- Headless CLI flags for mobile-only runs and safe fallback without mobile API tasks.
- Unit tests for authentication failures, retries, balance verification, duplicate prevention, and multi-batch scheduling.

The personal Windows daily wrapper and account-specific scheduled-task configuration are intentionally excluded from this repository. Configure scheduling for your own environment instead of copying someone else's account ID or local path.

### Requirements

- Windows 10/11 for the DPAPI-backed mobile token store.
- Microsoft Edge and a signed-in Rewards account profile.
- Python 3.12+ for source development, or a locally built PyInstaller package.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the GUI:

```powershell
python AutoRewarder.py
```

For headless operation, use an account ID or label from your own local configuration:

```powershell
python AutoRewarder.py --headless --account <account-id>
python AutoRewarder.py --headless --account <account-id> --mobile-tasks-only
python AutoRewarder.py --headless --account <account-id> --skip-mobile-tasks
```

Build the onedir package:

```powershell
python -m PyInstaller --noconfirm --clean AutoRewarder.spec
```

### Mobile authorization and safety

The first mobile-task authorization is interactive and must be completed by the account owner in a visible Edge window. This project does not ask for or store a Microsoft password. Never commit `mobile_token.bin`, account JSON files, logs, screenshots containing personal data, or any API key.

The mobile activity API, Rewards eligibility, activity identifiers, response schemas, and point limits can change by region or over time. A request is not treated as successful merely because it returned HTTP 200; the runner requires an explicit completion marker or a verified balance increase. Microsoft may restrict automated activity, so use a test account and review the current Rewards rules before running it.

### Upstream and changes in this fork

The browser automation, application structure, and original resources are derived from [AutoRewarder](https://github.com/safarsin/AutoRewarder) by safarsin. This fork adds or changes mobile task handling, OAuth/DPAPI storage, status models, scheduling integration, GUI controls, statistics, More Activities verification, tests, and documentation. The upstream copyright and MIT notice remain in [LICENSE](LICENSE); the non-authoritative Chinese explanation is in [LICENSE.zh-CN.md](LICENSE.zh-CN.md).

## 中文说明

AutoRewarder 增强版是基于 [safarsin/AutoRewarder](https://github.com/safarsin/AutoRewarder) 修改的 Microsoft Rewards 自动化项目。上游代码采用 MIT License，本仓库保留上游版权和许可证；中文许可证说明见 [LICENSE.zh-CN.md](LICENSE.zh-CN.md)。

### 功能

- 使用 Selenium Edge 配置执行 PC/移动 Bing 搜索。
- 执行 Daily Set 和 More Activities，并在点击后重新检查状态，最多有限重试。
- 可选执行移动签到和“阅读以赚取”任务。
- 首次授权使用可见 Edge 交互完成；刷新令牌使用 Windows DPAPI 保护，访问令牌只保存在内存中。
- 每个账号保存 `mobile_status.json`，明确记录完成、已完成、部分完成、不可用、需要授权、失败和停止等状态。
- 设置页提供移动任务配置和“仅运行移动任务”诊断入口。
- CLI 支持移动任务专用运行，以及跳过移动 API 的人工回退模式。
- 包含授权失败、网络重试、余额核验、重复提交防护和高级调度测试。

本仓库故意不包含个人的 Windows 每日包装脚本和账号专属计划任务配置。使用者应根据自己的账号和运行环境重新配置调度，不要复制他人的账号 ID、本地路径或运行数据。

### 使用前提

- Windows 10/11（移动令牌存储使用 DPAPI）。
- 已安装 Microsoft Edge，并在自己的账号配置中完成登录。
- 源码开发使用 Python 3.12 或更高版本；也可以自行构建 PyInstaller 版本。

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

启动 GUI：

```powershell
python AutoRewarder.py
```

无界面运行时必须使用自己的账号 ID 或标签：

```powershell
python AutoRewarder.py --headless --account <account-id>
python AutoRewarder.py --headless --account <account-id> --mobile-tasks-only
python AutoRewarder.py --headless --account <account-id> --skip-mobile-tasks
```

构建 onedir 版本：

```powershell
python -m PyInstaller --noconfirm --clean AutoRewarder.spec
```

### 授权与安全

移动任务首次授权必须由账号所有者在可见 Edge 窗口中完成。程序不会索取或保存微软密码。不要提交 `mobile_token.bin`、账号 JSON、日志、含个人信息的截图或任何 API Key。

移动活动接口、地区资格、活动标识、响应结构和积分上限都可能变化。程序不会仅凭 HTTP 200 判定成功，而是要求明确的完成状态或实际余额增加。微软可能限制自动化活动，使用前请确认当前 Rewards 规则，并优先使用测试账号。

### 上游与本仓库修改

浏览器自动化、应用结构和原始资源来自 safarsin 的 [AutoRewarder](https://github.com/safarsin/AutoRewarder)。本仓库新增或修改了移动任务、OAuth/DPAPI 存储、状态模型、调度接入、GUI、统计、More Activities 复核、测试和文档。上游版权和 MIT 原文保留在 [LICENSE](LICENSE)；中文说明见 [LICENSE.zh-CN.md](LICENSE.zh-CN.md)。

## License / 许可证

The upstream portions and this derivative distribution are released under the MIT License. See [LICENSE](LICENSE) for the authoritative English text and [LICENSE.zh-CN.md](LICENSE.zh-CN.md) for a non-authoritative Chinese explanation.
