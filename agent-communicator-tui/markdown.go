package main

import (
	"regexp"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

var linkStyle = lipgloss.NewStyle().Foreground(colors.Info).Underline(true)
var codeStyle = lipgloss.NewStyle().Foreground(colors.Warning)
var commentStyle = lipgloss.NewStyle().Foreground(colors.Muted).Italic(true)
var keywordStyle = lipgloss.NewStyle().Foreground(colors.AccentAlt).Bold(true)
var stringStyle = lipgloss.NewStyle().Foreground(colors.Success)
var numberStyle = lipgloss.NewStyle().Foreground(colors.Accent)
var typeStyle = lipgloss.NewStyle().Foreground(colors.Info).Bold(true)
var boolStyle = lipgloss.NewStyle().Foreground(colors.Error).Bold(true)

var urlRE = regexp.MustCompile(`https?://[^\s)]+`)
var mdLinkRE = regexp.MustCompile(`\[([^\]]+)\]\((https?://[^\s)]+)\)`)
var numberRE = regexp.MustCompile(`\b(0x[0-9a-fA-F]+|\d+(\.\d+)?)\b`)

func withMarkdownBg(style lipgloss.Style, bgOpt ...lipgloss.Color) lipgloss.Style {
	if len(bgOpt) == 0 {
		return style
	}
	return style.Background(bgOpt[0])
}

func markdownTitleStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(titleStyle, bgOpt...)
}

func markdownLinkStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(linkStyle, bgOpt...)
}

func markdownMutedStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(mutedStyle, bgOpt...)
}

func markdownTextStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(lipgloss.NewStyle().Foreground(colors.Text), bgOpt...)
}

func markdownCodeStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(codeStyle, bgOpt...)
}

func markdownCommentStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(commentStyle, bgOpt...)
}

func markdownKeywordStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(keywordStyle, bgOpt...)
}

func markdownStringStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(stringStyle, bgOpt...)
}

func markdownNumberStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(numberStyle, bgOpt...)
}

func markdownTypeStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(typeStyle, bgOpt...)
}

func markdownBoolStyle(bgOpt ...lipgloss.Color) lipgloss.Style {
	return withMarkdownBg(boolStyle, bgOpt...)
}

func renderMarkdown(s string, width int, bgOpt ...lipgloss.Color) string {
	lines := strings.Split(strings.ReplaceAll(s, "**", ""), "\n")
	var out []string
	for i := 0; i < len(lines); i++ {
		line := strings.TrimSpace(lines[i])
		switch {
		case strings.HasPrefix(line, "#"):
			out = append(out, markdownTitleStyle(bgOpt...).Render(strings.TrimSpace(strings.TrimLeft(line, "#"))))
		case isMarkdownTableStart(lines, i):
			table, next := renderMarkdownTable(lines, i)
			out = append(out, table...)
			i = next - 1
		case strings.HasPrefix(line, "- ") || strings.HasPrefix(line, "* "):
			out = append(out, markdownTextStyle(bgOpt...).Render("• ")+renderInlineMarkdown(strings.TrimSpace(line[2:]), bgOpt...))
		case strings.HasPrefix(line, "```"):
			block, next := renderCodeBlock(lines, i, bgOpt...)
			out = append(out, block...)
			i = next
		default:
			out = append(out, renderInlineMarkdown(lines[i], bgOpt...))
		}
	}
	return strings.Join(out, "\n")
}

func isMarkdownTableStart(lines []string, i int) bool {
	return i+1 < len(lines) && strings.Contains(lines[i], "|") && isMarkdownSeparator(lines[i+1])
}

func isMarkdownSeparator(line string) bool {
	line = strings.TrimSpace(line)
	if !strings.Contains(line, "|") {
		return false
	}
	for _, r := range strings.ReplaceAll(line, "|", "") {
		if r != '-' && r != ':' && r != ' ' {
			return false
		}
	}
	return true
}

func renderMarkdownTable(lines []string, start int) ([]string, int) {
	var rows [][]string
	i := start
	for ; i < len(lines) && strings.Contains(lines[i], "|"); i++ {
		if i == start+1 && isMarkdownSeparator(lines[i]) {
			continue
		}
		rows = append(rows, splitTableRow(lines[i]))
	}
	widths := tableWidths(rows)
	out := make([]string, 0, len(rows)+1)
	for idx, row := range rows {
		out = append(out, formatTableRow(row, widths))
		if idx == 0 {
			out = append(out, formatTableSeparator(widths))
		}
	}
	return out, i
}

func splitTableRow(line string) []string {
	line = strings.Trim(strings.TrimSpace(line), "|")
	parts := strings.Split(line, "|")
	for i := range parts {
		parts[i] = strings.TrimSpace(parts[i])
	}
	return parts
}

func tableWidths(rows [][]string) []int {
	var widths []int
	for _, row := range rows {
		for i, cell := range row {
			for len(widths) <= i {
				widths = append(widths, 0)
			}
			widths[i] = max(widths[i], lipgloss.Width(cell))
		}
	}
	return widths
}

func formatTableRow(row []string, widths []int) string {
	cells := make([]string, len(widths))
	for i := range widths {
		cell := ""
		if i < len(row) {
			cell = row[i]
		}
		cells[i] = lipgloss.PlaceHorizontal(widths[i], lipgloss.Left, cell)
	}
	return "│ " + strings.Join(cells, " │ ") + " │"
}

func formatTableSeparator(widths []int) string {
	parts := make([]string, len(widths))
	for i, w := range widths {
		parts[i] = strings.Repeat("─", w+2)
	}
	return "├" + strings.Join(parts, "┼") + "┤"
}

func renderInlineMarkdown(line string, bgOpt ...lipgloss.Color) string {
	var b strings.Builder
	last := 0
	for _, loc := range mdLinkRE.FindAllStringSubmatchIndex(line, -1) {
		b.WriteString(renderBareURLs(line[last:loc[0]], bgOpt...))
		label := line[loc[2]:loc[3]]
		url := line[loc[4]:loc[5]]
		b.WriteString(markdownLinkStyle(bgOpt...).Render(label))
		b.WriteString(markdownMutedStyle(bgOpt...).Render(" <" + url + ">"))
		last = loc[1]
	}
	b.WriteString(renderBareURLs(line[last:], bgOpt...))
	return b.String()
}

func renderBareURLs(line string, bgOpt ...lipgloss.Color) string {
	if line == "" {
		return ""
	}
	var b strings.Builder
	last := 0
	for _, loc := range urlRE.FindAllStringIndex(line, -1) {
		b.WriteString(renderMarkdownPlain(line[last:loc[0]], bgOpt...))
		b.WriteString(markdownLinkStyle(bgOpt...).Render(line[loc[0]:loc[1]]))
		last = loc[1]
	}
	b.WriteString(renderMarkdownPlain(line[last:], bgOpt...))
	return b.String()
}

func renderMarkdownPlain(s string, bgOpt ...lipgloss.Color) string {
	if s == "" || len(bgOpt) == 0 {
		return s
	}
	return markdownTextStyle(bgOpt...).Render(s)
}

func renderCodeBlock(lines []string, start int, bgOpt ...lipgloss.Color) ([]string, int) {
	lang := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(lines[start]), "```"))
	var out []string
	for i := start + 1; i < len(lines); i++ {
		if strings.HasPrefix(strings.TrimSpace(lines[i]), "```") {
			return out, i
		}
		out = append(out, renderMarkdownPlain("  ", bgOpt...)+highlightCodeLine(lines[i], lang, bgOpt...))
	}
	return out, len(lines) - 1
}

func highlightCodeLine(line, lang string, bgOpt ...lipgloss.Color) string {
	trimmed := strings.TrimSpace(line)
	if strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, "//") {
		return markdownCommentStyle(bgOpt...).Render(line)
	}
	if len(bgOpt) > 0 {
		code, comment := splitInlineComment(line, lang)
		out := highlightCodeLineWithBackground(code, lang, bgOpt[0])
		if comment != "" {
			out += markdownCommentStyle(bgOpt...).Render(comment)
		}
		return out
	}
	code, comment := splitInlineComment(line, lang)
	code = highlightWords(code, languageKeywords(lang), keywordStyle)
	code = highlightWords(code, languageTypes(lang), typeStyle)
	code = highlightWords(code, []string{"true", "false", "nil", "null", "None"}, boolStyle)
	code = numberRE.ReplaceAllStringFunc(code, func(s string) string { return numberStyle.Render(s) })
	code = highlightQuotedStrings(code)
	if comment != "" {
		return codeStyle.Render(code) + commentStyle.Render(comment)
	}
	return codeStyle.Render(code)
}

func highlightCodeLineWithBackground(line, lang string, bg lipgloss.Color) string {
	keywords := wordSet(languageKeywords(lang))
	types := wordSet(languageTypes(lang))
	bools := wordSet([]string{"true", "false", "nil", "null", "None"})
	var b strings.Builder
	for i := 0; i < len(line); {
		ch := line[i]
		if ch == '"' || ch == '\'' {
			end := i + 1
			for end < len(line) {
				if line[end] == '\\' && end+1 < len(line) {
					end += 2
					continue
				}
				if line[end] == ch {
					end++
					break
				}
				end++
			}
			b.WriteString(markdownStringStyle(bg).Render(line[i:end]))
			i = end
			continue
		}
		if isASCIIIdentStart(ch) {
			end := i + 1
			for end < len(line) && isASCIIIdentContinue(line[end]) {
				end++
			}
			word := line[i:end]
			switch {
			case keywords[word]:
				b.WriteString(markdownKeywordStyle(bg).Render(word))
			case types[word]:
				b.WriteString(markdownTypeStyle(bg).Render(word))
			case bools[word]:
				b.WriteString(markdownBoolStyle(bg).Render(word))
			default:
				b.WriteString(markdownCodeStyle(bg).Render(word))
			}
			i = end
			continue
		}
		if isASCIIDigit(ch) {
			end := i + 1
			if ch == '0' && end < len(line) && (line[end] == 'x' || line[end] == 'X') {
				end++
				for end < len(line) && isASCIIHexDigit(line[end]) {
					end++
				}
			} else {
				for end < len(line) && (isASCIIDigit(line[end]) || line[end] == '.') {
					end++
				}
			}
			b.WriteString(markdownNumberStyle(bg).Render(line[i:end]))
			i = end
			continue
		}
		start := i
		for i < len(line) && line[i] != '"' && line[i] != '\'' && !isASCIIIdentStart(line[i]) && !isASCIIDigit(line[i]) {
			i++
		}
		b.WriteString(markdownCodeStyle(bg).Render(line[start:i]))
	}
	return b.String()
}

func wordSet(words []string) map[string]bool {
	set := make(map[string]bool, len(words))
	for _, word := range words {
		set[word] = true
	}
	return set
}

func isASCIIIdentStart(ch byte) bool {
	return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || ch == '_'
}

func isASCIIIdentContinue(ch byte) bool {
	return isASCIIIdentStart(ch) || isASCIIDigit(ch)
}

func isASCIIDigit(ch byte) bool {
	return ch >= '0' && ch <= '9'
}

func isASCIIHexDigit(ch byte) bool {
	return isASCIIDigit(ch) || (ch >= 'A' && ch <= 'F') || (ch >= 'a' && ch <= 'f')
}

func highlightWords(line string, words []string, style lipgloss.Style) string {
	for _, word := range words {
		line = regexp.MustCompile(`\b`+regexp.QuoteMeta(word)+`\b`).ReplaceAllStringFunc(line, func(s string) string { return style.Render(s) })
	}
	return line
}

func splitInlineComment(line, lang string) (string, string) {
	marker := "//"
	switch langName(lang) {
	case "py", "python", "nix", "sh", "bash", "zsh", "shell":
		marker = "#"
	}
	idx := strings.Index(line, marker)
	if idx < 0 {
		return line, ""
	}
	return line[:idx], line[idx:]
}

func langName(lang string) string {
	fields := strings.Fields(lang)
	if len(fields) == 0 {
		return ""
	}
	return strings.ToLower(fields[0])
}

func highlightQuotedStrings(line string) string {
	var b strings.Builder
	inQuote := rune(0)
	start := 0
	for i, r := range line {
		if inQuote == 0 && (r == '"' || r == '\'') {
			b.WriteString(line[start:i])
			inQuote = r
			start = i
			continue
		}
		if inQuote != 0 && r == inQuote {
			b.WriteString(stringStyle.Render(line[start : i+1]))
			inQuote = 0
			start = i + 1
		}
	}
	b.WriteString(line[start:])
	return b.String()
}

func languageKeywords(lang string) []string {
	switch langName(lang) {
	case "go", "golang":
		return []string{"package", "import", "func", "return", "if", "else", "for", "range", "type", "struct", "interface", "var", "const", "defer", "go", "select", "case", "switch"}
	case "py", "python":
		return []string{"def", "return", "if", "elif", "else", "for", "while", "in", "import", "from", "class", "with", "as", "try", "except", "finally", "yield", "lambda"}
	case "nix":
		return []string{"let", "in", "with", "rec", "inherit", "if", "then", "else", "assert"}
	case "sh", "bash", "zsh", "shell":
		return []string{"if", "then", "else", "fi", "for", "do", "done", "case", "esac", "function", "export", "local", "while", "until"}
	default:
		return nil
	}
}

func languageTypes(lang string) []string {
	switch langName(lang) {
	case "go", "golang":
		return []string{"string", "int", "int64", "bool", "error", "map", "chan", "any"}
	case "py", "python":
		return []string{"str", "int", "bool", "dict", "list", "set", "tuple", "Exception"}
	case "nix":
		return []string{"pkgs", "lib", "config", "true", "false", "null"}
	default:
		return nil
	}
}
