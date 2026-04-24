# README Rewrite Brief

## Goal

为后续 `ccglm` 重写 `README.md` 与 `README.zh-CN.md` 提供一份收敛后的需求包.

目标不是把 README 写得更“像 AI”, 而是让它更像优秀 GitHub 项目首页:

- 价值主张短
- 命令真实可跑
- 结构清晰
- 少空话
- 少自夸
- 多证据

## Current README Problems

当前 README 的主要问题不是事实错误, 而是文风和信息组织方式带来的 “AI 味”.

### 1. 抽象价值句偏多

例如:

- `Code agents become more useful...`
- `packages that workflow...`

这类句子不是错, 但太像模型常见开场白. 优秀开源 README 通常更快进入:

- 这是什么
- 怎么装
- 怎么跑
- 为什么和别的东西不同

### 2. 用户入口不够前置

当前 README 先讲 `Why`, 再讲结构和命令. 对真正打开 GitHub 首页的人来说, 更重要的是:

1. 这是个什么工具
2. 我 30 秒内怎么跑起来
3. 它和别的工具相比到底解决什么问题

### 3. Feature list 偏“能力陈列”

当前条目大多是组件名或子系统名. 更好的写法应该围绕用户动作和结果:

- route a task
- bootstrap project memory
- inspect capability matches
- replay benchmark cases

而不是只列模块概念.

### 4. 缺少“为什么可信”的近身证据组织

现在 benchmark 在后面, 且像补充材料. 更好的 README 会更早给出可信信号:

- 本地执行
- smoke tests passed
- benchmark baseline
- optional deps, not required

### 5. 中文版基本是英文版结构翻译

这会让中文也带着英文技术营销腔. 中文版应该按中文技术社区的阅读习惯重组:

- 定位
- 解决什么问题
- 怎么跑
- 关键命令
- 边界

## Good README Patterns From Real Projects

以下模式来自真实知名项目的 README, 用于提炼写法, 不是照抄措辞.

### 1. `uv`

Source: https://github.com/astral-sh/uv

蒸馏点:

- 标题下一句就是**一句话定位**
- 很快进入 **Installation**
- 用 bullet 明确说明“替代什么, 快在哪里, 支持什么”
- 每个 feature 都附带真实命令片段
- 把 benchmark/性能数字作为可信信号, 不是空喊“很快”

可借鉴:

- 开头一句必须极短
- 安装和命令示例尽量前置
- 不讲空泛愿景, 直接讲动作和结果

### 2. `Playwright`

Source: https://github.com/microsoft/playwright

蒸馏点:

- 把文档入口放得非常明显
- `Get Started` 不只是安装, 而是按用户路径分流:
  - Test
  - CLI
  - MCP
  - Library
- 每个子路径都有 install + usage + capability
- README 本身像 landing page, 但仍然以可执行信息为主

可借鉴:

- 如果产品有多个入口, 要按“用户路径”组织, 不按“代码目录”组织
- 不同用户路径的命令示例要分组

### 3. `jj`

Source: https://github.com/jj-vcs/jj

蒸馏点:

- 顶部导航很清楚
- `Getting started` 前明确写实验性边界和限制
- 对“是否适合生产”这类问题有直接边界说明
- 把“风险/限制”正面写出来, 增加可信度

可借鉴:

- README 里应该有一段明确边界:
  - 它不是什么
  - 适合谁
  - 不适合谁

### 4. `Ollama`

Source: https://github.com/ollama/ollama

蒸馏点:

- 非常快进入 **Download / Get started**
- 命令和入口覆盖多平台
- 把 REST API / Python / JavaScript 使用路径并列展示
- 基本没有长段概念宣讲

可借鉴:

- 命令优先
- 平台和入口优先
- 少写长段解释, 多写短节和真实例子

## Rewrite Principles

后续 README 重写, 固定遵守下面这些原则.

### A. 开头三屏必须完成的事

1. 一句话定位
2. 30 秒快速开始
3. 2 到 4 条最关键差异点

如果前 3 屏还在解释“为什么记忆重要”, 就说明还不够收敛.

### B. 先写“做什么”, 再写“为什么”

推荐顺序:

1. What it is
2. Quick start
3. Core commands
4. Why it is different
5. Architecture / repo layout
6. Validation / benchmark
7. Scope / boundaries

### C. 每个 section 尽量回答一个问题

例如:

- `Quick Start` -> 我怎么跑
- `Core Commands` -> 我常用什么命令
- `Why This Is Different` -> 为什么不用别的方案
- `Validation` -> 我为什么该信它

不要一个 section 同时承担 3 个目标.

### D. 多用“可验证句”, 少用“判断句”

优先写:

- local route and capability search
- `./bin/codex-memo --help`
- 3 smoke tests passed
- route baseline: 130/130

少写:

- elegant workflow
- powerful memory layer
- serious developer tool

### E. 指标必须贴着能力出现

比如:

- 讲 route 时, 旁边就放 route baseline
- 讲 testing 时, 旁边就放 smoke tests

不要把所有数字都堆在文末.

### F. 中文版不要做直译

中文版应优先读起来像中文技术文档, 不是英文 README 的镜像.

## Required Sections For Rewrite

下一版 README 至少包含这些 section.

### English README

1. Title + one-line tagline
2. Short `What it is`
3. Quick Start
4. Core Commands
5. Why it is different
6. Validation
7. Repository Layout
8. Optional Semantic Extras
9. Scope

### 中文 README

1. 项目定位
2. 解决的问题
3. 快速开始
4. 常用命令
5. 与常见方案的差异
6. 验证结果
7. 仓库结构
8. 可选依赖
9. 边界说明

## Hard Constraints For ccglm

后续给 `ccglm` 的正文要求固定如下:

1. 不要写长段抽象背景铺垫.
2. 不要写“AI coding agents become more useful”这类泛化开场.
3. 不要把 README 写成产品宣传页.
4. 不要夸大成“best”, “world-class”, “market-leading”.
5. 每个 capability 后尽量给真实命令.
6. 命令必须与当前仓库真实命令面一致.
7. 数字只写已验证事实:
   - smoke tests 3 passed
   - route 130/130, top-1 100%, p50 445 ms
   - capability search 64/64, p50 139 ms
8. 必须明确:
   - local-first
   - no hosted API for core route / capability search
   - `numpy + sentence-transformers` 是 optional extras
9. 中文版必须单独成文, 不做英文直译腔.

## Suggested Structure For Next Rewrite

### README.md

```text
Title
One-line tagline
Quick Start
Core Commands
Why It Is Different
Validation
Repository Layout
Optional Semantic Extras
Scope
```

### README.zh-CN.md

```text
项目定位
快速开始
常用命令
为什么和常见方案不同
验证结果
仓库结构
可选依赖
边界说明
```

## Ready-To-Use Prompt Direction

后续不要让主线程直接改正文.

正确流程:

1. 主线程把本文件作为需求包给 `ccglm`
2. 主线程只补当前仓库真实事实与当前命令面
3. `ccglm` 直接输出最终版 `README.md` 与 `README.zh-CN.md`
4. 主线程只负责原样落盘, 不再二次改写
