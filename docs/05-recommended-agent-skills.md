---
title: Recommended Agent Skills for the Project
status: researched
last_updated: 2026-09-14
owners: maintainers
---

# Recommended skills

## Installation status

All eight recommended skills below were installed and verified locally on 2026-09-14 under `~/.codex/skills`: `frontend-design`, `vercel-react-best-practices`, `writing-plans`, `playwright-best-practices`, `tdd`, `verification-before-completion`, `requesting-code-review`, and `differential-review`. They become available to new Codex turns after installation. The optional `mantis-threat-model` skill was not installed.

These are the smallest useful set I would adopt. Popularity is a discovery signal, not proof of quality; counts are marketplace-reported snapshots from 2026-09-14 and will change. Inspect each `SKILL.md`, scripts, and requested permissions before installation. SkillsMP itself says its GitHub index does not certify quality or safety ([source](https://skillsmp.com/)).

| Skill | What it adds | Why it fits this project | Popularity snapshot | Link / install |
|---|---|---|---|---|
| **frontend-design** (`anthropics/skills`) | Intentional visual direction and production-grade UI patterns. | The review queue needs excellent hierarchy, collapsible sections, confidence/evidence display, batch selection, and non-generic interaction design. | **885.4K installs**, **176.1K repo stars** on skills.sh; also **#5 / 5,367 views** on SkillHub. | [skills.sh](https://www.skills.sh/anthropics/skills/frontend-design) · `npx skills add https://github.com/anthropics/skills --skill frontend-design` |
| **vercel-react-best-practices** (`vercel-labs/agent-skills`) | Prioritized React guidance for data fetching, rendering, bundles, and rerenders. | Still useful for the React/Vite review UI, scan progress, and large candidate lists; its Next.js-specific advice does not apply to the adopted Python backend. | **711.6K installs**, **31.2K repo stars** on skills.sh. | [skills.sh](https://www.skills.sh/vercel-labs/agent-skills/vercel-react-best-practices) · `npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices` |
| **writing-plans** (`obra/superpowers`) | Turns specs into small, file-specific, testable implementation steps with checkpoints. | Converts the four planning documents into contributor-sized issues and keeps security-sensitive executor work behind explicit dependencies and verification. Use its plan structure selectively; its default subagent-review requirement may be unnecessary for solo contributions. | **247.8K installs**, **286.2K repo stars** on skills.sh. | [skills.sh](https://www.skills.sh/obra/superpowers/writing-plans) · `npx skills add https://github.com/obra/superpowers --skill writing-plans` |
| **playwright-best-practices** (`currents-dev/playwright-best-practices-skill`) | Playwright selectors, isolation, OAuth/third-party mocking, retries, CI, accessibility, and security-oriented test patterns. | The project uses Playwright both as a product fallback and for E2E tests; this helps keep those two contexts isolated and reduces flaky or unsafe browser flows. | **82.3K installs**, **377 repo stars** on skills.sh. | [skills.sh](https://www.skills.sh/currents-dev/playwright-best-practices-skill/playwright-best-practices) · `npx skills add https://github.com/currents-dev/playwright-best-practices-skill --skill playwright-best-practices` |

## Recommendation

Start with **frontend-design**, **vercel-react-best-practices**, and **playwright-best-practices** for implementation. Add **writing-plans** when turning V1 slices into issues. I would not install the low-adoption `agent-architect` result found on SkillsMP (3 GitHub stars), and I would avoid a broad multi-agent framework for V1: the design deliberately uses one orchestrator until traces and evals show that extra agents are warranted.

## Development, review, and risk additions

| Skill | What it adds | Why it fits this project | Popularity snapshot | Link / install |
|---|---|---|---|---|
| **tdd** (`mattpocock/skills`) | Vertical red-green-refactor slices and behavior-focused tests through public interfaces. | Well suited to the parser, URL policy, grouping, action state machine, and fake unsubscribe server. These are risky boundaries where tests should survive internal refactors. | **899.7K installs**, **261.2K repo stars**; all three marketplace security audits pass. | [skills.sh](https://www.skills.sh/mattpocock/skills/tdd) · `npx skills add https://github.com/mattpocock/skills --skill tdd` |
| **verification-before-completion** (`obra/superpowers`) | Requires fresh test/build evidence before an agent claims work is complete. | A useful release gate for OAuth, URL validation, and unsubscribe actions, where “looks right” is not enough. | **209.8K installs**, **286.2K repo stars**; all three marketplace security audits pass. | [skills.sh](https://www.skills.sh/obra/superpowers/verification-before-completion) · `npx skills add https://github.com/obra/superpowers --skill verification-before-completion` |
| **requesting-code-review** (`obra/superpowers`) | Sends a bounded diff and requirements to a fresh reviewer and ranks findings by severity. | Adds an independent spec/correctness pass before merging sensitive slices. It is preferable here to the more popular `mattpocock/code-review`, whose current skills.sh page reports Gen Agent Trust Hub **Warn** and Snyk **Fail**. | **227.6K installs**, **286.2K repo stars**; all three marketplace security audits pass. | [skills.sh](https://www.skills.sh/obra/superpowers/requesting-code-review) · `npx skills add https://github.com/obra/superpowers --skill requesting-code-review` |
| **differential-review** (`trailofbits/skills`) | Evidence-based, risk-first security review of PRs, commits, and diffs. | Directly targets the project’s dangerous surfaces: OAuth/token handling, untrusted email HTML, prompt injection, outbound URLs/SSRF, and browser automation. Use after code exists, especially for slices 2, 3, 8, and 9. | **6.5K installs**, **7.1K repo stars**; all three marketplace security audits pass. | [skills.sh](https://www.skills.sh/trailofbits/skills/differential-review) · `npx skills add https://github.com/trailofbits/skills --skill differential-review` |

For design-time threat analysis, **mantis-threat-model** from `google/mantis` is the most credible candidate I found, but it currently has only **905 installs / 941 repo stars** and requires its own knowledge-base workflow. Treat it as an optional later addition, not a V1 prerequisite: [details](https://www.skills.sh/google/mantis/mantis-threat-model).

### Suggested minimal stack by phase

- **Plan:** `writing-plans`
- **Build:** `frontend-design`, `vercel-react-best-practices`, `tdd`
- **Verify:** `playwright-best-practices`, `verification-before-completion`
- **Review sensitive changes:** `requesting-code-review`, then `differential-review`

SkillHub provides quality grades and view counts, while skills.sh reports aggregate CLI installs; those numbers are not directly comparable. The skills.sh leaderboard is backed by anonymous install telemetry ([methodology](https://www.skills.sh/docs/faq)); SkillHub says its AI score evaluates instruction quality and security signals but does not prove runtime performance ([methodology summary](https://www.skillhub.club/)).
