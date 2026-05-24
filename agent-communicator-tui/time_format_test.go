package main

import "testing"

func TestFormatDisplayTimeConvertsToGMT530(t *testing.T) {
	got := formatDisplayTime("2026-05-20T10:24:51.338456+00:00")
	want := "20 May 2026 15:54"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestFormatDisplayTimeKeepsInvalidInput(t *testing.T) {
	if got := formatDisplayTime("not-a-time"); got != "not-a-time" {
		t.Fatalf("got %q", got)
	}
}
