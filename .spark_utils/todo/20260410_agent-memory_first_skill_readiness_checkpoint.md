# Task: Agent Memory First Skill Preparation

Parent backlog: [20260410_agent-memory_first_skill_readiness_checkpoint.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260410_agent-memory_first_skill_readiness_checkpoint.md)

## Checklist
- [x] define the startup recall contract for the first skill
- [x] define the candidate review output format for the first skill
- [x] rewrite the skill as a CLI-first workflow that does not assume direct tool access
- [x] move detailed layer and policy examples into `references/examples.md`
- [x] install the skill under `/Users/adhuy/.codex/skills/agent-memory`
- [x] validate the installed skill from the Codex skill root
- [x] list explicit deferred items for the first skill

## Notes
- Current readiness estimate: `75-80%`
- The skill must reflect tested behavior, not planned behavior.
- Long-term writes remain review-first in the first skill.
- Repo source-of-truth is `skills/agent-memory/`.
- Codex install path is a symlink: `/Users/adhuy/.codex/skills/agent-memory` -> repo source-of-truth.
- The skill now carries the policy directly; `.spark_utils/data/20260410_coding_agent_usage_model.md` remains human-facing support material.
- The old `Default Path` section was removed.
- The old `What Not To Do` section was removed.
- Candidate review format remains the structured long-term review block.
