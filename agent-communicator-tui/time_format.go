package main

import "time"

var displayLocation = time.FixedZone("GMT+5:30", 5*60*60+30*60)

func formatDisplayTime(value string) string {
	if value == "" {
		return ""
	}
	for _, layout := range []string{time.RFC3339Nano, time.RFC3339} {
		if t, err := time.Parse(layout, value); err == nil {
			return t.In(displayLocation).Format("02 Jan 2006 15:04")
		}
	}
	return value
}
