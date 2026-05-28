# HPDF Technical Design Specification — Workflow Guide

> **Version**: 1.1  
> **Maintained by**: HPDF Design Team  
> **Last updated**: 2026-05-26

This document defines how HPDF Technical Design Specification (TDS) documents are created, developed, reviewed, approved, and maintained — by human engineers and by LLM-assisted agents.

---

## 1. What is a TDS?

A Technical Design Specification records the *why* and *how* of a specific HPDF component or subsystem. It is the authoritative design record for that component and the primary artifact from which implementation work proceeds.

A TDS is **not** a requirements document (though it references requirements), a runbook (though it informs runbooks), or a meeting summary (though it absorbs decisions made in meetings).

### When to write a TDS

Write a TDS whenever:
- A new HPDF component or service is being designed
- An existing component is being substantially changed (interface, security model, or deployment topology)
- A design decision with multi-team implications needs to be recorded

A lightweight note or ADR (Architecture Decision Record) embedded in an existing TDS is sufficient for smaller decisions within an already-documented component.

### Granularity of TDS and recording decisions

In simple terms, a TDS document should be limited in scope and gravitate towards small granular descriptions rather than a single large document describing multiple complex components of a larger system. A TDS may begin with a larger scope, but limited amount of detail, and then be superseded by smaller detailed TDSs that focus on subsets of functionality or subcomponents of a given portion of a system previously described by a single TDS. This may typically happen as the design is refined. 

Relevant portions of the older TDS would be reflected in new multiple TDSs and the older ADRs distributed into the new documents according to scope of the new documents. A crosscheck should be performed to make sure previous ADRs are still respected in the updated design. If a conflict is identified and found to be deliberate, a new ADR can be created reflecting the new design decision, but it must reference the previous ADR. 

A TDS is typically written with a help of an LLM, but must be understandable by a human. 

---

## 2. Document Lifecycle

```
DRAFT ──► REVIEW ──► APPROVED
  ▲           │           │  │
  └───────────┘           │  ▼
  (revisions)             │  SUPERSEDED / DEPRECATED
  ▲                       │
  └───────────────────────┘
  (implementation gaps)
```

| Status | Meaning | Who sets it |
|---|---|---|
| `DRAFT` | Active authoring; may be incomplete | Owner |
| `REVIEW` | Author considers it ready; reviewers are commenting | Owner |
| `APPROVED` | All reviewers have signed off; no open questions remain | Owner (after all reviewer approvals) |
| `SUPERSEDED` | A newer TDS replaces this one; link to successor in frontmatter | Owner |
| `DEPRECATED` | Component retired; document kept for historical record | Owner |

### Transition gates

**DRAFT → REVIEW**
- All `[REQUIRED]` sections have material present (not necessarily complete)
- `tds validate <file.md>` passes with no errors (Mermaid syntax and image references clean)
- YAML frontmatter is complete (all required fields populated)

**REVIEW → APPROVED**
- Each named reviewer has confirmed approval (via comment in the DOCX in Google Drive, or explicit message)
- All open questions in §7 are resolved and incorporated inline
- Revision history updated with approval entry

**APPROVED → SUPERSEDED**
- The successor TDS references this doc's `doc_id` in its §8 (Related Documents)
- This doc's `status` field updated to `SUPERSEDED`

---

## 3. Document Naming and Registry

### File naming

```
HPDF_TDS_<NNNN>_<slug>.md
```

- `NNNN` — four-digit sequential ID assigned from the registry (see §3.2)
- `slug` — short lowercase kebab-case descriptor, e.g., `iam-token-service`, `data-catalog-api`

**Examples:**
```
HPDF_TDS_0001_iam-federation.md
HPDF_TDS_0042_transfer-engine.md
```

### TDS Registry

Maintain a file `TDS_REGISTRY.md` in this workspace with one row per TDS:

| Doc ID | Title | Owner | Component | Status | File |
|---|---|---|---|---|---|
| HPDF_TDS_0001 | IAM Federation Service | I. Baldin | IAM | DRAFT | HPDF_TDS_0001_iam-federation.md |
| HPDF_TDS_0002 | Data Catalog API | J. Smith | Data Catalog | REVIEW | HPDF_TDS_0002_data-catalog-api.md |

Assign the next available four-digit ID when a new TDS is created. The registry is the single source of truth for IDs — do not rely on file system ordering.

---

## 4. Owner Responsibilities

Each TDS has exactly one **owner**. The owner is:

- The engineer responsible for the correctness and completeness of the document
- The person who drives the document from DRAFT to APPROVED
- The long-term maintainer: they update the TDS when the design changes
- Accountable for closing open questions in §7

There is no co-ownership. Contributors and reviewers are listed separately in the frontmatter. If ownership must transfer, update the frontmatter and log the change in §10 (Revision History).

---

## 5. LLM and Agent Collaboration

LLM agents (Claude, GPT-4, Gemini, or others) are first-class collaborators in the HPDF TDS workflow. This section defines how to use them effectively and safely.

### 5.1 Roles an agent may perform

| Role | Description | Human gate required? |
|---|---|---|
| **Drafter** | Produces an initial DRAFT from conversation context, chat logs, or design notes | Yes — owner must review before sharing |
| **Section author** | Fills in specific sections (e.g., §3 Architecture, §4 Security) given context | Yes — owner reviews each section |
| **Reviewer** | Audits a TDS for internal consistency, missing sections, open questions, standards compliance | Owner reviews agent findings |
| **Updater** | Applies a targeted change to an existing TDS given a precise instruction | Yes — owner reviews the diff |
| **Renderer** | Runs pandoc to produce the DOCX for Google Drive distribution | No gate — purely mechanical |

An agent **may not** change document status (DRAFT → REVIEW → APPROVED). Only the human owner does that.

### 5.2 Prompting pattern for drafting a new TDS

When starting a new TDS with an LLM agent, provide:

1. **The template**: Owner uses `tds new` command to generate a new skeleton TDS from template. An agent with direct access to the system may offer the owner to do so on their behalf.
2. **Component context**: a short description of what the component does and where it fits in HPDF
3. **Source material**: relevant chat logs, meeting notes, prior documents, external specs
4. **Scope instruction**: which sections to fill in now vs. leave as placeholders

**Example prompt skeleton:**
```
Use the newly created HPDF_TDS_000X_<slug>.md to help me draft a TDS for the [component name].

Context:
- This component is responsible for [what it does]
- It sits at [layer/hub location/etc] and interfaces with [other components]
- The primary design challenge is [key problem]

Source material: [attach or paste relevant notes]

Fill in sections 1–4. Leave §7 (Open Questions), §8 (Decision Records), and §9 (Related Documents)
as placeholders — I will fill those in. 
```

### 5.3 Prompting pattern for targeted updates

When asking an agent to update an existing TDS:

```
Update HPDF_TDS_NNNN_<slug>.md as follows:
- Section [X.Y]: [precise description of the change]
- Reason: [why this change is being made]
- Do NOT modify any other sections.
- Add a row to §11 (Revision History): version [N+1], date today, author [name], summary [one line].
```

Always specify the section number, not a description like "the security section", to avoid ambiguity.

### 5.4 What agents must not do

- Create a new TDS themselves from the template - the new TDS must always be created by owner using `tds new`
- Resolve open questions in §6 by simply deleting them — unresolved questions must either be incorporated inline into the relevant section or remain in §6 with a clear explanation of why they are deferred
- Change the `status` field in frontmatter
- Remove content from §10 (Revision History)
- Invent requirements or constraints not present in the source material
- Produce a DOCX directly — always produce Markdown first; the owner renders to DOCX using `tds render`
- Declare a Mermaid diagram complete without running `tds validate` — see §5.6

### 5.6 Mermaid diagram validation (required for all agents)

Mermaid's grammar has lexer-level rules that are not obvious from prose or examples: certain punctuation characters (`;`) and Unicode symbols (`→`, `←`) are tokenized as operators and cannot appear in message labels or node text. LLMs reliably produce these errors.

**After writing or editing any Mermaid block, agents must run:**

```bash
tds validate <file.md> --check mermaid
```

A diagram is not complete until this command exits 0 for that block. The validate-and-fix loop is mandatory, not optional:

1. Write or edit the Mermaid block in the Markdown file.
2. Run `tds validate <file.md> --check mermaid`.
3. If any block reports `FAILED`, read the mmdc error, fix the offending line, and go back to step 2.
4. Only proceed to the next section once all blocks report `ok`.

Do not rely on `tds render` to surface diagram errors — render is slower and stops the pipeline. `tds validate` is fast and targeted.

### 5.5 Agent working in this Cowork project (Claude)

Claude (in this Cowork session) acts as a persistent design collaborator. It has access to:
- All TDS documents in this workspace folder
- Project memory from prior sessions (via the HPDF Design knowledge base)
- The TDS Registry

When working with Claude here:
- Ask Claude to "draft section X of TDS_NNNN" and it will read the file, make the targeted edit, and report what changed
- Ask Claude to "review TDS_NNNN for completeness" and it will check every `[REQUIRED]` section and list gaps
- Claude will never change document status without being explicitly told to

---

## 6. Rendering to DOCX

The Markdown file is the canonical source. DOCX is generated for distribution via Google Drive for reviewer comments.

### 6.1 Rendering command

```bash
tds render HPDF_TDS_NNNN_<slug>.md
```

Use the `tds` wrapper rather than invoking scripts or pandoc directly — it runs inside the Docker container and handles Mermaid pre-rendering, `.mmd` sidecar creation, engineer image validation, cover page insertion, and pandoc automatically. See `tds render --help` for all options including `--no-cover` (quick review renders) and `--ascii-art-font-size`.

Key rendering behaviours controlled by YAML frontmatter:
- `toc: true` — produces a table of contents.
- `numbersections: false` (default) — set to `true` to add section numbers to the DOCX.

See §6.2 for how each diagram format is handled.

### 6.2 Diagram handling

Three diagram formats are supported. Choose the one that fits the complexity and the tools available.

#### Option A — ASCII art

Embed directly in the Markdown as a fenced code block (no language tag, or `text`):

````markdown
```
Client ──► Service ──► Database
```
````

Pandoc renders this as a monospace code block in the DOCX. It is always legible but does not scale well for complex diagrams. Best suited for simple flow indicators or the lifecycle diagram in §2 of this document.

#### Option B — Mermaid

Write diagrams as ` ```mermaid ` fenced blocks in the Markdown source. The render pipeline handles everything automatically:

- `tds render` calls `mmdc` to render each block to a PNG and saves both the PNG and the Mermaid source as sidecars in `diagrams/`:
  - `diagrams/mmdc-<slug>-01.png` — embedded in the DOCX
  - `diagrams/mmdc-<slug>-01.mmd` — kept for round-trip recovery
- `tds unrender` reads the `.mmd` sidecars and re-inserts the original ` ```mermaid ` blocks, so the Markdown source stays authoritative after a review cycle.
- Pass `--nommdc` to `tds unrender` to keep diagrams as static PNG references instead of restoring fenced blocks.

No manual `mmdc` invocation or file management is required. Do not delete the `diagrams/mmdc-*` files — they are needed by `tds unrender`.

**Always validate Mermaid blocks before rendering** (see §5.6 for the required loop and common error patterns):

```bash
tds validate <file.md> --check mermaid
```

Common mistakes that cause mmdc parse errors:
- `;` in message labels — Mermaid treats it as a statement terminator; use `,` instead
- `→` / `←` in message labels or node text — Mermaid tokenizes them as arrow operators; use `->` in graph diagrams or plain words (`to`, `from`) in sequence diagrams

#### Option C — Engineer-authored PNG

If a diagram was created in an external tool (draw.io, Visio, Lucidchart, PowerPoint, etc.), export it as a PNG and reference it directly:

```markdown
![Caption](diagrams/HPDF_TDS_NNNN_figure-name.png)
```

Store PNGs in a `diagrams/` subdirectory alongside the TDS file. Name them `HPDF_TDS_NNNN_<descriptor>.png` to keep them associated with their document. Pandoc embeds PNGs into the DOCX natively — no pre-processing needed. If the source file (`.drawio`, `.vsdx`, etc.) exists, commit it alongside the PNG so the diagram remains editable.

#### Choosing between options

| Situation | Recommended option |
|---|---|
| Simple flow, lifecycle, or state diagram | B (Mermaid) — keeps source in the MD file |
| Complex multi-layer architecture diagram | C (PNG from external tool) |
| Quick inline annotation, no tooling available | A (ASCII art) |
| LLM agent is generating the diagram | B (Mermaid) |

### 6.3 Google Drive distribution

After rendering, upload the DOCX to the shared Google Drive folder and notify reviewers. Reviewer comments in Google Drive must be addressed in the Google Doc by the maintainer. In addition to comments it is acceptable for reviewers to use 'Suggestion' mode to propose changes. 

### 6.4 Transferring back to MD

Once comments have been addressed and the Google Doc is consistent with reviewer expectations, download the DOCX from Google Drive and run:

```bash
tds unrender HPDF_TDS_NNNN_<slug>.docx
```

This strips the cover page and TOC, restores Mermaid blocks from the `.mmd` sidecars in `diagrams/`, recovers YAML frontmatter from the original `.md`, and applies all round-trip cleanup passes. The output overwrites (after backing up) the original `.md` source file.

Do **not** use Google Doc's File → Download → Markdown — it does not restore Mermaid blocks, YAML frontmatter, or HPDF-specific formatting.

---

## 7. Review Process

### 7.1 Requesting review

When the owner sets status to `REVIEW`:
1. Render the DOCX and upload to Google Drive
2. Notify reviewers (email / Slack / issue tracker) with a link to the DOCX and a review deadline
3. Open a tracking issue (if using an issue tracker) to collect sign-offs

### 7.2 Reviewer responsibilities

Reviewers should check:
- Technical correctness of the design
- Add or help address open questions
- Provide feedback on the state of readiness of the document - whether it can be finalized or needs to go back for additional work. 

Reviewers provide comments in the Google Drive DOCX. The owner consolidates feedback into Google Drive DOCX, converts back to markdown when a version is completed, does another pass over the MD doc (with help from LLM) then converts back to DOCX and requests re-review.

### 7.3 Sign-off

When all reviewers' concerns have been addressed and the team agrees the document is in the ready state, it is finalized into the APPROVED state. 

It is acceptable to return the document back into the DRAFT phase if after reaching APPROVED and e.g. in the process of implementation certain aspects of the design were found to be lacking. 

---

## 8. Maintenance

A TDS is a living document while the component it describes is active.

- **Minor updates** (typo, clarifying prose, adding a decision record): owner updates directly, bumps the patch version (e.g., 1.0 → 1.0.1), adds a revision history row
- **Significant changes** (interface change, new sub-component, security model change): bump the minor version (e.g., 1.0 → 1.1), return to REVIEW status, notify reviewers
- **Breaking / superseding changes**: create a new TDS, link the old one as SUPERSEDED

When a component is retired, set status to `DEPRECATED`, add a final revision history row, and update the TDS Registry.

---

## 9. Quick-Reference Checklist

### Starting a new TDS

- [ ] Run `tds new "<Title>" --owner "I. Baldin"` — assigns the next ID, creates the file from the template, and adds the registry row automatically
- [ ] Fill in the content sections (with or without LLM agent assistance)
- [ ] Verify YAML frontmatter (status should be DRAFT)
- [ ] After writing or editing any Mermaid diagram, run `tds validate <file.md> --check mermaid` and fix all errors before moving on (see §5.6)

### Moving to REVIEW

- [ ] All `[REQUIRED]` sections have material present (not necessarily complete)
- [ ] Run `tds validate <file.md>` — must pass with no errors (Mermaid syntax and image references)
- [ ] Run `tds render <file.md>` — must succeed without errors
- [ ] Upload DOCX to Google Drive and notify reviewers

### Moving to APPROVED

- [ ] Team approved the transition
- [ ] §7 is empty (all questions resolved)
- [ ] frontmatter `status` changed to `APPROVED`
- [ ] TDS Registry updated
- [ ] Final DOCX rendered and uploaded to Google Drive

---

*End of HPDF TDS Workflow Guide*
