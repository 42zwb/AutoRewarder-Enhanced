# AutoRewarder Enhanced / AutoRewarder 增强版

English | [中文](#中文说明)

> A community-maintained derivative of [safarsin/AutoRewarder](https://github.com/safarsin/AutoRewarder). The original project is licensed under the MIT License; see [LICENSE](LICENSE).

## English

AutoRewarder Enhanced is a Windows-oriented desktop automation project for Microsoft Rewards. It extends the upstream AutoRewarder browser workflow with a separately controlled mobile-activity layer, stronger daily-task verification, per-account state, diagnostics, and tests.

### Known issue: Bing searches may not earn points

As of 2026-09-13, both the desktop and mobile Selenium search paths have been reproduced completing their browser actions while Microsoft Rewards awards no search points. The account remained signed in and an immediately following manual search earned 3 points, while the authenticated Rewards counter stayed unchanged after each automated test. Microsoft defines a qualifying Rewards search as text manually entered for genuine personal research and explicitly excludes bots, macros, and other automated means; its support guidance also says not to use programs for searching ([Services Agreement](https://www.microsoft.com/en-us/servicesagreement), [Rewards search limits](https://support.microsoft.com/en-au/accounts-billing/rewards/limiting-your-searches-in-microsoft-rewards)).

The code now treats the authenticated Rewards `pcSearch` counter—not a Selenium keypress—as the source of truth. It validates the Bing results URL, removes the unstable random Images/Videos/News tab switching, and submits one canary query before any remaining batch. If the server counter does not increase, it records no credited search, returns exit code `3` (`manual_required`), and stops instead of reporting `Done!` or repeatedly submitting searches. Other partial failures return exit code `2`. This fixes the false-success bug; it does **not** bypass Microsoft eligibility decisions or guarantee that automated searches earn points. Mobile check-in, Read to Earn, Daily Set, and More Activities were outside the scope of this reproduction and are not covered by this notice.

Diagnosis on the reproduced account ruled out the usual local causes: the account was authenticated, the Rewards user-info endpoint returned a valid balance and `18/60` search progress, the desktop result URL loaded correctly, and the mobile session reported an iPhone user agent, a 412×915 viewport, five touch points, and a coarse pointer. Neither automated path changed the server counter, while one manual search on the same account immediately changed it from `15/60` to `18/60` and increased the balance by 3. No explicit cooldown or restriction flag was exposed by the user-info payload. The evidence therefore locates the remaining decision at Microsoft’s server-side eligibility layer rather than in the GUI, cached balance, sign-in state, query count, or mobile emulation switch.

An exact upstream comparison reaches the same conclusion. The locally retained v4.1 `SearchEngine`, `DriverManager`, `HumanBehavior`, `human_typing`, and `assets/queries.json` match tag [`v4.1`](https://github.com/safarsin/AutoRewarder/tree/v4.1) byte-for-byte. From v4.1 to [`v4.3`](https://github.com/safarsin/AutoRewarder/tree/v4.3), the ordinary `perform_searches` function, typing helper, human-behavior implementation, and query dataset did not change; the relevant additions concern visual search, while the driver change only keeps GPU acceleration enabled for the separate “browse 30 minutes” task. Upstream issue [#115](https://github.com/safarsin/AutoRewarder/issues/115) reports the same combination—logs say success, automated searches receive no points, and manual searches still receive points—and the maintainer attributes it to Microsoft rejecting the points. The newer open issue [#128](https://github.com/safarsin/AutoRewarder/issues/128) again reports daily searches not being counted. Because the old and current upstream text-search submission chain is the same one already reproduced here, rerunning the old package would repeat the same automated request rather than test an alternative implementation.

There is no supported automatic workaround for a server rejection of automated Rewards searches. Changing fingerprints, hiding WebDriver, or adding “human-like” timing would attempt to evade the eligibility controls and is intentionally not implemented here. Stop automated searches and use manually entered, genuine searches; if manual searches also stop receiving credit, wait for any temporary earning limitation to clear or contact Microsoft Rewards Support. The application’s `manual_required` result is a truthful hand-off, not a recoverable browser error.

### Main features

- PC and mobile Bing search workflows through Selenium Edge profiles.
- Daily Set and More Activities processing with DOM/RSC status checks, post-click verification, and bounded retries.
- Optional mobile check-in and Read to Earn activities through the Rewards activity API.
- Interactive OAuth authorization in the account's visible Edge profile; refresh tokens are protected with Windows DPAPI and access tokens stay in memory.
- Optional LLM API keys are stored outside `settings.json` (Windows DPAPI; mode-600 file for non-Windows development).
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
python AutoRewarder.py --headless --visible-browser --account <account-id>
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

### 已知问题：Bing 搜索可能不计分

截至 2026-09-13，桌面端和移动端 Selenium 搜索均已复现“浏览器动作完成，但 Microsoft Rewards 没有增加搜索积分”的问题。测试时账号保持登录，紧接着进行的人工搜索可以获得 3 分，但每次自动化测试后的官方 Rewards 计数均不变。微软把符合条件的 Rewards 搜索定义为用户为了真实个人研究而手动输入的搜索，并明确排除机器人、宏和其他自动化方式；官方支持页也明确要求不要使用程序辅助搜索（[微软服务协议](https://www.microsoft.com/en-us/servicesagreement)、[Rewards 搜索限制说明](https://support.microsoft.com/en-au/accounts-billing/rewards/limiting-your-searches-in-microsoft-rewards)）。

代码现已改为以登录账号返回的 Rewards `pcSearch` 计数为准，而不是把 Selenium 按下回车当作成功；同时验证 Bing 结果页 URL、移除不稳定的图片/视频/新闻随机标签跳转，并在剩余批次前只提交一次探测搜索。若服务端计数不增长，则计分搜索记为 0、返回退出码 `3`（`manual_required`）并立即停止；其他部分失败返回退出码 `2`。程序不再误报 `Done!` 或持续重复提交。该修改解决的是“程序误报成功”问题，**不会**绕过微软的资格判定，也不能保证自动搜索获得积分。本次复现没有覆盖移动签到、阅读以赚取、Daily Set 和 More Activities，因此本说明不对这些任务的状态作判断。

本次账号实测已经排除常见的本机原因：账号处于登录状态，Rewards 用户信息接口可以正常返回余额和搜索进度 `18/60`，桌面端能进入正确的 Bing 结果页；移动会话也确实报告 iPhone UA、`412×915` 视口、5 个触点和粗指针。桌面、移动两条自动路径都没有改变服务端计数，而同一账号随后进行一次人工搜索，进度立即从 `15/60` 变为 `18/60`，余额增加 3 分。用户信息响应中也没有公开的冷却或限制标志。因此，剩余判定发生在微软服务端的搜索资格层，而不是界面缓存、登录状态、查询次数或 mobile 模拟开关。

对上游源码的精确比较也得到相同结论。本机保留的 v4.1 `SearchEngine`、`DriverManager`、`HumanBehavior`、`human_typing` 和 `assets/queries.json` 与上游 [`v4.1`](https://github.com/safarsin/AutoRewarder/tree/v4.1) 逐字节一致。从 v4.1 到 [`v4.3`](https://github.com/safarsin/AutoRewarder/tree/v4.3)，普通文字搜索的 `perform_searches`、输入函数、行为模拟和查询词库均未改变；新增内容主要是图片搜索，驱动层唯一相关修改只是为独立的“浏览 30 分钟”任务保留 GPU 加速。上游问题 [#115](https://github.com/safarsin/AutoRewarder/issues/115) 记录了完全相同的组合：日志显示成功、自动搜索不计分、人工搜索仍计分，维护者将其归因于微软拒绝积分；更新的开放问题 [#128](https://github.com/safarsin/AutoRewarder/issues/128) 也再次报告日常搜索不计数。旧版与最新版上游的文字搜索提交链就是本次已经复现的同一条链，因此再次运行旧包只会重复同一种自动请求，并不能测试另一套实现。

服务端拒绝自动搜索后，不存在受支持的自动修复办法。更换指纹、隐藏 WebDriver 或进一步增加“拟人化”节奏都属于尝试规避资格控制，本仓库不会实现。此时应停止自动搜索，改为用户亲自输入、用于真实查询的搜索；如果人工搜索也不再计分，应等待临时获取限制解除，或联系 Microsoft Rewards 支持。程序返回的 `manual_required` 是准确的人工接管状态，不是一个可以靠重启浏览器恢复的错误。

### 功能

- 使用 Selenium Edge 配置执行 PC/移动 Bing 搜索。
- 执行 Daily Set 和 More Activities，并在点击后重新检查状态，最多有限重试。
- 可选执行移动签到和“阅读以赚取”任务。
- 首次授权使用可见 Edge 交互完成；刷新令牌使用 Windows DPAPI 保护，访问令牌只保存在内存中。
- 可选的 LLM API Key 不再写入 `settings.json`；Windows 使用 DPAPI，非 Windows 开发环境使用独立的 `600` 权限文件。
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
python AutoRewarder.py --headless --visible-browser --account <account-id>
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
