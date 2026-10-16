import Foundation

struct QuotaData: Codable {
    var lastUpdated: Date? = nil
    /// Records whether the most recent attempt failed. Quota values themselves are
    /// deliberately retained until Codex supplies a newer successful snapshot.
    var lastRefreshFailed = false
    var fiveHourRemaining: Int? = nil
    var weeklyRemaining: Int? = nil
    var fiveHourReset: Date? = nil
    var weeklyReset: Date? = nil

    static let group = "group.no.hegstad.quotamonitor"
    static let key = "quota-data-v1"

    init(
        lastUpdated: Date? = nil,
        lastRefreshFailed: Bool = false,
        fiveHourRemaining: Int? = nil,
        weeklyRemaining: Int? = nil,
        fiveHourReset: Date? = nil,
        weeklyReset: Date? = nil
    ) {
        self.lastUpdated = lastUpdated
        self.lastRefreshFailed = lastRefreshFailed
        self.fiveHourRemaining = fiveHourRemaining
        self.weeklyRemaining = weeklyRemaining
        self.fiveHourReset = fiveHourReset
        self.weeklyReset = weeklyReset
    }

    private enum CodingKeys: String, CodingKey {
        case lastUpdated, lastRefreshFailed, fiveHourRemaining, weeklyRemaining, fiveHourReset, weeklyReset
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        lastUpdated = try values.decodeIfPresent(Date.self, forKey: .lastUpdated)
        // Older versions have no failure marker; treat their stored quota as valid.
        lastRefreshFailed = try values.decodeIfPresent(Bool.self, forKey: .lastRefreshFailed) ?? false
        fiveHourRemaining = try values.decodeIfPresent(Int.self, forKey: .fiveHourRemaining)
        weeklyRemaining = try values.decodeIfPresent(Int.self, forKey: .weeklyRemaining)
        fiveHourReset = try values.decodeIfPresent(Date.self, forKey: .fiveHourReset)
        weeklyReset = try values.decodeIfPresent(Date.self, forKey: .weeklyReset)
    }

    static func load() -> QuotaData {
        guard let defaults = UserDefaults(suiteName: group),
              let raw = defaults.data(forKey: key),
              let result = try? JSONDecoder().decode(QuotaData.self, from: raw) else {
            return QuotaData()
        }
        return result
    }

    func save() {
        guard let raw = try? JSONEncoder().encode(self) else { return }
        UserDefaults(suiteName: Self.group)?.set(raw, forKey: Self.key)
    }

    static func countdown(_ date: Date?, now: Date = .now) -> String {
        guard let date else { return "Ikke registrert" }
        let seconds = date.timeIntervalSince(now)
        if seconds <= 0 { return "Tidspunkt passert – oppdater status" }
        let formatter = DateComponentsFormatter()
        formatter.unitsStyle = .abbreviated
        formatter.allowedUnits = seconds >= 86_400 ? [.day, .hour, .minute] : [.hour, .minute]
        formatter.maximumUnitCount = seconds >= 86_400 ? 3 : 2
        formatter.zeroFormattingBehavior = .dropAll
        return formatter.string(from: seconds) ?? "Ikke registrert"
    }

    static func percent(_ value: Int?) -> String {
        guard let value else { return "Ukjent" }
        return "\(max(0, min(100, value))) %"
    }

    static func formattedReset(_ date: Date?, now: Date = .now, locale: Locale = .current) -> String {
        guard let date else { return "Ikke registrert" }
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = .current
        formatter.setLocalizedDateFormatFromTemplate(Calendar.current.isDate(date, inSameDayAs: now) ? "Hm" : "EEE d MMM Hm")
        return formatter.string(from: date)
    }

    static func resetDescription(_ date: Date?, now: Date = .now) -> String {
        "\(formattedReset(date, now: now)) (\(countdown(date, now: now)))"
    }

    static func lastUpdatedDescription(_ date: Date?, now: Date = .now) -> String {
        guard let date else { return "Sist oppdatert: aldri" }
        let formatter = DateFormatter()
        formatter.locale = .current
        formatter.timeZone = .current
        formatter.setLocalizedDateFormatFromTemplate(Calendar.current.isDate(date, inSameDayAs: now) ? "Hm" : "EEE d MMM Hm")
        return "Sist oppdatert \(formatter.string(from: date))"
    }

    static func status(for remaining: Int?) -> QuotaStatus {
        guard let remaining else { return .unknown }
        switch remaining {
        case 50...: return .green
        case 20...: return .yellow
        default: return .red
        }
    }

    var lowestRemaining: Int? {
        [fiveHourRemaining, weeklyRemaining].compactMap { $0 }.min()
    }
}

enum QuotaStatus {
    case green, yellow, red, unknown
}
