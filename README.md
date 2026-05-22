# HPDF TDS Tools

Command-line tools for rendering and round-tripping HPDF Technical Design
Specification documents between Markdown and DOCX.

## What it does

| Command | What happens |
|---|---|
| `tds render <file.md>` | Renders a TDS Markdown source to a styled DOCX with cover page, DOE disclaimer, TOC, and Mermaid diagrams |
| `tds unrender <file.docx>` | Converts a reviewed DOCX back to Markdown, restoring Mermaid blocks and YAML frontmatter |

All conversion logic runs inside a Docker container — pandoc, Mermaid CLI, and
python-docx are bundled in the image. The only local dependency is Docker.

## Prerequisites

Docker Desktop, [Colima](https://github.com/abiosoft/colima), or any
Docker-compatible runtime. No other local tools required.

## Installation

Download the `tds` wrapper script and make it executable:

```bash
curl -fsSL https://raw.githubusercontent.com/ibaldin/tds/main/tds \
  -o /usr/local/bin/tds && chmod +x /usr/local/bin/tds
```

> On macOS/Linux you may need `sudo` if `/usr/local/bin` is root-owned:
> ```bash
> sudo curl -fsSL https://raw.githubusercontent.com/ibaldin/tds/main/tds \
>   -o /usr/local/bin/tds && sudo chmod +x /usr/local/bin/tds
> ```
>
> Alternatively, install to a user-writable location on your `PATH`:
> ```bash
> curl -fsSL https://raw.githubusercontent.com/ibaldin/tds/main/tds \
>   -o ~/bin/tds && chmod +x ~/bin/tds
> ```

Then pull the Docker image (one-time):

```bash
tds pull
```

## Usage

Run `tds` from your TDS working directory. The current directory is
volume-mounted into the container, so all relative paths — `diagrams/`,
`.mmd` sidecars, referenced PNGs — resolve naturally.

```bash
cd ~/path/to/your/tds

# Render Markdown to DOCX
tds render HPDF_TDS_0001_example.md

# Unrender a reviewed DOCX back to Markdown
tds unrender HPDF_TDS_0001_example.docx

# See all options for either subcommand
tds render --help
tds unrender --help
```

## Diagram support

Three diagram formats are supported in TDS source files:

- **ASCII art** — use a ` ```text ` fenced block for simple inline sketches
- **Mermaid** — use a ` ```mermaid ` block; the render pipeline converts it to
  PNG automatically and saves a `.mmd` sidecar for round-trip recovery
- **Engineer-authored PNG** — place in `diagrams/` and reference with
  `![Caption](diagrams/filename.png)`

## Updating

To pull the latest image:

```bash
tds pull
```

To pin to a specific version, set the `TDS_IMAGE` environment variable:

```bash
TDS_IMAGE=ibaldin/tds:1.0 tds render HPDF_TDS_0001_example.md
```
