# LAUNCH.md — 从 0 到第一个 300 star

> 这份文件不进 README。它是操作手册：渠道、文案、时间表、指标、以及哪些手段有效但有代价。

---

## 0. 先认清 star 从哪来

一个陌生人在 8 秒内决定 star 与否，只回答三个问题：

| 问题 | 由什么回答 | 缺了会怎样 |
|---|---|---|
| 这解决我的问题吗？ | 标题 + 一句话 + 图 | 划走 |
| 我信它真的能用吗？ | 动图 / 真实输出 / 测试数字 | 收藏不 star |
| 作者是谁？ | 技术文章 / HN 评论区 / commit 历史 | 不转发 |

**star 不是被说服的，是被"看懂 + 相信"触发的。** 所以本手册 70% 的工作在仓库本身，30% 在渠道。

冷启动只有一条路：**借别人的流量**。你自己的账号发帖 = 0 曝光。HN / Reddit / PH / 中文社区 = 现成流量池。

---

## 1. 仓库转化优化（T-7 天，半天能做完全部）

每一项都是转化率，不是装饰。

- [x] 首屏图（`docs/architecture.png`）——已做
- [x] demo 动图（`docs/demo.gif`，499KB）——已做，**必须放 README 第一屏**
- [ ] social preview 图（`docs/social.png`，1280×640）→ 网页操作：`Settings → Social preview → Upload`
- [x] topics：`ai llm agents testing regression-testing developer-tools ci python`
- [ ] Release `v0.1.0` + release notes（GitHub 首页会显示，且 awesome-list 要求有 release）
- [ ] 中文 README（`README.zh-CN.md`）——中文渠道转化翻倍
- [ ] `CONTRIBUTING.md` + Issue 模板——fork 的主要动机是"我想改一点"
- [x] 零依赖 badge（`runtime deps: 0` 是最强的信任信号之一）
- [ ] 顶部固定一句"它不是中间件"——已写，别删，这是最常被误解的点

**别做的事**：不要在 README 里堆 15 个 badge、不要写 "blazingly fast"、不要放 roadmap 里 20 个没做的功能。开源读者对"过度承诺"的免疫力极高。

---

## 2. 内容弹药（T-3 天）

传播靠故事，不靠功能列表。这个项目有一个**天然的好故事**：

> 我做了个检测 AI 静默失败的工具。它在我自己的测试集上全绿通过。然后我拿 60 个真实文件去跑，它在三个已知回归上依然全绿——因为它只抽查了 25 个输入。抽样决定通过与否，等于门是装饰。

这个故事有：具体场景、反转、自省、技术细节。比"我做了一个工具"强十倍。

### 五个选题（挑两个写）

1. **《我的 AI 测试工具在全绿的情况下漏掉了 58% 的输入》**
   主线：五次迭代、五个缺陷、每次都是真实数据打脸。
   平台：dev.to / Medium / 掘金 / 知乎。

2. **《AI 应用没有 CI 这件事，值多少钱》**
   主线：市场分析。引用真实 issue 数据（autogen 417 条评论要动作回执、llama_index 33 条要确定性中间件）。
   平台：即刻 / X / 少数派。

3. **《我扒了 166 个 AI 项目的 issue，它们都在同一个地方坏》**
   主线：六类痛点 → 一个根因（不产出证据）。
   平台：知乎 / 公众号 / HN（作为独立帖）。

4. **《为什么 token-set 比 embedding 更适合做回归检测》**
   技术向，吸引工程师。论证：回归要的是"变了没有"，不是"像不像"；成本、确定性、离线。
   平台：dev.to / Lobsters。

5. **《不调用模型的门，才会被留在 CI 里》**
   产品哲学，短。适合 X 线程。

---

## 3. 渠道与可粘贴文案

### 3.1 Hacker News（最重要，一次机会）

**时点**：周二 / 周三 / 周四，美东 06:00–09:00 发（= 北京 19:00–22:00）。
**标题**（不要用感叹号、不要用 "revolutionary"）：

```
Show HN: Agent-contract – CI for AI agents that catches silent regressions
```

**正文**（HN 用户会读第一段决定是否点开）：

```
Hi HN,

I kept hitting the same failure mode with AI agents: you swap a model, nothing
crashes, exit code 0, and three days later someone notices the app has been
quoting a 3-day refund window instead of 7. The shape is right, the tone is
right, the fact is wrong. Traditional software throws when it breaks; LLM apps
return something plausible.

agent-contract does two things:

  mine  — reads the traces you already log, writes assertions with evidence
  run   — replays the same inputs against a new version, reports red/amber/green

No model calls, no embeddings, no API key, stdlib only. Comparison is token-set
similarity plus fact and number extraction. Everything stays local.

The most useful thing I can tell you is how it failed. I built it against a
clean fixture set and it passed. Then I ran it on 60 real files and it reported
all green on a batch with three deliberate regressions. Five defects fell out.
The worst: drift only checked a sample of 25 of the 60 inputs, so the file that
actually changed was never examined. Sampling the thing that decides pass/fail
is how a gate becomes decorative.

Repo: https://github.com/bandageok/agent-contract

Happy to talk about the mining heuristics, the false-positive problem, or where
this approach breaks down (it currently assumes the target batch replays the
baseline's inputs — that is the biggest open question).
```

**评论区纪律**（决定能不能上首页）：
- 前 2 小时必须在线，每条评论 10 分钟内回。
- 有人质疑"这不就是 promptfoo / langfuse 吗" → 直接承认边界，给对比表，不要杠。
- 有人问实现细节 → 给具体数字，不给形容词。
- 被 flag 了不要重新发，等 6 个月。

### 3.2 Reddit

发三个，间隔 24 小时，**每个都改写开头**（同文多发会被识别）。

- `r/LocalLLaMA`（对无依赖、本地跑最友好）：
  > **Title**: I built a CI gate for agents that runs fully offline (no embeddings, no API key, stdlib only)
- `r/ClaudeAI` / `r/AI_Agents`：
  > **Title**: Swapped models and the refund policy silently changed from 7 days to 3. So I built a regression gate for agents.
- `r/LLMDevs`：技术向，讲 mining 启发式。

**不要**发 `r/MachineLearning`（禁自推，直接封）。

### 3.3 Product Hunt

- 需要提前 7 天排队，UTC 00:01 上线。
- Tagline（60 字符内）：`CI for AI agents: catch silent regressions before merge`
- 第一张图用 `docs/social.png`，第二张 `docs/architecture.png`，第三张 GIF。
- PH 的流量质量低于 HN，但对"收藏/书签"有效。

### 3.4 X / Twitter 线程（5 条）

```
1/ Your agent didn't crash.
   It just started quoting a 3-day refund window instead of 7.
   Exit code 0. No exception. Nobody noticed for six days.

2/ This is the default failure mode of LLM apps: the output stays plausible.
   And the stronger the model, the more plausible the mistake.

3/ So I built agent-contract:
   mine — learn "correct" from traces you already log
   run  — replay the same prompts, get red/amber/green

4/ No model calls. No embeddings. No API key. stdlib only.
   A gate that costs money per run is a gate people disable.

5/ Best part: it lied to me first. All green on a real batch with 3 known regressions.
   Cause: drift only sampled 25 of 60 inputs.
   Sampling the thing that decides pass/fail is how a gate becomes decorative.
   → github.com/bandageok/agent-contract
```

配图：第 1 条配 `docs/social.png`，第 5 条配 `docs/demo.gif`。

### 3.5 中文渠道

- **V2EX** → `/go/create`（分享创造）：
  > **标题**：做了个给 AI 应用做回归测试的 CLI，不调模型、零依赖
  > 正文：讲那个"全绿但全错"的故事，附 GIF。V2EX 对"零依赖/本地"特别买账。
- **即刻**：短，图为主，讲痛点不讲技术。
- **掘金 / 知乎**：发第 1 或第 3 个选题的完整文章，结尾放仓库链接。
- **少数派**：如果能写成"工作流"视角（我怎么给 AI 产品做发布检查），过稿率高。

---

## 4. 时间表

| 日 | 动作 | 耗时 |
|---|---|---|
| T-7 | 仓库优化清单全部勾完；上传 social preview；建 `v0.1.0` release | 2h |
| T-5 | 发一篇技术文章（选题 1），拿第一批自然搜索流量 | 4h |
| T-3 | 中文 README + 中文帖草稿；准备好所有文案 | 2h |
| T-0 周二 | 19:00 北京 Show HN → 全程守评论 3h | 3h |
| T-0 +2h | X 线程；r/LocalLLaMA | 30m |
| T+1 | Product Hunt；V2EX；即刻 | 1h |
| T+2 | r/ClaudeAI；掘金/知乎长文 | 1h |
| T+3 | 批量提 awesome-list PR（见下） | 1h |
| T+7 | 复盘：哪个渠道带来的 star，决定第二轮 | 1h |

---

## 5. 指标（别自欺）

| 指标 | 及格 | 好 |
|---|---|---|
| HN 前 3 小时得分 | 15 | 50+（进首页） |
| HN → 仓库点击率 | 8% | 15% |
| 仓库访客 → star | 5% | 12% |
| 一周 star | 80 | 300 |
| fork / star 比 | 5% | 15%（工具类项目的健康值） |

**fork 比 star 更能说明问题**：fork 意味着"我要改/我要用"，star 只是"我看见了"。想提高 fork，就在 README 里给出**明确的改造入口**（见第 7 节）。

---

## 6. 边缘手段（有效，但有代价）

按风险从低到高。自己判断。

**低风险**
- 在 HN 的**相关讨论**下留言（不是发新帖），讲你在解决的具体问题，附链接。这是 HN 最接受的推广方式。
- 给 awesome-list 提 PR（见第 7 节）。
- 在你引用的那些 issue 里，**当有人问"怎么测这个"时**回答，并提一句你的工具。只在你真的解决了对方问题的时候。

**中风险**
- 每次大模型发布（新 Claude / GPT 版本），跑一次"换模型回归"并公开发结果。持续蹭热点，且每次产出真实数据。这是长期最有效的曝光机器。
- 给 promptfoo / langfuse 的 issue 提"互补方案"说明。会被部分人视为蹭，但也会被目标用户看到。

**高风险（会反噬）**
- 买 star / 互 star 群。GitHub 有检测，且懂行的人一眼看出 star 曲线异常，信任归零。
- 同一天在 5 个社群发同一段文案。会被标记为 spam。
- 在别人仓库的 issue 里硬推链接。

**代价是怎么算的**：开源信任是一次性的。被 flag 一次，同一个渠道永久失去。所以高风险的收益必须极大才做——而 300 star 这个量级，不值得。

---

## 7. 提高 fork 的具体做法

fork 的动机只有三个：「我想加个功能」「我想改判据」「我想在自己的仓库里用」。

对应三个入口，写进 README 和 issue 模板：

1. **`Good first issue` × 5**，每个都是 30 分钟能改完的：
   - 加一个 trace 格式适配器（Bedrock / Vercel AI SDK / 自建）
   - 加一种事实单位（货币代码、时区）
   - `--format html`
   - 中文事实正则（`万元`、`个工作日`）
   - `action.path_within_root` 支持 glob 白名单
2. **`CONTRIBUTING.md` 明确写清**：怎么加一个断言类型（三步：miner 生成 → runner 求值 → 注册表加一行）。
3. **`docs/extending.md`**：一个完整的"加一种断言"的示例 diff。

没有这三个，fork 率会停在 3% 左右。

---

## 8. awesome-list PR 清单

按收录概率排序（都是真实存在、接受 PR 的列表）：

| 仓库 | 加到哪一节 | 备注 |
|---|---|---|
| `steven2358/awesome-generative-ai` | Testing & Evaluation | 门槛低 |
| `Hannibal046/Awesome-LLM` | 会挑，写清"为什么值得收录" |
| `e2b-dev/awesome-ai-agents` | Tools | 高流量 |
| `microsoft/awesome-ai-agents` | Evaluation | |
| `kaushikb11/awesome-llm-agents` | | |
| `veggiemonk/awesome-docker` | 不适用，跳过 | |

PR 描述模板：

```
Adds agent-contract — a CLI that mines behavioural contracts from existing agent
traces and gates model/prompt/dependency changes in CI.

Why it belongs here: it is the only entry in this list that works from traces
you already have, requires no model calls and no API key (stdlib only), and runs
fully offline. MIT, 61 tests, zero runtime dependencies.
```

一次提 3 个，别一次提 10 个（会被当 spam）。

---

## 9. 不要做

- 不要写"我们非常激动地宣布"。
- 不要在 README 顶部放 roadmap。
- 不要在 HN 标题里放 "Open Source" 或 "AI-powered"。
- 不要回复"这没用的"这类评论超过一次。
- 不要在发布当天改 API 或重写 README（访客会撞到 404）。

---

## 10. 一句话总结

**仓库做成"看一眼就懂、看两眼就信"，然后用一个真实的反转故事，去 HN 借一次流量。**
剩下的渠道都是这同一件事的复制。