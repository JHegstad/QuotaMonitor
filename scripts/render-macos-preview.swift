import Foundation

// Build a small, offline renderer from the actual widget view and shared types.
// No QuotaModel is started and no Codex request or App Group write is performed.
let root = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent()
let build = root.appendingPathComponent("build/widget-preview", isDirectory: true)
let images = root.appendingPathComponent("docs/images", isDirectory: true)
try FileManager.default.createDirectory(at: build, withIntermediateDirectories: true)
try FileManager.default.createDirectory(at: images, withIntermediateDirectories: true)

let shared = try ["Shared/QuotaData.swift", "Shared/QuotaProgressView.swift"]
    .map { try String(contentsOf: root.appendingPathComponent($0), encoding: .utf8) }
    .joined(separator: "\n")
let widget = try String(contentsOf: root.appendingPathComponent("Widget/QuotaWidget.swift"), encoding: .utf8)
guard let mainMarker = widget.range(of: "\n@main\n") else {
    fatalError("Could not locate the widget entry point; review the renderer before updating the preview.")
}
let widgetViews = String(widget[..<mainMarker.lowerBound])
let renderer = #"""

import AppKit

@main
struct WidgetPreviewRenderer {
    @MainActor
    static func main() throws {
        _ = NSApplication.shared
        NSApplication.shared.appearance = NSAppearance(named: .darkAqua)
        let formatter = ISO8601DateFormatter()
        let now = formatter.date(from: "2026-10-16T10:25:00+02:00")!
        let example = QuotaData(
            lastUpdated: now,
            fiveHourRemaining: 82,
            weeklyRemaining: 61,
            fiveHourReset: formatter.date(from: "2026-10-16T14:37:00+02:00"),
            weeklyReset: formatter.date(from: "2026-10-22T10:50:00+02:00")
        )
        let preview = ZStack {
            Color(red: 0.13, green: 0.13, blue: 0.14)
            QuotaWidgetView(entry: QuotaEntry(date: now, quota: example))
        }
        .frame(width: 360, height: 190)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .environment(\.colorScheme, .dark)

        let renderer = ImageRenderer(content: preview)
        renderer.scale = 3
        guard let image = renderer.cgImage,
              let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
            fatalError("SwiftUI could not render the preview.")
        }
        try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
    }
}
"""#

let source = build.appendingPathComponent("WidgetPreview.swift")
try (shared + "\n" + widgetViews + "\n" + renderer).write(to: source, atomically: true, encoding: .utf8)
let executable = build.appendingPathComponent("render-widget")

func run(_ executable: URL, _ arguments: [String]) throws {
    let process = Process()
    process.executableURL = executable
    process.arguments = arguments
    try process.run()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else {
        throw NSError(domain: "QuotaMonitorPreview", code: Int(process.terminationStatus), userInfo: [
            NSLocalizedDescriptionKey: "Preview renderer failed: \(executable.lastPathComponent)"
        ])
    }
}

try run(URL(fileURLWithPath: "/usr/bin/xcrun"), [
    "swiftc", "-parse-as-library", "-module-cache-path", build.appendingPathComponent("ModuleCache").path,
    source.path, "-o", executable.path
])
let output = images.appendingPathComponent("macos-widget.png")
try run(executable, [output.path])
print(output.path)
