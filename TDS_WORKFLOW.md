# HPDF Technical Design Specification — Workflow Guide

> **Version**: 1.0  
> **Maintained by**: HPDF Design Team  
> **Last updated**: 2026-05-21

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

Relevant portions of the older TDS would be reflected in new multiple TDSs and the older ADRs distributed into the new documents according to scope of the new documents. A crosscheck should be performed to make sure previous ADRs are still respected in the updated design. If a conflict is identified and found to be deliberate, a new ADR can be created reflecting the new design decision, but it must reference the previous ADR 

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
- All Mermaid diagrams render correctly
- YAML frontmatter is complete (`reviewers` list populated)

**REVIEW → APPROVED**
- Each named reviewer has confirmed approval (via comment in the DOCX in Google Drive, or explicit message)
- All open questions in §6 are resolved and incorporated inline
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
| HPDF_TDS_0001 | IAM Federation Service | I. Baldin, JLab | IAM | DRAFT | HPDF_TDS_0001_iam-federation.md |
| HPDF_TDS_0002 | Data Catalog API | J. Smith, LBNL | Data Catalog | REVIEW | HPDF_TDS_0002_data-catalog-api.md |

Assign the next available four-digit ID when a new TDS is created. The registry is the single source of truth for IDs — do not rely on file system ordering.

---

## 4. Owner Responsibilities

Each TDS has exactly one **owner**. The owner is:

- The engineer responsible for the correctness and completeness of the document
- The person who drives the document from DRAFT to APPROVED
- The long-term maintainer: they update the TDS when the design changes
- Accountable for closing open questions in §6

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

1. **The template**: point the agent to `TDS_TEMPLATE.md`
2. **Component context**: a short description of what the component does and where it fits in HPDF
3. **Source material**: relevant chat logs, meeting notes, prior documents, external specs
4. **Scope instruction**: which sections to fill in now vs. leave as placeholders

**Example prompt skeleton:**
```
Using TDS_TEMPLATE.md as the template, draft a TDS for the [component name].

Context:
- This component is responsible for [what it does]
- It sits at [layer/hub location/etc] and interfaces with [other components]
- The primary design challenge is [key problem]

Source material: [attach or paste relevant notes]

Fill in sections 1–4. Leave §6 (Open Questions), §7 (Decision Records), and §8 (Related Documents)
as placeholders — I will fill those in. Assign doc_id HPDF_TDS_XXXX for now.
```

### 5.3 Prompting pattern for targeted updates

When asking an agent to update an existing TDS:

```
Update HPDF_TDS_NNNN_<slug>.md as follows:
- Section [X.Y]: [precise description of the change]
- Reason: [why this change is being made]
- Do NOT modify any other sections.
- Add a row to §10 (Revision History): version [N+1], date today, author [name], summary [one line].
```

Always specify the section number, not a description like "the security section", to avoid ambiguity.

### 5.4 What agents must not do

- Resolve open questions in §6 by simply deleting them — unresolved questions must either be incorporated inline into the relevant section or remain in §6 with a clear explanation of why they are deferred
- Change the `status` field in frontmatter
- Remove content from §10 (Revision History)
- Invent requirements or constraints not present in the source material
- Produce a DOCX directly — always produce Markdown first; the owner renders to DOCX

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

### 6.1 Pandoc command

```bash
python3 scripts/tds_render.py HPDF_TDS_NNNN_<slug>.md [--reference-doc hpdf-reference.docx]
```

Use `tds_render.py` rather than invoking pandoc directly — the script handles Mermaid pre-rendering, engineer image validation, and cleanup automatically. The underlying pandoc call it runs is:

```bash
pandoc HPDF_TDS_NNNN_<slug>.md \
  -o HPDF_TDS_NNNN_<slug>.docx \
  --toc \
  -f markdown+yaml_metadata_block \
  [--reference-doc hpdf-reference.docx]
```

- `hpdf-reference.docx` — a reference style document with HPDF heading styles, fonts, and page layout. Create this once and commit it alongside the TDS files.
- `--toc` matches the `toc: true` frontmatter field and produces a table of contents.
- Section numbering is **off by default** (`numbersections: false` in frontmatter). Set `numbersections: true` in a document's frontmatter to enable it for that document.
- Diagrams must be in PNG form before running pandoc — see §6.2 for how each diagram format is handled.

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

Write diagrams as ` ```mermaid ` fenced blocks in the Markdown source. Pandoc does not render Mermaid natively, so they must be pre-rendered to PNG before running pandoc.

**Pre-rendering with `mmdc`:**

```bash
# Install once:
npm install -g @mermaid-js/mermaid-cli

# Render each diagram:
mmdc -i diagram.mmd -o diagram.png -t neutral
```

Then replace the fenced block with a standard image reference before running pandoc:

```markdown
![Caption](diagram.png)
```

Keep the original `.mmd` source files alongside the TDS — they are the editable source and must be updated whenever the diagram changes. When converting the DOCX back to Markdown (§6.4), restore the `.mmd` fenced block and remove the PNG reference so the Markdown source stays authoritative.

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

Once the comments have been addressed and the Google Doc text is consistent with reviewer expectations, the maintainer uses pandoc to convert the file back into MD format. Using Google Doc option File->Download->Md is acceptable assuming it produces satisfactory results preserving original formatting and diagrams. 

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

- [ ] Assign ID from `TDS_REGISTRY.md`
- [ ] Copy `TDS_TEMPLATE.md` to `HPDF_TDS_NNNN_<slug>.md`
- [ ] Fill in YAML frontmatter (status: DRAFT)
- [ ] Add registry row
- [ ] Begin drafting (with or without LLM agent assistance)

### Moving to REVIEW

- [ ] All `[REQUIRED]` sections have material present (not necessarily complete)
- [ ] Render DOCX and upload to Google Drive
- [ ] Notify reviewers

### Moving to APPROVED

- [ ] Team approved the transition
- [ ] §6 is empty (all questions resolved)
- [ ] frontmatter `status` changed to `APPROVED`
- [ ] TDS Registry updated
- [ ] Final DOCX rendered and uploaded to Google Drive

---

*End of HPDF TDS Workflow Guide*
