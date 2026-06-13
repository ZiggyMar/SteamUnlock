package gamelist

import (
	_ "embed"
	"encoding/json"
	"strings"
	"sync"
)

//go:embed ../../../assets/data/games.json
var raw []byte

type Game struct {
	AppID       string            `json:"appid"`
	Name        string            `json:"name"`
	Type        string            `json:"type"`
	HeaderImage string            `json:"header_image"`
	Tags        []string          `json:"tags"`
	NSFW        bool              `json:"nsfw"`
	DRM         bool              `json:"drm"`
	DLC         map[string]string `json:"dlc"`
}

var (
	once  sync.Once
	games []Game
)

func load() {
	once.Do(func() {
		_ = json.Unmarshal(raw, &games)
	})
}

// Search returns up to limit games whose name or appid contains query (case-insensitive).
func Search(query string, limit int) []Game {
	load()
	q := strings.ToLower(query)
	var out []Game
	for _, g := range games {
		if strings.Contains(strings.ToLower(g.Name), q) || strings.Contains(g.AppID, q) {
			out = append(out, g)
			if len(out) >= limit {
				break
			}
		}
	}
	return out
}

// Count returns total number of games in the embedded catalog.
func Count() int {
	load()
	return len(games)
}
