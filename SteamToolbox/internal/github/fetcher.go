// Package github fetches Steam manifests from public GitHub repositories.
// It ports the logic from Manifest2Lua (Python) and ManifestDownload (C#)
// into Go, providing a free alternative to the paid Onekey API.
//
// Repos searched (in priority order):
//
//	SteamAutoCracks/ManifestHub
//	ikun0014/ManifestHub
//	Auiowu/ManifestAutoUpdate
//	tymolu233/ManifestAutoUpdate-fix
//	wxy1343/ManifestAutoUpdate
//
// Each repo stores manifests indexed by appID as a git branch name.
// The branch tree contains:
//   - *.manifest files  → downloaded to depotcache/
//   - Key.vdf / key.vdf / config.vdf → parsed for depot decryption keys
package github

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"steamtoolbox/internal/depotkeys"
	"steamtoolbox/internal/models"
)

// Repos to search for manifests, in priority order.
var repos = []string{
	"SteamAutoCracks/ManifestHub",
	"ikun0014/ManifestHub",
	"Auiowu/ManifestAutoUpdate",
	"tymolu233/ManifestAutoUpdate-fix",
	"wxy1343/ManifestAutoUpdate",
}

// CDN mirrors for raw GitHub content (avoids rate limits in CN).
var rawMirrors = []string{
	"https://raw.githubusercontent.com/%s/%s/%s",
	"https://raw.gitmirror.com/%s/%s/%s",
	"https://raw.dgithub.xyz/%s/%s/%s",
	"https://cdn.jsdmirror.com/gh/%s@%s/%s",
}

var httpClient = &http.Client{Timeout: 30 * time.Second}

// FetchResult is returned by FetchForApp.
type FetchResult struct {
	Manifests []models.ManifestInfo
	RepoUsed  string
	UpdatedAt string
}

// FetchForApp searches all repos for manifests belonging to appID.
// It returns the first repo that has the branch, or an error if none do.
// The caller is responsible for writing manifest files to disk.
func FetchForApp(appID, githubToken string) (*FetchResult, error) {
	for _, repo := range repos {
		result, err := fetchFromRepo(repo, appID, githubToken)
		if err != nil {
			continue
		}
		if len(result.Manifests) > 0 {
			result.RepoUsed = repo
			return result, nil
		}
	}
	return nil, fmt.Errorf("appID %s not found in any manifest repository", appID)
}

func fetchFromRepo(repo, appID, token string) (*FetchResult, error) {
	branchURL := fmt.Sprintf("https://api.github.com/repos/%s/branches/%s", repo, appID)
	branchData, err := apiGet(branchURL, token)
	if err != nil {
		return nil, err
	}

	var branch struct {
		Commit struct {
			SHA    string `json:"sha"`
			Commit struct {
				Tree struct {
					URL string `json:"url"`
				} `json:"tree"`
				Author struct {
					Date string `json:"date"`
				} `json:"author"`
			} `json:"commit"`
		} `json:"commit"`
	}
	if err := json.Unmarshal(branchData, &branch); err != nil || branch.Commit.SHA == "" {
		return nil, fmt.Errorf("no branch %s in %s", appID, repo)
	}

	sha := branch.Commit.SHA
	treeURL := branch.Commit.Commit.Tree.URL
	updatedAt := branch.Commit.Commit.Author.Date

	treeData, err := apiGet(treeURL, token)
	if err != nil {
		return nil, err
	}

	var tree struct {
		Tree []struct {
			Path string `json:"path"`
			SHA  string `json:"sha"`
		} `json:"tree"`
	}
	if err := json.Unmarshal(treeData, &tree); err != nil {
		return nil, err
	}

	// Collect depot keys from VDF files first.
	parsedKeys := map[string]string{} // depotID → key
	vdfNames := []string{"Key.vdf", "key.vdf", "config.vdf"}
	for _, item := range tree.Tree {
		for _, vname := range vdfNames {
			if item.Path == vname {
				content := fetchRaw(repo, sha, item.Path)
				if content != nil {
					parseVDF(content, parsedKeys)
				}
				break
			}
		}
	}

	// Download .manifest files and build ManifestInfo list.
	var manifests []models.ManifestInfo
	for _, item := range tree.Tree {
		if !strings.HasSuffix(item.Path, ".manifest") {
			continue
		}
		// item.Path format: "{depotID}_{manifestID}.manifest"
		base := strings.TrimSuffix(item.Path, ".manifest")
		parts := strings.SplitN(base, "_", 2)
		if len(parts) != 2 {
			continue
		}
		depotID, manifestID := parts[0], parts[1]

		// Resolve depot key: VDF file > ManifestHub embedded data > empty
		key := parsedKeys[depotID]
		if key == "" {
			key = depotkeys.Get(depotID)
		}

		manifests = append(manifests, models.ManifestInfo{
			AppID:      appID,
			DepotID:    depotID,
			ManifestID: manifestID,
			DepotKey:   key,
			// RawURL is used by DownloadManifestFile to fetch the actual bytes.
			URL: fmt.Sprintf("/__github__/%s/%s/%s", repo, sha, item.Path),
		})
	}

	return &FetchResult{
		Manifests: manifests,
		UpdatedAt: updatedAt,
	}, nil
}

// DownloadManifestFile fetches the raw bytes of a manifest file.
// manifestURL must be the URL field set by FetchForApp (starts with /__github__/).
func DownloadManifestFile(manifestURL string) ([]byte, error) {
	// Parse our internal URL: /__github__/{owner}/{repo}/{sha}/{path}
	path := strings.TrimPrefix(manifestURL, "/__github__/")
	// path is now: "{owner}/{repo}/{sha}/{filename}"
	// We need to split into repo (owner/repo), sha, and file path.
	parts := strings.SplitN(path, "/", 4)
	if len(parts) != 4 {
		return nil, fmt.Errorf("invalid internal manifest URL: %s", manifestURL)
	}
	repo := parts[0] + "/" + parts[1]
	sha := parts[2]
	filePath := parts[3]
	data := fetchRaw(repo, sha, filePath)
	if data == nil {
		return nil, fmt.Errorf("failed to download manifest %s from %s", filePath, repo)
	}
	return data, nil
}

// fetchRaw downloads file content from GitHub CDN mirrors.
func fetchRaw(repo, sha, filePath string) []byte {
	parts := strings.SplitN(repo, "/", 2)
	if len(parts) != 2 {
		return nil
	}
	owner, repoName := parts[0], parts[1]

	for _, mirror := range rawMirrors {
		var url string
		if strings.Contains(mirror, "@%s") {
			// jsdelivr-style: cdn.jsdmirror format uses @sha
			url = fmt.Sprintf(mirror, owner+"/"+repoName, sha, filePath)
		} else {
			url = fmt.Sprintf(mirror, owner, repoName, sha+"/"+filePath)
		}

		resp, err := httpClient.Get(url)
		if err != nil {
			continue
		}
		if resp.StatusCode == 200 {
			data, err := io.ReadAll(resp.Body)
			resp.Body.Close()
			if err == nil {
				return data
			}
		} else {
			resp.Body.Close()
		}
	}
	return nil
}

// apiGet calls the GitHub API with optional token auth.
func apiGet(url, token string) ([]byte, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github.v3+json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == 404 {
		return nil, fmt.Errorf("not found: %s", url)
	}
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, url)
	}
	return io.ReadAll(resp.Body)
}

// parseVDF extracts depot decryption keys from a ValveKeyValue VDF file.
// Format:
//
//	"depots"
//	{
//	    "12345"
//	    {
//	        "DecryptionKey"   "aabbcc..."
//	    }
//	}
func parseVDF(data []byte, out map[string]string) {
	text := string(data)
	lines := strings.Split(text, "\n")
	var currentDepot string
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || line == "{" || line == "}" {
			continue
		}
		fields := splitVDFLine(line)
		if len(fields) == 1 {
			currentDepot = fields[0]
			continue
		}
		if len(fields) == 2 && strings.EqualFold(fields[0], "DecryptionKey") && currentDepot != "" {
			out[currentDepot] = fields[1]
		}
	}
}

func splitVDFLine(line string) []string {
	var fields []string
	inQuote := false
	var cur strings.Builder
	for _, ch := range line {
		if ch == '"' {
			if inQuote {
				fields = append(fields, cur.String())
				cur.Reset()
			}
			inQuote = !inQuote
			continue
		}
		if inQuote {
			cur.WriteRune(ch)
		}
	}
	return fields
}
