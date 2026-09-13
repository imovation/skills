# 故障排查手册

## 症状 → 原因 → 处置

| 症状 | 根因 | 处置 |
|------|------|------|
| `403 SUBSCRIPTION_REQUIRED (#3501)` | prod/autopush 端点的订阅校验（免费号在 prod 上必然出现）| 确认请求落在 daily；变体重试补丁是否在位 |
| `403 VALIDATION_REQUIRED` + validation_url | Google 账号级风控挑战；链接 plt 一次性、分钟级失效 | 浏览器登录**同一账号**打开最新链接完成验证；验证后建议重新 OAuth 刷新授权 |
| daily 返回 `404 Requested entity was not found` | 该模型实体当前不在 daily 清单中（动态漂移），或 wire 名不对 | 变体重试补丁自动换名重试；若仍 404 则该模型此刻确实不可用，稍后再试 |
| `429 RESOURCE_EXHAUSTED` | prod 免费配额耗尽（按账号+项目+IP 综合判定）| 换池内其他账号 / 等重置 / AI Pro 订阅 |
| 挂起无报错 | 见 §挂起类 |
| 模型列表缺某模型 | opencode.jsonc 未定义且核心解析失败会直接报 UnknownError | 在 provider.google.models 补定义（含 variants）|

## 挂起类

已定位的三种挂起点：

1. **错误响应体 web 流竞态**：响应头到达后 body 流永不结束 → `response.text()` 永挂。（pi 侧同类问题的修复参考 pi-expert P3）
2. **daily SSE 不关流**：finishReason 输出后服务端不断开，等 EOF 永挂。
3. **端点对特定请求静默拖延**：偶发，连接建立后零字节回包。

处置思路：给请求/读流加超时与看门狗，把"永挂"转化为"可重试错误"；不要依赖 EOF。

## 诊断工具箱

1. **调试日志**：
   ```bash
   OPENCODE_ANTIGRAVITY_DEBUG=1 opencode run -m google/<model> "hi"
   tail ~/.config/opencode/antigravity-logs/*.log
   ```
   含 ModelFamily 解析、账号选择、每端点请求/响应状态。

2. **请求转储补丁**（本技能维护的补丁自带）：转储到 `/tmp/oc-req-dump.json`，
   phase=pre(url/headers/body)/variant(候选名与状态)/resp(respBody)。
   注意 body 里 system prompt 含 `---`，分割要用 `\n---\n`。

3. **mihomo 连接表**：`up=1604/down=0` = TLS ClientHello 发出后握手黑洞（出口节点问题）。

4. **对照基准**：pi 侧同账号请求是否正常？pi 正常而 opencode 异常 → 客户端差异；都不正常 → 服务端/网络。

## 已知坑

- 标题生成等 small 请求固定用别名 `gemini-flash-latest`，主模型修复不代表它不报错。
- 插件的账号轮换只在限流信号时触发；手动切号要改 auth.json。
- `opencode models` 的列表 ≠ 可用性；必须实际发消息冒烟。
- 验证 JSONC 配置别用简单正则去注释（$schema 的 `//` 会误伤），用 opencode 本身验证。

## 2026-08-25 实战案例：3.7 Flash 全端点失败/挂起

排查链（值得复用的方法论）：
1. `OPENCODE_ANTIGRAVITY_DEBUG=1` + antigravity-logs 看账号选择与每端点状态
2. 包缓存 plugin.js 加 AGY_OC_DUMP 门控转储（pre/variant 带时间戳）
3. 同刻四路 A/B 隔离变量（UA×模型名），锁定 **UA 指纹是 daily 的模型实体门禁**
4. 账号池文件 rateLimitResetTimes 发现"限流中毒"→ 清标记 + antigravity.json 快速失败配置

最终修复集：
- 变体重试触发条件扩展为 404/429/403；候选名=原名±横线点分互换±思考后缀
- 200 响应需预读首块校验含 candidates/data: 才采纳（防空体假成功）
- UA 覆写为 cli 风格（放在 let response fetch 之前）
- antigravity.json: max_rate_limit_wait_seconds=20
- onebuilding2025 设为主活动账号（auth.json + 池首位），basepointxl 停用

遗留认知：daily 模型清单分钟级漂移属服务端行为，客户端只能自适应；某模型"突然全员不可用"时先怀疑漂移窗口，稍后重试。
