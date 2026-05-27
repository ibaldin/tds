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

Then pull the Docker image (one-time, also to update to latest):

```bash
tds pull
```

## Usage

Run `tds` from your TDS working directory. The current directory is
volume-mounted into the container, so all relative paths — `diagrams/`,
`.mmd` sidecars, referenced PNGs — resolve naturally.

```bash
cd ~/path/to/your/tds

# Initialize the repo
tds init

# Create a fresh doc (it will be HPDF_TDS_0002)
tds new --owner "J.Doe" --component iam "Identity and Access Management"

# Render Markdown to DOCX for the existing example
# The document created from `tds new` wbove is likely to be called HPDF_TDS_0002_iam.md
# It will only have the basic sections and no diagram examples, so instead use
# the example document like so:

# validate diagrams saving .mmd files under @diagrams/ as well as newly generated .pngs
tds validate HPDF_TDS_0001_example.md

# render to DocX (will use .pngs that are generated from Mermaid diagrams)
tds render HPDF_TDS_0001_example.md

# Unrender a reviewed DOCX back to Markdown
# By default will substitute Mermaid text blocks instead of diagrams back where they
# belong. Use --nommdc if you don't want it to do that.
tds unrender HPDF_TDS_0001_example.docx

# See all options for either subcommand
tds -h 
tds render --help
tds unrender --help
```

## Diagram support

Three diagram formats are supported in TDS source files:

- **ASCII art** — use a ` ```text ` fenced block for simple inline sketches. You can use `--ascii-art-font-size` option with `tds render` to change how the ASCII art diagrams look in DocX. Default is 9 pts font. 
- **Mermaid** — use a ` ```mermaid ` block; the render pipeline converts it to PNG automatically and saves a `.mmd` sidecar for round-trip recovery in `diagrams/`. By default the workflow substitues Mermaid diagrams with PNG files saved in `diagrams/` when you call `tds render` and attempts to reinsert ` ```mermaid ` blocks back based on the saved .mmd files in `diagrams/` when you call `tds unrender`. You can stop the conversion back to Mermaid by adding `--nommdc` to `tds unrender` command. 
- **Engineer-authored PNG** — place in `diagrams/` and reference with
  `![Caption](diagrams/filename.png)`



## Updating

To pull the latest image:

```bash
tds pull
```

To pull latest TDS_WORKFLOW, example or other resource files do this in the TDS repository - it is safe
not to overwrite anything that exists. If you want it to overwrite a specific file, remove it first.
```bash
tds init
```

To pin to a specific version, set the `TDS_IMAGE` environment variable:

```bash
TDS_IMAGE=ibaldin/tds:1.0 tds render HPDF_TDS_0001_example.md
```
