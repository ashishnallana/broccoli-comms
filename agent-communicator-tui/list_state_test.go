package main

import "testing"

func TestCardListStateMoveClampWrapAndScroll(t *testing.T) {
	state := CardListState{Selected: 0, Offset: 0, Count: 10, Visible: 3}.Move(5)
	if state.Selected != 5 || state.Offset != 3 {
		t.Fatalf("move down selected/offset=%d/%d want 5/3", state.Selected, state.Offset)
	}
	state = state.Move(-100)
	if state.Selected != 0 || state.Offset != 0 {
		t.Fatalf("clamp up selected/offset=%d/%d want 0/0", state.Selected, state.Offset)
	}
	state = CardListState{Selected: 0, Count: 3, Visible: 2, Wrap: true}.Move(-1)
	if state.Selected != 2 || state.Offset != 1 {
		t.Fatalf("wrap selected/offset=%d/%d want 2/1", state.Selected, state.Offset)
	}
	state = CardListState{Selected: 5, Offset: 5, Count: 0, Visible: 3}.Normalize()
	if state.Selected != 0 || state.Offset != 0 {
		t.Fatalf("empty normalize selected/offset=%d/%d want 0/0", state.Selected, state.Offset)
	}
}

func TestMemorySelectionUsesSharedCardListState(t *testing.T) {
	m := model{mode: memoryView, memoryItems: makeLargeMemoryRecords(20)}
	m.moveMemorySelection(8, 4)
	if m.memorySelected != 8 || m.memoryOffset != 5 {
		t.Fatalf("memory selection/offset=%d/%d want 8/5", m.memorySelected, m.memoryOffset)
	}
	m.moveMemorySelection(-100, 4)
	if m.memorySelected != 0 || m.memoryOffset != 0 {
		t.Fatalf("memory clamp selected/offset=%d/%d want 0/0", m.memorySelected, m.memoryOffset)
	}
}
