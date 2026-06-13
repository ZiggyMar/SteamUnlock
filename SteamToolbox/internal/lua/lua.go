package lua

import (
	"fmt"
	"strings"

	"steamtoolbox/internal/models"
)

// GenerateScript creates a .lua script from the provided AppID and its manifests.
// The format follows the requirements for SteamTools manifest loading.
func GenerateScript(appID string, manifests []models.ManifestInfo) string {
	var sb strings.Builder

	// Start with the main appID
	sb.WriteString(fmt.Sprintf("addappid(%s)\n", appID))

	// For each manifest, add the depot key and the manifest ID
	for _, m := range manifests {
		// If a decryption key exists, add it using addappid(depotID, 1, "key")
		if m.DepotKey != "" {
			sb.WriteString(fmt.Sprintf("addappid(%s,1,\"%s\")\n", m.DepotID, m.DepotKey))
		}
		// Set the manifest ID using setManifestid(depotID, "manifestID", 0)
		sb.WriteString(fmt.Sprintf("setManifestid(%s,\"%s\",0)\n", m.DepotID, m.ManifestID))
	}

	return sb.String()
}
