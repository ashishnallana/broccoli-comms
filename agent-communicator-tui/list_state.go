package main

type CardListState struct {
	Selected int
	Offset   int
	Count    int
	Visible  int
	Wrap     bool
}

func (s CardListState) Normalize() CardListState {
	if s.Count <= 0 {
		s.Selected = 0
		s.Offset = 0
		return s
	}
	s.Visible = min(max(1, s.Visible), s.Count)
	s.Selected = min(max(0, s.Selected), s.Count-1)
	s.Offset = min(max(0, s.Offset), max(0, s.Count-s.Visible))
	return s.ScrollSelectedIntoView()
}

func (s CardListState) Move(delta int) CardListState {
	if s.Count <= 0 {
		return CardListState{Visible: s.Visible, Wrap: s.Wrap}
	}
	if s.Wrap {
		s.Selected = (s.Selected + delta + s.Count) % s.Count
	} else {
		s.Selected = min(max(0, s.Selected+delta), s.Count-1)
	}
	return s.Normalize()
}

func (s CardListState) ScrollSelectedIntoView() CardListState {
	if s.Count <= 0 {
		s.Selected = 0
		s.Offset = 0
		return s
	}
	s.Visible = min(max(1, s.Visible), s.Count)
	if s.Selected < s.Offset {
		s.Offset = s.Selected
	}
	if s.Selected >= s.Offset+s.Visible {
		s.Offset = s.Selected - s.Visible + 1
	}
	s.Offset = min(max(0, s.Offset), max(0, s.Count-s.Visible))
	return s
}
