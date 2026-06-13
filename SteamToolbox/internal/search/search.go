package search

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// GameResult represents a game found via the SteamUI search API.
type GameResult struct {
	AppID        string `json:"appid"`
	Name         string `json:"name"`
	SchineseName string `json:"schinese_name"`
}

// SearchResponse is the wrapper for the SteamUI API response.
type SearchResponse struct {
	Games []GameResult `json:"games"`
}

var httpClient = &http.Client{Timeout: 15 * time.Second}

// SearchGames calls the SteamUI API to find games matching the search term.
func SearchGames(term string) ([]GameResult, error) {
	url := fmt.Sprintf("https://steamui.com/api/loadGames.php?search=%s", term)

	resp, err := httpClient.Get(url)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API returned status %d", resp.StatusCode)
	}

	var sr SearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&sr); err != nil {
		return nil, fmt.Errorf("failed to decode JSON: %w", err)
	}

	return sr.Games, nil
}
