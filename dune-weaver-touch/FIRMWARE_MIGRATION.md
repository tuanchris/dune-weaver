# Touch app → FluidNC firmware migration

Status of wiring `dune-weaver-touch` directly to the new headless FluidNC
firmware (`dune-weaver-firmware`), replacing the old dune-weaver host FastAPI
server. The entire QML interface (properties / slots / signals) is preserved, so
no `.qml` files were changed.

## Architecture change

| Concern | Before (host FastAPI) | After (firmware direct) |
|---------|-----------------------|-------------------------|
| Status | WebSocket `/ws/status` | poll `GET /sand_status` (~1 Hz) |
| Actions | REST `/run_theta_rho`, `/stop_execution`, … | `$...` cmds via `/command` + `/sand_*` routes |
| Patterns | local FS `../patterns` | `GET /sand_patterns`, files from `/sd/patterns/...` |
| Previews | prebuilt PNG cache | rendered locally from `.thr`, cached in `preview_cache/` |
| Playlists | `../playlists.json` | `/sand_playlists` + `.txt` on SD (upload/delete file-ops) |
| LEDs | `/api/dw_leds/*` numeric ids | `$LED/*` / `/sand_led` named effects/palettes |
| Table address | `DUNE_WEAVER_URL` (localhost) | mDNS auto-discovery + `DUNE_WEAVER_URL` pin |
| Screen / LCD | local sysfs (unchanged) | local sysfs (unchanged) |

## Files

**New**
- `firmware_client.py` — shared async HTTP client singleton (`FirmwareClient.instance()`);
  status/patterns/playlists/settings reads, `$...` commands, `/sand_*` actions,
  `/upload` file-ops, LED + clear-mode maps, firmware error surfacing.
- `discovery.py` — mDNS discovery of `_http._tcp` tables (`model=dune-weaver`);
  optional `zeroconf`, degrades to empty list if missing.
- `thr_preview.py` — parse `.thr`, render polar path → cached PNG, sync cache lookup.

**Rewritten**
- `backend.py` — QML-facing controller. Status polling, all actions remapped to
  firmware, LED catalogue, playlist file editing, table connect/disconnect via the
  old "serial" UI, local screen/LCD kept verbatim.
- `models/pattern_model.py`, `models/playlist_model.py` — firmware-backed, refresh
  on `baseUrlChanged`.

**Updated**
- `requirements.txt` (+`zeroconf`), `.env.example`, `run.sh` (dropped localhost:8080
  gate), `README.md`, added `.gitignore`.

## Mapping decisions (verify on hardware)

- **Clear modes:** `clear_center → in`, `clear_perimeter → out`, `adaptive → adaptive`,
  `none → none` (`CLEAR_MODE_MAP` in `firmware_client.py`). `$Sand/Run … clear=` needs a
  `playlist:` config section on the board.
- **Speed** → `/sand_feed?mm=` (motor mm/min); the 50–500 options pass through as feed.
- **"Restart backend"** → reboots the table (`$Bye`). **"Shutdown Pi"** → local `sudo shutdown`.
- **Auto-play-on-boot:** disabling clears `$Playlist/Autostart` reliably; enabling needs a
  chosen playlist name (best-effort / logged only).
- **Table picker** reuses the serial UI: discovered URLs populate the port list;
  `connectSerial(url)` selects one; saved to `touch_settings.json`.

## Verification done

- All modules byte-compile.
- `.thr` renderer produces valid PNGs; `discovery.py` imports with/without zeroconf.
- Full contract check: every QML-consumed slot/property/signal exists in the rewrite.
- Not yet run against real hardware or a live GUI (no PySide6/display in the dev env).

## Known gaps / follow-ups

- **No in-UI manual IP entry** — if mDNS fails, fall back to `DUNE_WEAVER_URL`. A kiosk
  text field in `TableControlPage.qml` would be a good addition.
- Auto-play-on-boot could be wired to a playlist picker for full parity.
- Live smoke test against a table still needed.

## Before running

```bash
pip install -r requirements.txt   # adds zeroconf
# optionally pin the table:
echo 'DUNE_WEAVER_URL=dunetable.local' >> .env
./run.sh
```
