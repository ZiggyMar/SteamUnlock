package depotkeys

import (
	_ "embed"
	"encoding/json"
	"sync"
)

//go:embed ../../../assets/data/depotkeys.json
var raw []byte

var (
	once sync.Once
	keys map[string]string // depotID → hex key
)

func load() {
	once.Do(func() {
		keys = make(map[string]string)
		_ = json.Unmarshal(raw, &keys)
	})
}

// Get returns the depot decryption key for the given depot ID, or "" if unknown.
func Get(depotID string) string {
	load()
	return keys[depotID]
}

// Has reports whether a depot key is available for depotID.
func Has(depotID string) bool {
	load()
	_, ok := keys[depotID]
	return ok
}
