--[[
ascii_art_font.lua — Pandoc Lua filter for HPDF TDS rendering

Applies a smaller monospace font to untagged code blocks (ASCII art).
Code blocks with a language tag (```bash, ```json, ```mermaid, etc.) are
left untouched — they are handled by Word's default Source Code style.

Font size is controlled via pandoc metadata key 'ascii-art-font-pt':
  pandoc ... --metadata ascii-art-font-pt=9

The default is 9pt if the key is not present.
--]]

local FONT_NAME     = "Courier New"
local font_size_hp  = "18"          -- default: 9pt expressed in half-points

-- ── Pass 1: read font size from document metadata ─────────────────────────────
-- Runs before CodeBlock traversal because Meta precedes Blocks in the AST.

local function read_meta(meta)
    if meta["ascii-art-font-pt"] then
        local pt = tonumber(pandoc.utils.stringify(meta["ascii-art-font-pt"]))
        if pt and pt > 0 then
            font_size_hp = tostring(math.floor(pt * 2))
        end
    end
end

-- ── Pass 2: replace untagged CodeBlocks with sized OpenXML ───────────────────

local function xml_escape(s)
    return s:gsub("&", "&amp;")
             :gsub("<", "&lt;")
             :gsub(">", "&gt;")
end

local function render_code_block(el)
    -- Only process untagged blocks — language-tagged blocks are ASCII art's peers
    -- but get their own Word style; we leave those alone.
    if #el.classes > 0 then
        return nil   -- no change
    end

    -- Split into lines, drop the trailing empty line the pattern produces
    local lines = {}
    for line in (el.text .. "\n"):gmatch("([^\n]*)\n") do
        table.insert(lines, line)
    end
    if #lines > 0 and lines[#lines] == "" then
        table.remove(lines)
    end

    -- Emit one Word paragraph per line so line breaks are hard paragraph breaks
    -- (more reliable across Word versions than <w:br/> within a single paragraph).
    local blocks = {}
    for _, line in ipairs(lines) do
        local xml = string.format(
            "<w:p>"
            .. "<w:pPr>"
            ..   "<w:spacing w:before='0' w:after='0'/>"
            .. "</w:pPr>"
            .. "<w:r>"
            ..   "<w:rPr>"
            ..     "<w:rFonts w:ascii='%s' w:hAnsi='%s' w:cs='%s'/>"
            ..     "<w:sz w:val='%s'/>"
            ..     "<w:szCs w:val='%s'/>"
            ..   "</w:rPr>"
            ..   "<w:t xml:space='preserve'>%s</w:t>"
            .. "</w:r>"
            .. "</w:p>",
            FONT_NAME, FONT_NAME, FONT_NAME,
            font_size_hp, font_size_hp,
            xml_escape(line)
        )
        table.insert(blocks, pandoc.RawBlock("openxml", xml))
    end

    return blocks
end

-- Return filters as an ordered list so Meta always runs before CodeBlock.
return {
    { Meta      = read_meta        },
    { CodeBlock = render_code_block },
}
