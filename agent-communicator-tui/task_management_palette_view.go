package main

func (m model) taskCommandPaletteView(width, height int) string {
	return CommandPaletteComponent{
		Title:    "Task commands",
		Help:     "↑/↓ select · enter run · esc close",
		Items:    taskCommandPaletteItems(m.taskCommandEntries()),
		Selected: m.tasksPalette.Selected,
		Width:    width,
		Height:   height,
	}.View()
}

func taskCommandPaletteItems(entries []taskCommandEntry) []CommandPaletteItem {
	items := make([]CommandPaletteItem, 0, len(entries))
	for _, entry := range entries {
		items = append(items, CommandPaletteItem{Title: entry.Label, Subtitle: entry.Help, Enabled: entry.Enabled})
	}
	return items
}
