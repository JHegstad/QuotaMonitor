# QuotaMonitor widget images

- `macos-widget.png`: an offline render of the actual `QuotaWidgetView` and shared
  progress component, in dark appearance with example data. It is a UI preview,
  not a capture of live account data or the entire macOS desktop.
- `linux-widget.png`: the user's Ubuntu 24.04 / GNOME Shell 46 screenshot from
  16 October 2026. Copied without editing; it includes the desktop quota card and
  the matching limiting-quota indicator in the top bar.

The macOS preview can be rebuilt on a Mac with Xcode installed:

```bash
swift scripts/render-macos-preview.swift
```

Run that command from the repository root. The renderer compiles the actual widget
view into a temporary executable under the ignored `build/widget-preview` folder
and writes `docs/images/macos-widget.png` at 3× resolution. It does not launch the
menu-bar app, contact Codex, read a signed-in account, or write App Group quota data.

The illustrated macOS reset times come from a fixed example snapshot, dated
16 October 2026. The installed application always displays Codex's returned reset
times. The screenshot and preview are documentation assets only.
