# QuotaMonitor for Ubuntu 24.04 / GNOME Shell 46

This is the Linux version of QuotaMonitor. The macOS application and its App Group
remain unchanged. The Linux extension displays a desktop quota card and a top-bar
indicator such as `Work 41%`.

It monitors the Codex account signed in **on the Ubuntu machine**. Sign in to the
same account as on your Mac if you want to monitor the same account's quota.

## Install on Ubuntu

1. Transfer `QuotaMonitor-GNOME46.zip` from the Mac to Ubuntu and extract it.
2. Make sure Codex CLI is installed and signed in on Ubuntu. In a terminal,
   `command -v codex` and `codex --version` should work. The CLI must support
   `codex app-server --listen stdio://` and `account/rateLimits/read`, as the Mac
   version does. If not signed in yet, use `codex login`.
3. Open a terminal inside the extracted `QuotaMonitor-GNOME46` folder and run:

   ```bash
   python3 install.py
   ```

   Run as your normal desktop user, **without sudo**. Python 3 and GNOME's
   `gnome-extensions` and `glib-compile-schemas` commands are required. If the
   installer reports the schema compiler is missing, install it with
   `sudo apt install libglib2.0-bin`.

4. **Log out of Ubuntu and log back in.** This lets GNOME discover the new extension,
   including under Wayland. Locking the screen is not sufficient.
5. Enable it in a terminal:

   ```bash
   gnome-extensions enable quotamonitor@hegstad.no
   ```

The desktop card should appear in the top-right corner of your primary monitor.
Click the `Work` percentage in the top bar for manual refresh, the desktop card
visibility switch, or a choice of four corners. Normal application windows cover
the desktop card. It is hidden with the desktop in the Activities overview and
disabled on the lock screen. Desktop visibility and corner choice survive logout.

Use **Oppdater fra Codex nå** in the top-bar menu for a manual refresh. The desktop
card is display-only, so it does not intercept mouse input intended for other apps
or desktop icons. The UI labels match the Norwegian macOS version; reset dates and
times use your Ubuntu locale/timezone.

## Codex installed through NVM, npm, Conda, or a custom PATH

Run `install.py` from a terminal where Codex works. It records that terminal's
absolute Codex executable path, so GNOME does not need your interactive shell's
PATH. The worker also adds the executable's directory to its child PATH so an NVM
installation can find its sibling `node` executable.

You can specify an executable explicitly (replace the example with your real path):

```bash
python3 install.py --codex /absolute/path/to/codex
```

Rerun the installer if you move Codex or replace an NVM version containing it.
The installer does not log in, copy credentials, or execute Codex during installation.

## What it reads and stores

- It launches a short-lived `codex app-server --listen stdio://`, sends `initialize`,
  `initialized`, and the read-only `account/rateLimits/read`, and stops that child.
- It matches the 300-minute and 10080-minute windows. It uses the returned
  `resetsAt` values directly for local reset dates and countdowns.
- Automatic refresh is every **120 seconds**, with at most one in flight. A
  persisted last-attempt time avoids extra automatic calls when unlocking or
  re-enabling the extension. Manual refresh can run sooner.
- The top bar shows the lowest available remaining percentage. Progress is green
  at 50% or more, yellow from 20% through 49%, and red below 20%.
- Failed refreshes retain successful values, reset dates, and last-updated time.
  Both views show a compact failure message; the top-bar menu includes details.
- The screen countdown redraws every minute locally without contacting Codex.
- No model turns, GPT Pro scraping, authentication-file parsing, purchases, billing
  calls, automatic top-ups, or extra background service.

Local files (standard XDG paths are respected):

| Purpose | Default location |
| --- | --- |
| Extension | `~/.local/share/gnome-shell/extensions/quotamonitor@hegstad.no/` |
| Codex executable setting | `~/.config/quotamonitor/config.json` |
| Last quota and refresh status | `~/.local/state/quotamonitor/quota.json` |
| Backups made before extension updates | `~/.local/share/quotamonitor/backups/` |

Desktop appearance preferences are stored in the extension's GSettings schema.
Linux state is separate from the macOS App Group; it is not copied or synchronized.

## Updating and disabling

For an update, extract the new download and rerun `python3 install.py`. Existing
extension files are backed up before replacement. Cached quota and appearance
settings are retained. Log out/in, then enable it again using the command above.

To stop the UI and its quota checks:

```bash
gnome-extensions disable quotamonitor@hegstad.no
```

The extension uses GNOME's normal enabled-extension setting to start at login;
there is no separate startup application or systemd service.

## Troubleshooting

If it does not appear, check:

```bash
gnome-extensions info quotamonitor@hegstad.no
journalctl --user -b -o cat | grep -i -E 'quotamonitor|quota_monitor'
```

Ensure you actually logged out after installing. This package intentionally targets
GNOME 46 only; do not disable GNOME's version checking to install it on other versions.

To test the reader outside GNOME (one read-only refresh):

```bash
python3 extension/quota_reader.py --force
```

If the card is hidden or appears behind Ubuntu's desktop icons, the same data is
available from the top-bar menu. Report that behavior with the session type
(`echo "$XDG_SESSION_TYPE"`) and the journal output above. Desktop stacking is
implemented for GNOME 46 and recognizes Ubuntu's Desktop Icons NG surfaces, but
needs verification on the target Ubuntu desktop.

## Validation and development

The reader and display tests use synthetic RPC responses; they do not access a
real account or consume model quota:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
gjs -m tests/test_display.mjs
glib-compile-schemas --strict --dry-run extension/schemas
```

On the Mac, JavaScriptCore's `jsc -m tests/test_display.mjs` can run the pure display
tests instead of GJS. A GNOME runtime is required to check the real extension UI,
desktop stacking, Wayland interaction, and Shell enable/disable behavior.

To rebuild the transfer ZIP from the development folder:

```bash
python3 package.py
```

The extension follows the GNOME 45+ ES module format and the GNOME 46 Shell APIs:
[extension anatomy](https://gjs.guide/extensions/overview/anatomy.html),
[subprocess guide](https://gjs.guide/guides/gio/subprocesses.html), and
[GNOME 46 layout implementation](https://github.com/GNOME/gnome-shell/blob/46.0/js/ui/layout.js).
