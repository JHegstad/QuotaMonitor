import Foundation

// Read-only Codex app-server RPC. Never starts a model turn or reads auth files.
enum CodexReader {
    struct Snapshot {
        let five: Int?
        let week: Int?
        let fiveReset: Date?
        let weekReset: Date?
    }

    static func executable() -> String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let candidates = ["/opt/homebrew/bin/codex", "/usr/local/bin/codex", home + "/.npm-global/bin/codex", home + "/.local/bin/codex", home + "/.bun/bin/codex"]
        return candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) })
    }

    static func read() throws -> Snapshot {
        guard let path = executable() else { throw NSError(domain: "QuotaMonitor", code: 1, userInfo: [NSLocalizedDescriptionKey: "Codex CLI finnes ikke i standardstiene. Installer Codex CLI."]) }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: path)
        process.arguments = ["app-server", "--listen", "stdio://"]
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errors
        try process.run()
        defer {
            if process.isRunning { process.terminate() }
            try? input.fileHandleForWriting.close()
            try? output.fileHandleForReading.close()
            try? errors.fileHandleForReading.close()
        }
        func send(_ obj: [String: Any]) throws {
            let bytes = try JSONSerialization.data(withJSONObject: obj)
            input.fileHandleForWriting.write(bytes + Data([10]))
        }
        try send(["id": 1, "method": "initialize", "params": ["clientInfo": ["name": "quota_monitor", "title": "Quota Monitor", "version": "2.0"]]])
        try send(["method": "initialized", "params": [:]])
        try send(["id": 2, "method": "account/rateLimits/read", "params": [:]])

        // Blocking pipe reads happen only on a detached worker, never on the UI thread.
        // A watchdog terminates a stuck child and unblocks the read.
        let watchdog = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 12, execute: watchdog)
        defer { watchdog.cancel() }
        var buffer = Data()
        while true {
            let chunk = output.fileHandleForReading.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)
            while let end = buffer.firstIndex(of: 10) {
                let line = Data(buffer[..<end]); buffer.removeSubrange(...end)
                guard let json = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
                      (json["id"] as? Int) == 2 else { continue }
                if let error = json["error"] { throw NSError(domain: "QuotaMonitor", code: 2, userInfo: [NSLocalizedDescriptionKey: "Codex returnerte feil: \(error)"]) }
                guard let result = json["result"] as? [String: Any] else { break }
                let byId = result["rateLimitsByLimitId"] as? [String: Any]
                let limits = (byId?["codex"] as? [String: Any]) ?? (result["rateLimits"] as? [String: Any])
                guard let limits else { throw NSError(domain: "QuotaMonitor", code: 3, userInfo: [NSLocalizedDescriptionKey: "Ingen Codex-kvoter i svaret. Sjekk innlogging med codex /status."]) }
                let windows = [limits["primary"] as? [String: Any], limits["secondary"] as? [String: Any]].compactMap { $0 }
                func window(_ duration: Int) -> [String: Any]? { windows.first { ($0["windowDurationMins"] as? Int) == duration } }
                func remaining(_ w: [String: Any]?) -> Int? {
                    guard let n = w?["usedPercent"] as? NSNumber else { return nil }
                    return max(0, min(100, Int((100 - n.doubleValue).rounded())))
                }
                func reset(_ w: [String: Any]?) -> Date? {
                    guard let n = w?["resetsAt"] as? NSNumber else { return nil }
                    return Date(timeIntervalSince1970: n.doubleValue)
                }
                let five = window(300), week = window(10080)
                guard five != nil || week != nil else { throw NSError(domain: "QuotaMonitor", code: 4, userInfo: [NSLocalizedDescriptionKey: "Codex returnerte ingen 5-timers- eller ukesvinduer."]) }
                return Snapshot(five: remaining(five), week: remaining(week), fiveReset: reset(five), weekReset: reset(week))
            }
        }
        throw NSError(domain: "QuotaMonitor", code: 5, userInfo: [NSLocalizedDescriptionKey: "Codex svarte ikke innen 12 sekunder. Kontroller at Codex CLI er innlogget."])
    }
}
