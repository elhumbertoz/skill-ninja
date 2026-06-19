# Agent Skills — Reference knowledge

> Source: https://agentskills.io (Overview, Specification, Quickstart, Best Practices, Optimizing Descriptions).
> Collected: 2026-06-19.

---

## 1. What are Agent Skills?

**Agent Skills** are an open, lightweight format for extending the capabilities of AI agents with specialized knowledge and workflows.

At its core, a *skill* is a **folder containing a `SKILL.md` file**. That file includes metadata (`name` and `description` at minimum) and instructions that tell the agent how to perform a specific task. A skill can also bundle scripts, reference material, templates, and other resources.

```
my-skill/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
├── assets/           # Optional: templates, resources
└── ...               # Any other file or directory
```

The format was **originally developed by Anthropic**, released as an open standard, and adopted by a growing number of agent products. The standard is open to community contributions (GitHub: `agentskills/agentskills`, and Discord).

---

## 2. Why use Agent Skills?

Agents are increasingly capable but often lack the context to work reliably. Skills solve this by packaging procedural knowledge and specific context (company, team, or user) into portable, versioned folders that the agent loads on demand. This gives the agent:

- **Domain expertise:** captures specialized knowledge — from legal review processes to data-analysis pipelines or presentation formatting — as reusable instructions and resources.
- **Repeatable workflows:** turns multi-step tasks into consistent, auditable procedures.
- **Cross-product reuse:** build a skill once and use it in any agent compatible with the format.

---

## 3. How do they work? — Progressive Disclosure

Agents load skills **progressively**, in three stages, to keep context consumption low:

1. **Discovery:** at startup, the agent loads only each available skill's `name` and `description` (~100 tokens) — just enough to know when it might be relevant.
2. **Activation:** when a task matches a skill's `description`, the agent reads the full body of `SKILL.md` into context (<5000 tokens recommended).
3. **Execution:** the agent follows the instructions and, optionally, runs bundled code or loads referenced files as needed (on demand).

Full instructions load only when the task requires them, so the agent can have many skills available with a minimal context footprint.

| Level | Content | Approx. size | When loaded |
|-------|---------|--------------|-------------|
| Metadata | `name` + `description` | ~100 tokens | At startup, for all skills |
| Instructions | Body of `SKILL.md` | <5000 tokens (rec.) | When the skill activates |
| Resources | `scripts/`, `references/`, `assets/` | Variable | Only when needed |

---

## 4. Format specification

### 4.1 Directory structure

A skill is a directory containing, at minimum, a `SKILL.md` file. The subdirectories (`scripts/`, `references/`, `assets/`) are optional.

### 4.2 `SKILL.md` format

`SKILL.md` must contain **YAML frontmatter** followed by **Markdown content**.

#### Frontmatter fields

| Field | Required | Constraints |
|-------|----------|-------------|
| `name` | **Yes** | Max 64 chars. Lowercase letters, numbers, and hyphens only. No leading/trailing hyphen. |
| `description` | **Yes** | Max 1024 chars. Non-empty. Describes what the skill does and when to use it. |
| `license` | No | License name or a reference to an included license file. |
| `compatibility` | No | Max 500 chars. States environment requirements (product, packages, network, etc.). |
| `metadata` | No | Arbitrary key-value map for additional metadata. |
| `allowed-tools` | No | Space-separated string of pre-approved tools. (Experimental) |

#### `name` field

- Must be between 1 and 64 characters.
- Lowercase unicode alphanumeric characters (`a-z`, `0-9`) and hyphens (`-`) only.
- Cannot start or end with a hyphen.
- Cannot contain consecutive hyphens (`--`).
- **Must match the parent directory name.**

```yaml
# Valid
name: pdf-processing
name: data-analysis
name: code-review

# Invalid
name: PDF-Processing   # uppercase not allowed
name: -pdf             # cannot start with a hyphen
name: pdf--processing  # consecutive hyphens not allowed
```

#### `description` field

- Must be between 1 and 1024 characters.
- Must describe **what** the skill does and **when** to use it.
- Must include specific keywords that help the agent identify relevant tasks.

```yaml
# Good
description: Extracts text and tables from PDF files, fills PDF forms, and merges multiple PDFs. Use when working with PDF documents or when the user mentions PDFs, forms, or document extraction.

# Poor
description: Helps with PDFs.
```

#### `license` field

Specifies the skill's license. Recommended to keep it short.

```yaml
license: Proprietary. LICENSE.txt has complete terms
```

#### `compatibility` field

Between 1 and 500 characters. Include only if the skill has specific environment requirements. Most skills don't need it.

```yaml
compatibility: Designed for Claude Code (or similar products)
compatibility: Requires git, docker, jq, and access to the internet
compatibility: Requires Python 3.14+ and uv
```

#### `metadata` field

A map of string keys to string values. Use reasonably unique key names to avoid conflicts.

```yaml
metadata:
  author: example-org
  version: "1.0"
```

#### `allowed-tools` field (Experimental)

Space-separated string of pre-approved tools. Support varies across implementations.

```yaml
allowed-tools: Bash(git:*) Bash(jq:*) Read
```

#### Complete examples

```markdown
---
name: skill-name
description: A description of what this skill does and when to use it.
---
```

```markdown
---
name: pdf-processing
description: Extract PDF text, fill forms, merge files. Use when handling PDFs.
license: Apache-2.0
metadata:
  author: example-org
  version: "1.0"
---
```

### 4.3 `SKILL.md` body

The Markdown after the frontmatter contains the instructions. There are no formatting restrictions. Recommended sections:

- Step-by-step instructions.
- Examples of inputs and outputs.
- Common edge cases.

The agent loads the **entire** file when activating the skill → split long content into referenced files. **Keep `SKILL.md` under 500 lines / 5000 tokens.**

### 4.4 Optional directories

- **`scripts/`** — executable code. Should be self-contained or document its dependencies, include helpful error messages, and handle edge cases. Languages depend on the implementation (Python, Bash, JavaScript are common).
- **`references/`** — additional documentation the agent reads when needed (`REFERENCE.md`, `FORMS.md`, domain files like `finance.md`, `legal.md`). Keep files small and focused.
- **`assets/`** — static resources: templates, images, data files (lookup tables, schemas).

### 4.5 File references

Use relative paths from the skill root. Keep references **one level deep** from `SKILL.md`; avoid deeply nested reference chains.

```markdown
See [the reference guide](references/REFERENCE.md) for details.

Run the extraction script:
scripts/extract.py
```

### 4.6 Validation

Use the reference library [`skills-ref`](https://github.com/agentskills/agentskills/tree/main/skills-ref):

```bash
skills-ref validate ./my-skill
```

It checks that the frontmatter is valid and follows the naming conventions.

---

## 5. Quickstart — Create your first skill

Example: a skill that rolls dice using a random number generator.

VS Code looks for skills in `.agents/skills/` by default. Create `.agents/skills/roll-dice/SKILL.md`:

````markdown
---
name: roll-dice
description: Roll dice using a random number generator. Use when asked to roll a die (d6, d20, etc.), roll dice, or generate a random dice roll.
---

To roll a die, use the following command that generates a random number from 1
to the given number of sides:

```bash
echo $((RANDOM % <sides> + 1))
```

```powershell
Get-Random -Minimum 1 -Maximum (<sides> + 1)
```

Replace `<sides>` with the number of sides on the die (e.g., 6 for a standard
die, 20 for a d20).
````

**Test it (in VS Code + GitHub Copilot):**
1. Open the project in VS Code.
2. Open the Copilot Chat panel.
3. Select **Agent** mode.
4. Type `/skills` to confirm that `roll-dice` appears in the list.
5. Ask: **"Roll a d20"**.

> Note: tool-use reliability varies across models. If the agent responds without running the command, try a different model.

**Skill location:** varies by client — it may be a skills directory, a config file, or a CLI flag. (In the VS Code quickstart: `.agents/skills/`.)

---

## 6. Best practices for creating skills

### 6.1 Start from real experience
- **Avoid** asking an LLM to generate a skill from its general knowledge alone → it produces vague, generic procedures.
- **Extract from a real task:** complete a real task with the agent, then extract the reusable pattern. Pay attention to: steps that worked, corrections you made, input/output formats, and project-specific context you provided.
- **Synthesize from existing artifacts:** internal docs, runbooks, style guides, API specs/schemas, code-review comments, version-control history (patches and fixes), and real failure cases and their resolution. The key is **project-specific** material, not generic references.

### 6.2 Refine with real execution
- Run the skill on real tasks and feed **all** the results (not just failures) back into the creation process.
- Ask yourself: what triggered false positives? what was missed? what can be trimmed?
- Read the **execution traces**, not just the final outputs. If the agent wastes time: instructions too vague, instructions that don't apply to the task, or too many options without a clear default.

### 6.3 Spend context wisely
- **Add what the agent doesn't know, omit what it already knows.** Don't explain what a PDF is or how HTTP works. Focus on project conventions, domain procedures, non-obvious edge cases, and the specific APIs/tools to use.
- For each piece of content ask: *"Would the agent get this wrong without this instruction?"* If not, cut it.
- **Design coherent units:** like deciding what a function does. Neither too narrow (forces loading several skills) nor too broad (hard to trigger precisely).
- **Aim for moderate detail:** a concise step-by-step guide with one working example beats exhaustive documentation.
- **Structure large skills with progressive disclosure:** move reference material to `references/` and tell the agent **when** to load each file (e.g.: *"Read `references/api-errors.md` if the API returns a non-200 status"*).

### 6.4 Calibrate control
- **Match specificity to task fragility.**
- **Give freedom** when several approaches are valid: explain the *why* instead of giving rigid directives.
- **Be prescriptive** when operations are fragile or require an exact sequence (e.g.: database migration commands that must not be modified).
- **Give defaults, not menus:** pick a default option and mention alternatives briefly, rather than presenting them as equals.
- **Favor procedures over declarations:** teach *how to approach* a class of problems, not *what to produce* for a specific case (reusable method > specific answer).

### 6.5 Patterns for effective instructions
- **"Gotchas" sections:** environment-specific facts that contradict reasonable assumptions (e.g.: the `users` table uses soft deletes → filter `WHERE deleted_at IS NULL`). Keep these in `SKILL.md`. **When you correct an agent's mistake, add the correction here.**
- **Templates for output format:** more reliable than describing the format in prose (agents pattern-match against concrete structures). Short ones in `SKILL.md`; long ones in `assets/`.
- **Checklists for multi-step workflows:** help avoid skipping steps with dependencies or validation gates.
- **Validation loops:** do the work → run a validator → fix → repeat until it passes.
- **Plan-validate-execute:** for batch or destructive operations, generate a structured intermediate plan, validate it against a source of truth, and only then execute.
- **Package reusable scripts:** if the agent reinvents the same logic on every run, write a tested script once and store it in `scripts/`.

---

## 7. Optimizing the `description` (triggering)

The `description` carries all the triggering weight: the agent decides whether to load the skill based on it. Too narrow → it won't trigger when it should; too broad → it triggers when it shouldn't.

**Key nuance:** agents usually only consult skills for tasks requiring knowledge or capabilities beyond what they can do alone. A simple one-step request ("read this PDF") may not trigger a skill even if the description matches.

### 7.1 How to write good descriptions
- **Imperative phrasing:** "Use this skill when..." instead of "This skill does...".
- **Focus on user intent, not implementation.**
- **Be "pushy":** list contexts where it applies, even when the user doesn't name the domain directly (*"even if they don't explicitly mention 'CSV' or 'analysis.'"*).
- **Be concise:** from a few sentences to a short paragraph. Hard limit of 1024 characters.

### 7.2 Design evaluation queries (eval)
- Create ~20 realistic prompts labeled with `should_trigger` (8-10 that should trigger, 8-10 that shouldn't).
- **Should-trigger:** vary phrasing (formal/casual/with typos), explicitness (whether they name the domain), detail, and complexity (1 step vs multi-step). The most useful are where the skill would help but the connection isn't obvious.
- **Should-not-trigger:** the most valuable are **near-misses** (share keywords but need something different), not obviously irrelevant examples.
- **Realism:** include file paths, personal context, specific details, casual language, and typos.

```json
[
  { "query": "I've got a spreadsheet in ~/data/q4_results.xlsx with revenue in col C and expenses in col D — can you add a profit margin column and highlight anything under 10%?", "should_trigger": true },
  { "query": "whats the quickest way to convert this json file to yaml", "should_trigger": false }
]
```

### 7.3 Test triggering
- Run each query through the agent with the skill installed and observe whether it invokes it (via the client's logs/observability).
- **Run multiple times** (3 is reasonable) and compute the **trigger rate**. A should-trigger query passes if its trigger rate exceeds a threshold (0.5 by default); a should-not-trigger passes if it's below.

### 7.4 Avoid overfitting (train/validation split)
- **Train (~60%):** identify failures and guide improvements.
- **Validation (~40%):** only to check that the improvements generalize.
- Keep a proportional mix of positives/negatives in both sets and fix the split across iterations.

### 7.5 Optimization loop
1. **Evaluate** the current description on train and validation.
2. **Identify failures** in the train set (what didn't trigger / what over-triggered).
3. **Revise the description:** if triggers are missing → broaden the scope; if there are false triggers → add specificity and draw boundaries. **Don't add keywords specific to failed queries** (overfitting) → address the general category/concept. Stay under 1024 characters.
4. **Repeat** until the train set passes or there's no improvement.
5. **Select the best iteration by its validation rate** (may not be the last).

~5 iterations usually suffice. If it doesn't improve, the problem may be in the queries (too easy/hard/mislabeled).

```yaml
# Before
description: Process CSV files.

# After
description: >
  Analyze CSV and tabular data files — compute summary statistics,
  add derived columns, generate charts, and clean messy data. Use this
  skill when the user has a CSV, TSV, or Excel file and wants to
  explore, transform, or visualize the data, even if they don't
  explicitly mention "CSV" or "analysis."
```

> The [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) skill automates this loop end to end (split, parallel evaluation, Claude-proposed improvements, and a live HTML report).

---

## 8. Where can they be used? (Compatible clients)

The Agent Skills format is supported by numerous agentic tools and clients. Some from the official showcase:

- **Coding agents / CLIs:** Claude Code, OpenAI Codex, Gemini CLI, OpenCode, Amp, Goose, Roo Code, Factory, Autohand Code CLI, Mistral AI Vibe, VT Code, Command Code, pi, Tabnine.
- **IDEs / editors:** Cursor, VS Code (GitHub Copilot), Kiro, TRAE, Firebender (Android), Junie (JetBrains).
- **Cloud / multi-agent platforms:** OpenHands, Mux, Ona, Superconductor, Emdash, Workshop, Letta, Piebald, Qodo.
- **Data platforms:** Databricks Genie Code, Snowflake Cortex Code.
- **Frameworks / other:** Spring AI, Laravel Boost, fast-agent, bub, nanobot, Agentman, Vita, Google AI Edge Gallery.

> Note: the default skill location and how to register them varies by client (directory, config file, or CLI flag). Check each product's documentation.

---

## 9. Official skill repositories

Yes — Anthropic published an **official, public** repository of skills, freely accessible.

### 9.1 `anthropics/skills` — example skills catalog

- URL: https://github.com/anthropics/skills
- License: mostly **Apache 2.0** (some skills are *source-available*).
- It's the reference implementation and demonstration of what's possible with Claude's skills system.
- **Anthropic notice:** the skills are offered for **demonstration and education**; test them well before using them in critical tasks.

**Included categories:**
- **Document Skills** — PDF, DOCX, PPTX, XLSX handling (*source-available*, used in production).
- **Creative & Design** — art, music, design.
- **Development & Technical** — web app testing, MCP server generation.
- **Enterprise & Communication** — communications and brand/branding workflows.

**Resources inside the repo:**
- Template: https://github.com/anthropics/skills/tree/main/template
- Format specification: https://github.com/anthropics/skills/blob/main/spec/agent-skills-spec.md
- `skill-creator` skill (automates the description-optimization loop): https://github.com/anthropics/skills/tree/main/skills/skill-creator

**How to access / install:**

```bash
# Claude Code — register as a plugin marketplace
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
/plugin install example-skills@anthropic-agent-skills
```

- **Claude.ai:** upload custom skills via the web interface (paid plans).
- **Claude API:** use prebuilt or custom skills via the Skills Guide.

### 9.2 `agentskills/agentskills` — open standard

- URL: https://github.com/agentskills/agentskills
- Contains the **specification and documentation of the open standard** (backs agentskills.io). Distinct from the examples catalog.
- Includes the `skills-ref` validation library: https://github.com/agentskills/agentskills/tree/main/skills-ref

### 9.3 Anthropic support guides

- What are skills?: https://support.claude.com/en/articles/12512176-what-are-skills
- Creating custom skills: https://support.claude.com/en/articles/12512198-creating-custom-skills

---

## 10. Reference links

- Site / docs: https://agentskills.io
- Docs index (for LLMs): https://agentskills.io/llms.txt
- Specification: https://agentskills.io/specification
- Quickstart: https://agentskills.io/skill-creation/quickstart
- Best practices: https://agentskills.io/skill-creation/best-practices
- Optimizing descriptions: https://agentskills.io/skill-creation/optimizing-descriptions
- Evaluating skills: https://agentskills.io/skill-creation/evaluating-skills
- Using scripts: https://agentskills.io/skill-creation/using-scripts
- Client showcase: https://agentskills.io/clients
- `skills-ref` validation library: https://github.com/agentskills/agentskills/tree/main/skills-ref
- Example skills (Anthropic): https://github.com/anthropics/skills
- Community: GitHub `agentskills/agentskills` · Discord
