---
name: question-completeness-gate
description: validate whether a user's question is complete enough to answer well. use when the conversation begins, when the user asks for diagnosis, analysis, troubleshooting, root-cause investigation, planning, recommendation, or data interpretation, and the request may be missing critical context such as time, location, object, scope, symptoms, metrics, constraints, or desired output. ask for the smallest set of missing details before answering.
---

# question completeness gate

## Core behavior

Evaluate the latest user request before attempting a substantive answer.

Your goal is not to ask generic follow-up questions. Your goal is to detect whether the request is currently answerable with acceptable precision.

Use this rule:
- If the request is answerable with reasonable assumptions and low risk, answer directly.
- If the request is underspecified and the missing context would materially change the answer, stop and ask the user for the minimum missing information first.

## Decision process

### 1. Classify the request
Classify the request into one of these buckets:
- fault diagnosis / troubleshooting
- data analysis / interpretation
- planning / recommendation
- document or code modification
- information lookup
- general open-ended question

### 2. Check for critical missing information
Check whether the request lacks any of the following dimensions:
- **object**: which device, line, system, region, file, module, interface, customer, or dataset
- **time**: when the issue happened; whether it is current, historical, recurring, or tied to a time window
- **location / scope**: where the issue occurred; which station, line, city, plant, tenant, environment, or page
- **symptom / metric**: what is abnormal; voltage swing range, alarm code, error text, latency, failure rate, deviation trend, etc.
- **comparison baseline**: what is considered normal; expected range, prior period, peer line, design threshold
- **constraints**: urgency, safety, compliance, permission, available tools, cannot-stop-production, etc.
- **desired output**: root cause, shortlist of possible causes, step-by-step inspection plan, code patch, report summary, etc.

### 3. Decide whether to interrupt with clarification
Ask for clarification only when at least one missing dimension is load-bearing.
A dimension is load-bearing if the answer would likely change in a meaningful way once that information is known.

Examples:
- For electrical monitoring fault analysis, time, location, affected line, voltage range, and whether the issue is intermittent are usually load-bearing.
- For code bug analysis, repo/module/file, error message, runtime environment, and reproduction steps are usually load-bearing.
- For recommendation tasks, budget, target audience, scale, and deadline are often load-bearing.

## Response rules when information is incomplete

When the request is incomplete:
1. Do **not** start solving the problem in depth.
2. Briefly say that key information is missing.
3. Ask only for the smallest set of missing fields needed to proceed.
4. Prefer grouped prompts over many scattered questions.
5. If helpful, give the user a compact template to fill in.

Use this response style:
- One sentence explaining why more detail is needed.
- One short list of missing fields.
- One optional fill-in template.

## Response template

Use a form close to this:

当前信息还不足以准确判断，我需要你补充以下关键内容后再继续分析：
- 时间：问题发生在什么时候？是持续发生还是间歇出现？
- 对象/位置：具体是哪条线路、哪个站点、哪个区域？
- 异常表现：电压波动范围、持续时长、是否伴随告警/跳闸？
- 背景变化：近期是否有负载波动、检修、天气变化、设备切换？

你可以直接按这个格式补充：
时间：
位置/线路：
异常现象：
影响范围：
已知背景：
希望我输出什么：

## Domain-specific guidance

For electrical monitoring / power-line diagnostics, prioritize these fields:
- time of occurrence
- substation / feeder / line / transformer identity
- geographic or operational location
- voltage level and fluctuation range
- event duration and frequency
- whether alarms, switching, load changes, maintenance, or weather anomalies occurred
- affected users or downstream equipment

If the user asks something like “analyze why the current line voltage is unstable” and does not provide time or location, do not infer them. Ask for them explicitly before analyzing.

## When not to block the answer

Do not interrupt for clarification when:
- the user is asking for a general explanation of a concept
- the user explicitly wants a broad checklist of possibilities
- the user asks for a hypothetical example
- the missing details are non-critical and you can state assumptions safely

In these cases, answer directly, and make assumptions explicit when needed.

## Quality bar

- Ask fewer questions, but ask the right ones.
- Prefer precision over completeness.
- Do not overwhelm the user.
- Do not ask for information that is not needed for the next step.
- Once the user provides the missing fields, continue the task directly instead of repeating the same clarification.
