package i18n

import (
	"fmt"
	"strings"
	"sync"
)

var (
	currentLang = "zh"
	mu          sync.RWMutex
)

var translations = map[string]map[string]string{
	"zh": {
		// ç³»ç»Ÿæ‰˜ç›˜
		"tray.show_window":  "æ˜¾ç¤ºç¨‹åº",
		"tray.show_console": "æ˜¾ç¤ºæŽ§åˆ¶å°",
		"tray.exit":         "é€€å‡ºç¨‹åº",
		// é…ç½®
		"config.generated":         "é…ç½®æ–‡ä»¶å·²ç”Ÿæˆ",
		"config.create_failed":     "é…ç½®æ–‡ä»¶åˆ›å»ºå¤±è´¥: {error}",
		"config.corrupted":         "é…ç½®æ–‡ä»¶æŸåï¼Œæ­£åœ¨é‡æ–°ç”Ÿæˆ...",
		"config.steam_path_failed": "Steamè·¯å¾„èŽ·å–å¤±è´¥: {error}",
		// API
		"api.key_not_exist":   "å¡å¯†ä¸å­˜åœ¨",
		"api.key_type":        "å¡å¯†ç±»åž‹: {type}",
		"api.key_expires":     "å¡å¯†è¿‡æœŸæ—¶é—´: {time}",
		"api.key_info_failed": "èŽ·å–å¡å¯†ä¿¡æ¯å¤±è´¥",
		"api.fetching_game":   "æ­£åœ¨èŽ·å–æ¸¸æˆ {app_id} çš„ä¿¡æ¯...",
		"api.request_failed":  "APIè¯·æ±‚å¤±è´¥ï¼ŒçŠ¶æ€ç : {code}",
		"api.no_manifest":     "æœªæ‰¾åˆ°æ­¤æ¸¸æˆçš„æ¸…å•ä¿¡æ¯",
		"api.game_name":       "æ¸¸æˆåç§°: {name}",
		// ä»»åŠ¡
		"task.no_steam_path":         "Steamè·¯å¾„æœªé…ç½®æˆ–æ— æ•ˆï¼Œæ— æ³•ç»§ç»­",
		"task.run_error":             "è¿è¡Œé”™è¯¯: {error}",
		"task.step.auth":             "æ­£åœ¨éªŒè¯å¡å¯†...",
		"task.step.steamtools_setup": "æ­£åœ¨ç”Ÿæˆ SteamTools è§£é”é…ç½®...",
		"task.step.steamtools_done":  "SteamTools é…ç½®å®Œæˆ: åº”ç”¨ {appid}, å…± {depots} ä¸ªä»“åº“",
		"task.step.finish":           "æ“ä½œæˆåŠŸï¼æ¸¸æˆå·²è§£é”ï¼Œé‡å¯SteamåŽç”Ÿæ•ˆã€‚",
		// Web
		"web.task_running":   "å·²æœ‰ä»»åŠ¡æ­£åœ¨è¿è¡Œ",
		"web.invalid_appid":  "è¯·è¾“å…¥æœ‰æ•ˆçš„App ID",
		"web.invalid_format": "App IDæ ¼å¼æ— æ•ˆ",
		"web.task_started":   "ä»»åŠ¡å·²å¼€å§‹",
		// å¡å¯†ç±»åž‹
		"key_type.week":      "å‘¨å¡",
		"key_type.month":     "æœˆå¡",
		"key_type.year":      "å¹´å¡",
		"key_type.permanent": "æ°¸ä¹…å¡",
		// SteamTools
		"steamtools.setup_done": "SteamTools è§£é”é…ç½®å·²å†™å…¥: {appid}",
		// æ¸…å•
		"manifest.start_batch":        "å¼€å§‹æ‰¹é‡å¤„ç† {count} ä¸ªæ¸…å•ä»»åŠ¡...",
		"manifest.download.failed":    "ä»Ž {url} ä¸‹è½½å¤±è´¥: {error}",
		"manifest.delete_old":         "åˆ é™¤æ—§æ¸…å•: {name}",
		"manifest.process.success":    "æ¸…å•å¤„ç†æˆåŠŸ: {depot_id}_{manifest_id}.manifest",
		"manifest.downloading.failed": "ä¸‹è½½æ¸…å•å¤±è´¥: {depot_id}_{manifest_id}",
		"manifest.status.exists":      "å·²ç¼“å­˜: ä»“åº“ {depot_id}",
		"manifest.status.downloaded":  "å·²ä¸‹è½½: ä»“åº“ {depot_id}",
		"manifest.status.failed":      "å¤±è´¥: ä»“åº“ {depot_id}",
		// é”™è¯¯
		"error.network":                "ç½‘ç»œè¿žæŽ¥é”™è¯¯: {error}",
		"error.invalid_response":       "æ— æ•ˆçš„å“åº”æ•°æ®: {error}",
		"error.invalid_json":           "API è¿”å›žäº†æ— æ•ˆçš„æ•°æ®æ ¼å¼",
		"error.api_response":           "API è¯·æ±‚è¢«æ‹’ç»: {error}",
		"error.server_response":        "æœåŠ¡å™¨ä¸šåŠ¡é”™è¯¯: {error}",
		"error.no_game_data":           "æœªåœ¨å“åº”ä¸­æ‰¾åˆ°æœ‰æ•ˆçš„æ¸¸æˆæ•°æ®",
		"error.unknown":                "æœªçŸ¥é”™è¯¯",
		"error.manifest_empty":         "æ¸¸æˆæ¸…å•åˆ—è¡¨ä¸ºç©ºï¼Œæ— æ³•ç»§ç»­",
		"error.manifest_process_none":  "æ²¡æœ‰æˆåŠŸå¤„ç†ä»»ä½•æ¸…å•æ–‡ä»¶",
		"error.steamtools_setup":       "SteamTools é…ç½®å†™å…¥å¤±è´¥: {error}",
		"error.update_check_failed":    "æ£€æŸ¥æ›´æ–°å¤±è´¥",
		"error.kernel_download_failed": "å†…æ ¸æ–‡ä»¶ä¸‹è½½å¤±è´¥",
		// Steam æ“ä½œ
		"steam.restart_success": "Steam å·²é‡æ–°å¯åŠ¨",
		"steam.restart_failed":  "Steam é‡å¯å¤±è´¥: {error}",
		"steam.exe_not_found":   "æœªæ‰¾åˆ° steam.exe",
		// æ¸¸æˆåº“
		"library.added":               "å·²åŠ å…¥æ¸¸æˆåº“",
		"library.removed":             "å·²ä»Žæ¸¸æˆåº“ç§»é™¤",
		"library.dlc_grouped":         "DLCã€Œ{dlc}ã€å·²å½’å…¥çˆ¶æ¸¸æˆã€Œ{parent}ã€",
		"library.dlc_added_to_parent": "DLC å·²å½’å…¥çˆ¶æ¸¸æˆã€Œ{parent}ã€",
		// Web é…ç½®
		"web.config_saved":        "é…ç½®å·²ä¿å­˜",
		"web.config_save_failed":  "ä¿å­˜é…ç½®å¤±è´¥: {error}",
		"web.config_reset":        "é…ç½®å·²é‡ç½®ä¸ºé»˜è®¤å€¼",
		"web.config_reset_failed": "é‡ç½®é…ç½®å¤±è´¥: {error}",
		// å†…æ ¸
		"kernel.downloading":      "æ­£åœ¨ä¸‹è½½å†…æ ¸æ–‡ä»¶...",
		"kernel.download_success": "å†…æ ¸å·²åŠ è½½åˆ° Steam ç›®å½•",
		"kernel.download_failed":  "å†…æ ¸ä¸‹è½½å¤±è´¥: {error}",
		"kernel.save_failed":      "å†…æ ¸æ–‡ä»¶ä¿å­˜å¤±è´¥: {error}",
		"kernel.no_steam_path":    "è¯·å…ˆé…ç½® Steam è·¯å¾„",
		// å…¬å‘Š
		"announcement.fetch_failed": "èŽ·å–å…¬å‘Šå¤±è´¥",
		// è¡¥ä¸
		"patch.success":  "ä¿®è¡¥å®Œæˆï¼Œå…±ä¿®æ”¹ {count} å¤„",
		"patch.failed":   "ä¿®è¡¥å¤±è´¥: {error}",
		"patch.no_match": "æœªæ‰¾åˆ°éœ€è¦ä¿®è¡¥çš„å†…å®¹",
		// å†…æ ¸è®¾ç½®
		"kernel_settings.saved": "å†…æ ¸è®¾ç½®å·²ä¿å­˜",
		// ä»£ç†
		"settings.proxy_invalid": "ä»£ç†åœ°å€æ ¼å¼æ— æ•ˆ",
		"settings.proxy_fail":    "ä»£ç†è¿žé€šæ€§æµ‹è¯•å¤±è´¥: {error}",
		"settings.proxy_ok":      "ä»£ç†è¿žé€šæ€§æµ‹è¯•æˆåŠŸ",
		// æ›´æ–°
		"update.check_failed": "æ£€æŸ¥æ›´æ–°å¤±è´¥: {error}",
		"update.up_to_date":   "å½“å‰å·²æ˜¯æœ€æ–°ç‰ˆæœ¬",
		"update.new_version":  "å‘çŽ°æ–°ç‰ˆæœ¬: {version}",
	},
	"en": {
		"tray.show_window":             "Show Window",
		"tray.show_console":            "Show Console",
		"tray.exit":                    "Exit",
		"config.generated":             "Configuration file generated",
		"config.create_failed":         "Failed to create configuration file: {error}",
		"config.corrupted":             "Configuration file corrupted, regenerating...",
		"config.steam_path_failed":     "Failed to get Steam path: {error}",
		"api.key_not_exist":            "Key does not exist",
		"api.key_type":                 "Key type: {type}",
		"api.key_expires":              "Key expires at: {time}",
		"api.key_info_failed":          "Failed to get key info",
		"api.fetching_game":            "Fetching game {app_id} information...",
		"api.request_failed":           "API request failed with status code: {code}",
		"api.no_manifest":              "No manifest found for this game",
		"api.game_name":                "Game name: {name}",
		"task.no_steam_path":           "Steam path not configured or invalid",
		"task.run_error":               "Run error: {error}",
		"task.step.auth":               "Verifying API Key...",
		"task.step.steamtools_setup":   "Generating SteamTools unlock configuration...",
		"task.step.steamtools_done":    "SteamTools config done: App {appid}, {depots} depots",
		"task.step.finish":             "Success! Game has been unlocked. Restart Steam to take effect.",
		"web.task_running":             "A task is already running",
		"web.invalid_appid":            "Please enter a valid App ID",
		"web.invalid_format":           "Invalid App ID format",
		"web.task_started":             "Task started",
		"key_type.week":                "Weekly",
		"key_type.month":               "Monthly",
		"key_type.year":                "Yearly",
		"key_type.permanent":           "Permanent",
		"steamtools.setup_done":        "SteamTools unlock config written: {appid}",
		"manifest.start_batch":         "Starting batch processing for {count} manifests...",
		"manifest.download.failed":     "Downloading from {url} failed: {error}",
		"manifest.delete_old":          "Delete old manifest: {name}",
		"manifest.process.success":     "Manifest processed: {depot_id}_{manifest_id}.manifest",
		"manifest.downloading.failed":  "Manifest download failed: {depot_id}_{manifest_id}",
		"manifest.status.exists":       "Cached: Depot {depot_id}",
		"manifest.status.downloaded":   "Downloaded: Depot {depot_id}",
		"manifest.status.failed":       "Failed: Depot {depot_id}",
		"error.network":                "Network Error: {error}",
		"error.invalid_response":       "Invalid response: {error}",
		"error.invalid_json":           "API returned invalid data format",
		"error.api_response":           "API Request Denied: {error}",
		"error.server_response":        "Server Business Error: {error}",
		"error.no_game_data":           "No valid game data found in response",
		"error.unknown":                "Unknown error",
		"error.manifest_empty":         "Manifest list is empty, cannot proceed",
		"error.manifest_process_none":  "No manifests were successfully processed",
		"error.steamtools_setup":       "SteamTools config failed: {error}",
		"error.update_check_failed":    "Failed to check for updates",
		"error.kernel_download_failed": "Kernel file download failed",
		// Steam actions
		"steam.restart_success": "Steam has been restarted",
		"steam.restart_failed":  "Failed to restart Steam: {error}",
		"steam.exe_not_found":   "steam.exe not found",
		// Library
		"library.added":               "Added to library",
		"library.removed":             "Removed from library",
		"library.dlc_grouped":         "DLC \"{dlc}\" grouped under parent game \"{parent}\"",
		"library.dlc_added_to_parent": "DLC added to parent game \"{parent}\"",
		"web.config_saved":            "Configuration saved",
		"web.config_save_failed":      "Failed to save configuration: {error}",
		"web.config_reset":            "Configuration reset to default",
		"web.config_reset_failed":     "Failed to reset configuration: {error}",
		// Kernel
		"kernel.downloading":      "Downloading kernel file...",
		"kernel.download_success": "Kernel loaded to Steam directory",
		"kernel.download_failed":  "Kernel download failed: {error}",
		"kernel.save_failed":      "Failed to save kernel file: {error}",
		"kernel.no_steam_path":    "Please configure Steam path first",
		// Announcement
		"announcement.fetch_failed": "Failed to fetch announcement",
		// Patch
		"patch.success":  "Patch complete, {count} occurrence(s) modified",
		"patch.failed":   "Patch failed: {error}",
		"patch.no_match": "No matching entries found",
		// Kernel settings
		"kernel_settings.saved": "Kernel settings saved",
		// Proxy
		"settings.proxy_invalid": "Invalid proxy URL format",
		"settings.proxy_fail":    "Proxy connectivity test failed: {error}",
		"settings.proxy_ok":      "Proxy connectivity test passed",
		// Update
		"update.check_failed": "Failed to check for updates: {error}",
		"update.up_to_date":   "You are on the latest version",
		"update.new_version":  "New version available: {version}",
	},
}

// SetLanguage sets the current language.
func SetLanguage(lang string) {
	mu.Lock()
	defer mu.Unlock()
	if _, ok := translations[lang]; ok {
		currentLang = lang
	}
}

// T returns a translated string, replacing {key} placeholders with provided values.
// Usage: T("api.fetching_game", "app_id", "730")
func T(key string, args ...string) string {
	mu.RLock()
	lang := currentLang
	mu.RUnlock()

	dict, ok := translations[lang]
	if !ok {
		return key
	}
	text, ok := dict[key]
	if !ok {
		return key
	}

	if len(args) >= 2 {
		for i := 0; i+1 < len(args); i += 2 {
			text = strings.ReplaceAll(text, fmt.Sprintf("{%s}", args[i]), args[i+1])
		}
	}
	return text
}

