# Peer Review Arena — Research & Design Document

This document explains the academic foundations, design rationale, and experimental methodology behind the Peer Review Arena environment.

---

## 1. Academic Foundation

### Multiagent Debate (Du et al., ICML 2024)

Du et al. demonstrated that having multiple LLM instances debate and refine answers leads to significantly more factual and accurate outputs than single-agent generation. The key insight: agents exposed to alternative viewpoints self-correct more effectively than agents reasoning in isolation.

**Relevance to Peer Review Arena:** Our cross-review phase directly implements this mechanism. After round 1, each agent sees the other's findings — an explicit "alternative viewpoint" that triggers re-evaluation and self-correction.

### MARTI Framework (Tsinghua University, ICLR 2026)

The Multi-Agent Review and Targeted Iteration (MARTI) framework achieved state-of-the-art code generation quality by having multiple agents iteratively review and improve each other's code. MARTI showed that cross-observation — agents seeing each other's work products — creates a stronger learning signal than self-refinement alone.

**Relevance to Peer Review Arena:** MARTI is a training framework; we provide the RL environment. Where MARTI trains code *generation*, our environment trains code *review* — the complementary skill. We package the core mechanism (cross-observation with iterative refinement) as an OpenEnv environment accessible to any RL researcher.

### Connection to Broader Multi-Agent RL

The environment draws on established multi-agent RL concepts:
- **Competitive self-play** (Silver et al., 2017): Agents improve by competing against each other
- **Theory of Mind** (Rabinowitz et al., 2018): Agents benefit from modeling what the opponent knows
- **Emergent communication** (Lazaridou et al., 2017): The flag format becomes a shared language for describing code issues

---

## 2. Multi-Agent System Design

### Why Two Agents?

Two is the minimum for cross-observation while keeping episode complexity manageable:
- **Two agents** = one opponent's perspective to learn from. Simple, focused learning signal.
- **Three+ agents** = combinatorial explosion in information sharing. Who sees whose findings? In what order? These design choices multiply without clear benefit for the core research question.

Two-agent design also maps cleanly to real-world pair code review, making results interpretable.

### Identity Isolation

Agents are identified only as "A" and "B" within an episode. They share:
- The same codebase
- The same task description
- The same action space

They do NOT share:
- Internal state (flags, step count)
- Round 1 findings (until cross-review)
- Model identity (can be different models)

This isolation ensures the cross-review signal is clean — improvement in round 2 is attributable to seeing the opponent's findings, not to information leakage.

### Information Control

The environment carefully controls what each agent knows and when:

| Phase | Agent knows | Agent doesn't know |
|-------|------------|-------------------|
| round_1 | Task, files, own flags | Opponent's existence, flags, or progress |
| cross_review | Own round 1 flags | Opponent's flags (until both submit) |
| round_2 | Own flags + opponent's round 1 flags | Opponent's round 2 changes |
| finished | Final scores, bug counts | Opponent's final flags (privacy) |

This staged information reveal is the core mechanism that makes cross-review meaningful. If agents always saw each other's work, there would be no independent review phase and no measurable "learning" signal.

---

## 3. Phase Design Rationale

### Why Four Phases?

```
round_1 --> cross_review --> round_2 --> finished
```

**round_1 (Independent Review):** Establishes a baseline. How thorough is the agent working alone? This is the control condition against which round 2 improvement is measured.

**cross_review (Synchronization):** Both agents must complete round 1 before either enters round 2. This prevents information asymmetry — if agent A saw B's findings before B was done, A would have an unfair advantage.

**round_2 (Cross-Review):** The experimental condition. Agents see opponent findings and can refine. The delta between round 1 and round 2 scores measures the agent's ability to learn from peer observation.

**finished (Terminal):** Both agents have submitted. Graded scores are returned. The episode is complete.

### Why Not More Rounds?

Diminishing returns. Research on multiagent debate shows most improvement happens in the first exchange of information. Additional rounds add complexity without proportional benefit. A single cross-review keeps the environment clean and the learning signal interpretable.

---

## 4. Reward Structure Design

### Two-Tier Rewards

**Shaping rewards (per-step):**
- `flag_issue`: +0.05

**Terminal reward (submit_final):**
- Graded score: [0.0, 1.0]

The 0.05 per-flag shaping reward solves the sparse reward problem. Without it, agents in early training would take random actions with no gradient signal until they happen to submit a good final review. The small reward encourages exploration (reading files, flagging issues) without overwhelming the terminal graded score that represents the true objective.

### Composite Scoring (Inference Layer)

The inference script computes a richer composite score:

```
score = W_RECALL * recall + W_UNIQUE * uniqueness + W_LEARN * learning
```

| Weight | Component | Value | Rationale |
|--------|-----------|-------|-----------|
| W_RECALL | Recall (bugs found / total) | 0.60 | Primary objective: find bugs |
| W_UNIQUE | Uniqueness (found but opponent missed / total) | 0.25 | Competitive pressure: be thorough |
| W_LEARN | Learning (round 2 gains / total) | 0.15 | Cooperative pressure: learn from peer |

**Why these weights?** Recall dominates because finding bugs is the core task. Uniqueness gets 25% because we want to reward agents that add value beyond what any single agent could find. Learning gets 15% because it's the novel signal — but shouldn't dominate, since an agent that finds everything in round 1 (learning = 0) is still excellent.

---

## 5. Task Difficulty Progression

### Design Methodology

Each difficulty level increases along three axes:

| Axis | Easy (bug_hunt) | Medium (security_audit) | Hard (architecture_review) |
|------|-----------------|------------------------|---------------------------|
| **File count** | 1-2 files | 2-3 files | 3-5 files |
| **Bug visibility** | Syntactically obvious | Requires flow analysis | Requires systems reasoning |
| **Bug type** | Logic errors, off-by-one | Injection, IDOR, hardcoded secrets | N+1 queries, race conditions, memory leaks |
| **Cross-file reasoning** | Not needed | Some (auth flow) | Essential (trace call paths) |

### Template System

Each task has 5 procedurally generated templates (seed-selectable). Templates are hand-crafted code snippets with known ground truth bugs. The seed determines which template is selected, ensuring reproducibility while providing variety across episodes.

**Why 5 templates per task?** Enough variety to prevent memorization, few enough to ensure quality. Each template is manually verified to contain exactly the documented bugs with correct ground truth metadata.

---

## 6. Grading Algorithm Design

### Three Graders for Three Tasks

Each grader implements `is_true_positive(flag, ground_truth)` and `compute_score(flags, ground_truth)` with the same matching interface but different scoring logic.

#### grader1 (Bug Hunt): TP Count / Total

```python
score = len(matched_bugs) / len(ground_truth)
```

**Rationale:** For general bug hunting, all bugs matter equally. A missed off-by-one is as bad as a missed logic error. Simple ratio scoring.

#### grader2 (Security Audit): Severity-Weighted

```python
score = sum(severity_weight[bug] for bug in matched) / sum(severity_weight[bug] for bug in all_bugs)
```

Weights: critical=0.40, major=0.35, minor=0.25

**Rationale:** In security, a missed SQL injection (critical) is categorically worse than a missed verbose error message (minor). Severity weighting reflects real-world risk prioritization.

#### grader3 (Architecture Review): Keyword-Match Fraction

```python
score = sum(keyword_fraction(flag, bug) for matched) / total_bugs
```

**Rationale:** Architecture issues are nuanced. Saying "performance problem" is less valuable than saying "N+1 query pattern: one DB query per item in loop; batch-fetch with SELECT IN." Keyword matching rewards depth of understanding, not just location accuracy.

### Shared Matching Criteria

All three graders use identical `is_true_positive` logic:

1. **File match:** `flag.file_path == bug.file` (exact match)
2. **Line proximity:** `abs(flag.line_number - bug.line) <= 8`
3. **Keyword overlap:** `matched_keywords / total_keywords >= 0.30`

**Why 8-line tolerance?** Agents might flag a function signature (line 10) while the bug is in the function body (line 15). An 8-line window accommodates this without being so loose that unrelated flags match.

**Why 30% keyword threshold?** Low enough that agents don't need to use exact terminology, high enough that a generic "there's a bug here" doesn't count. With 5-6 expected keywords per bug, 30% means matching 2+ keywords.

**Deduplication:** Multiple flags matching the same bug (same file + line) count only once. This prevents score inflation from re-flagging.

---

## 7. Cross-Learning Mechanism

### Information Asymmetry as Learning Signal

The key insight: by withholding opponent findings until round 2, we create a natural experiment within each episode.

```
Round 1 score = f(agent's independent ability)
Round 2 score = f(agent's independent ability + learning from opponent)
Delta = Round 2 - Round 1 = learning signal
```

An agent with delta > 0 has successfully extracted value from the cross-review. An agent with delta = 0 either found everything already (perfect round 1) or failed to learn from opponent findings.

### Adversarial Pressure

Two complementary pressures emerge:

1. **Find things your opponent will miss** (competitive): If both agents find the same bugs, neither gets uniqueness credit. Agents are incentivized to be thorough and creative.

2. **Recognize valid findings from your opponent** (cooperative): If the opponent found a real bug you missed, adding it improves your score. Agents are incentivized to be humble and evaluative.

These pressures don't conflict — they push toward the same outcome: a thorough, self-aware reviewer. This is why the framework produces better reviewers than single-agent training.

### Measuring Cross-Review Improvement

The inference script tracks:
- `round1_score`: Agent's graded score after round 1
- `final_score`: Agent's graded score after round 2
- `adopted_flags`: Count of opponent flags the agent added in round 2
- Composite score with explicit learning weight (W_LEARN = 0.15)

A well-performing agent shows: high round 1 score (thorough independent review) + positive improvement in round 2 (effective cross-learning).

---

## 8. Experimental Design

### Measuring Environment Effectiveness

To validate that the cross-review mechanism creates meaningful learning signal:

**Experiment 1: Cross-review vs. no cross-review**
- Control: Run agents for 2 rounds but never reveal opponent findings
- Treatment: Standard Peer Review Arena (reveal after round 1)
- Metric: Average final score difference

**Experiment 2: Same model vs. different models**
- Condition A: Both agents use the same LLM
- Condition B: Agent A uses model X, Agent B uses model Y
- Metric: Learning delta (round 2 - round 1 improvement)
- Hypothesis: Different models find different bugs, creating richer cross-review

**Experiment 3: Difficulty scaling**
- Run all three tasks with the same model
- Metric: Cross-review improvement delta by task difficulty
- Hypothesis: Harder tasks benefit more from cross-review (more to learn)

### Reproducibility

- Seed-based template selection ensures deterministic code generation
- Fixed grading criteria (line tolerance, keyword threshold) ensure consistent evaluation
- Mandatory `[START]`/`[STEP]`/`[END]` logging format enables automated result parsing

---

## 9. Future Directions

### N-Agent Scaling
Extend from 2 to N agents. Each agent sees a subset of others' findings (not all). Tournament-style matchmaking with Elo ratings could identify which agents learn best from cross-review.

### Heterogeneous Models
Pit different model families against each other. A code-specialized model (CodeLlama) vs. a general model (GPT-4) could reveal whether domain specialization helps or hurts cross-review learning.

### Adaptive Difficulty
Dynamically adjust bug count, subtlety, and template complexity based on agent performance. If an agent consistently scores >0.8, increase difficulty. This keeps the learning signal informative throughout training.

### Tournament Mode
Multiple episodes across different tasks, with cumulative scoring. Agents that perform well across all three difficulty levels demonstrate robust review capability, not just task-specific pattern matching.

### Real Codebases
Replace generated templates with real open-source code and known CVEs/bugs. This would test whether cross-review learning transfers to realistic code review scenarios. Challenge: establishing ground truth for real code is expensive.

### Persistent Memory
Allow agents to accumulate knowledge across episodes. An agent that learned about SQL injection in episode 1 should be better at finding it in episode 2. This requires extending the environment's state model to support cross-episode memory.

---

## References

- Du, Y., Li, S., Torralba, A., Tenenbaum, J.B., & Mordatch, I. (2024). "Improving Factuality and Reasoning in Language Models through Multiagent Debate." *ICML 2024*.
- MARTI Framework. (2026). "Multi-Agent Review and Targeted Iteration for Code Generation." *ICLR 2026*. Tsinghua University.
- Silver, D., et al. (2017). "Mastering the Game of Go without Human Knowledge." *Nature*.
- Rabinowitz, N., et al. (2018). "Machine Theory of Mind." *ICML 2018*.
- Lazaridou, A., et al. (2017). "Multi-Agent Cooperation and the Emergence of (Natural) Language." *ICLR 2017*.
