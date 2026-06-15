---
name: linked-intent-dev
description: Start or continue the Linked-Intent Development workflow — design before code (HLD → LLD → EARS → Tests → Code). Use for new features, large changes, or when bootstrapping LID on a fresh project.
---

Invoke the `linked-intent-dev` skill. On a fresh project (no `docs/high-level-design.md`), describe what you want to build — the skill bootstraps LID inline as part of Phase 1. On an established project, the skill walks the next change through the six-phase workflow with mandatory stops at each phase boundary. See `.claude/skills/linked-intent-dev/SKILL.md` for the full behavior.
