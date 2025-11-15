# Per-Pattern LED Effects

## Overview

The Dune Weaver system now supports customizable LED effects for individual patterns. This allows you to configure different LED behaviors for different patterns, creating a more immersive and customized experience.

## Features

- **Pattern-Specific LED Effects**: Configure unique LED effects (color, speed, intensity, palette) for each pattern
- **Playing and Idle Effects**: Set different effects for when a pattern is playing vs. when it completes
- **Global Fallback**: Patterns without custom effects use the global LED settings
- **WLED and DW LED Support**: Works with both WLED network controllers and DW LED (built-in NeoPixel) systems

## How It Works

### Pattern Execution Flow

1. When a pattern starts playing:
   - System checks if the pattern has a custom "playing" LED effect configured
   - If found, uses the pattern-specific effect
   - If not found, falls back to global "playing" effect

2. When a pattern completes:
   - System checks if the pattern has a custom "idle" LED effect configured
   - If found, uses the pattern-specific effect
   - If not found, falls back to global "idle" effect

### Data Storage

Per-pattern LED effects are stored in the metadata cache (`metadata_cache.json`) alongside other pattern metadata:

```json
{
  "data": {
    "hero_7loop4.thr": {
      "metadata": {
        "total_coordinates": 1234,
        "first_coordinate": {"x": 45.5, "y": 0.25},
        "last_coordinate": {"x": 350.2, "y": 0.24},
        "led_effect": {
          "playing": {
            "effect_id": 7,
            "palette_id": 0,
            "speed": 150,
            "intensity": 200,
            "color1": "#ff0000",
            "color2": "#00ff00",
            "color3": "#0000ff"
          },
          "idle": {
            "effect_id": 0,
            "palette_id": 0,
            "speed": 128,
            "intensity": 128,
            "color1": "#ffffff",
            "color2": "#000000",
            "color3": "#0000ff"
          }
        }
      }
    }
  }
}
```

## API Endpoints

### Get Pattern LED Effect

Get the configured LED effect for a specific pattern.

```http
GET /api/patterns/{pattern_path}/led_effect?effect_type=playing
```

**Parameters:**
- `pattern_path` (path): Pattern filename (e.g., `hero_7loop4.thr` or `custom_patterns/mypattern.thr`)
- `effect_type` (query): `playing` or `idle` (default: `playing`)

**Response:**
```json
{
  "pattern": "hero_7loop4.thr",
  "effect_type": "playing",
  "settings": {
    "effect_id": 7,
    "palette_id": 0,
    "speed": 150,
    "intensity": 200,
    "color1": "#ff0000",
    "color2": "#00ff00",
    "color3": "#0000ff"
  }
}
```

If no custom effect is configured, `settings` will be `null`.

### Set Pattern LED Effect

Configure a custom LED effect for a specific pattern.

```http
POST /api/patterns/{pattern_path}/led_effect
```

**Request Body:**
```json
{
  "effect_type": "playing",
  "effect_id": 7,
  "palette_id": 0,
  "speed": 150,
  "intensity": 200,
  "color1": "#ff0000",
  "color2": "#00ff00",
  "color3": "#0000ff"
}
```

**Parameters:**
- `effect_type`: `playing` or `idle`
- `effect_id`: Effect ID (0-15 for DW LEDs, 0-101 for WLED)
- `palette_id`: Palette ID (0-58 for DW LEDs)
- `speed`: Effect speed (0-255)
- `intensity`: Effect intensity (0-255)
- `color1`, `color2`, `color3`: Hex color codes (e.g., `#ff0000`)

**Response:**
```json
{
  "success": true,
  "pattern": "hero_7loop4.thr",
  "effect_type": "playing",
  "settings": { ... }
}
```

### Clear Pattern LED Effect

Remove custom LED effect configuration for a pattern (reverts to global settings).

```http
DELETE /api/patterns/{pattern_path}/led_effect?effect_type=playing
```

**Parameters:**
- `pattern_path` (path): Pattern filename
- `effect_type` (query): `playing`, `idle`, or omit to clear all

**Response:**
```json
{
  "success": true,
  "pattern": "hero_7loop4.thr",
  "effect_type": "playing"
}
```

## Usage Examples

### Example 1: Set Rainbow Effect for a Pattern

Set the "Rainbow Cycle" effect (ID 7) to play when the `hero_7loop4.thr` pattern runs:

```bash
curl -X POST "http://localhost:8080/api/patterns/hero_7loop4.thr/led_effect" \
  -H "Content-Type: application/json" \
  -d '{
    "effect_type": "playing",
    "effect_id": 7,
    "palette_id": 0,
    "speed": 150,
    "intensity": 200,
    "color1": "#ff0000",
    "color2": "#00ff00",
    "color3": "#0000ff"
  }'
```

### Example 2: Set Calm Blue Idle Effect

Set a static blue effect when the pattern completes:

```bash
curl -X POST "http://localhost:8080/api/patterns/hero_7loop4.thr/led_effect" \
  -H "Content-Type: application/json" \
  -d '{
    "effect_type": "idle",
    "effect_id": 0,
    "palette_id": 0,
    "speed": 128,
    "intensity": 128,
    "color1": "#0000ff",
    "color2": "#000000",
    "color3": "#0000ff"
  }'
```

### Example 3: Get Pattern LED Effect

Check if a pattern has custom LED effects configured:

```bash
curl "http://localhost:8080/api/patterns/hero_7loop4.thr/led_effect?effect_type=playing"
```

### Example 4: Clear Pattern LED Effect

Remove custom effects and revert to global settings:

```bash
curl -X DELETE "http://localhost:8080/api/patterns/hero_7loop4.thr/led_effect"
```

## DW LED Effect IDs

For DW LED controllers, the following effects are available:

| ID | Effect Name | Description |
|----|-------------|-------------|
| 0 | Static | Solid color |
| 1 | Blink | Two colors blinking |
| 2 | Breath | Breathing/pulsing effect |
| 3 | Fade | Smooth fade between colors |
| 4 | Scan | Moving dot |
| 5 | Dual Scan | Two moving dots |
| 6 | Rainbow | Cycling hue |
| 7 | Rainbow Cycle | Rainbow across strip |
| 8 | Theater Chase | Theater-style chasing lights |
| 9-15 | Various | Additional effects |

See `/api/dw_leds/effects` for a complete list.

## DW LED Palette IDs

For DW LED controllers, the following color palettes are available:

| ID | Palette Name | Description |
|----|--------------|-------------|
| 0 | Default | Use custom colors |
| 1 | Rainbow | Full spectrum rainbow |
| 2 | Fire | Warm fire colors |
| 3 | Ocean | Cool blue/cyan tones |
| 4-58 | Various | Additional palettes |

See `/api/dw_leds/palettes` for a complete list.

## Implementation Details

### Backend Components

1. **Cache Manager** (`modules/core/cache_manager.py`)
   - `get_pattern_led_effect()`: Retrieve LED effect settings
   - `set_pattern_led_effect()`: Save LED effect settings
   - `clear_pattern_led_effect()`: Remove LED effect settings

2. **Pattern Manager** (`modules/core/pattern_manager.py`)
   - Loads pattern-specific LED effects before execution
   - Falls back to global settings if no custom effect exists
   - Applies effects at pattern start, pause, resume, and completion

3. **API Endpoints** (`main.py`)
   - RESTful API for managing per-pattern LED settings
   - Path-based routing for pattern selection
   - Query parameters for effect type selection

### Compatibility

- ✅ Works with WLED (network-based LED controllers)
- ✅ Works with DW LEDs (built-in NeoPixel controllers)
- ✅ Backward compatible (patterns without custom effects use global settings)
- ✅ Supports custom patterns in subdirectories
- ✅ Playlist-compatible (each pattern in playlist can have its own effect)

## Troubleshooting

### Pattern Effect Not Applied

1. Check that the pattern path is correct (use forward slashes: `custom_patterns/mypattern.thr`)
2. Verify the effect was saved: `GET /api/patterns/{pattern}/led_effect`
3. Check server logs for any errors during pattern execution

### Effects Reverting to Global

If a pattern uses global effects instead of custom ones:
1. The custom effect may not be configured
2. The pattern path may not match exactly
3. Check the metadata cache file for the pattern entry

### API Errors

- **400 Bad Request**: Invalid effect_type or missing required fields
- **500 Internal Server Error**: Check server logs for details

## Future Enhancements

Potential future improvements:
- Web UI for configuring pattern LED effects
- Bulk edit multiple patterns at once
- Import/export LED effect presets
- Visual LED effect preview
- Pattern categories with shared LED themes
