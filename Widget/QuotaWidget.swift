import WidgetKit
import SwiftUI

struct QuotaEntry: TimelineEntry {
    var date: Date
    var quota: QuotaData
}

struct QuotaProvider: TimelineProvider {
    func placeholder(in context: Context) -> QuotaEntry { QuotaEntry(date: .now, quota: .init()) }
    func getSnapshot(in context: Context, completion: @escaping (QuotaEntry) -> Void) {
        completion(QuotaEntry(date: .now, quota: .load()))
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<QuotaEntry>) -> Void) {
        let now = Date()
        let data = QuotaData.load()
        let entries = (0..<12).map { i in
            QuotaEntry(date: now.addingTimeInterval(TimeInterval(i * 300)), quota: data)
        }
        completion(Timeline(entries: entries, policy: .atEnd))
    }
}

struct QuotaWidgetView: View {
    let entry: QuotaEntry
    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text("WORK + CODEX").font(.caption.bold())
            row("5 timer", entry.quota.fiveHourRemaining, entry.quota.fiveHourReset)
            row("Uke", entry.quota.weeklyRemaining, entry.quota.weeklyReset)
            Divider()
            Text(QuotaData.lastUpdatedDescription(entry.quota.lastUpdated, now: entry.date))
                .font(.caption2).foregroundStyle(.secondary)
            if entry.quota.lastRefreshFailed {
                Text("Kunne ikke oppdatere – viser siste data")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .containerBackground(for: .widget) { Color(nsColor: .windowBackgroundColor) }
    }

    @ViewBuilder
    private func row(_ title: String, _ remaining: Int?, _ reset: Date?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(title).font(.subheadline.bold())
                Spacer()
                Text(QuotaData.percent(remaining)).font(.subheadline.monospacedDigit())
            }
            QuotaProgressView(remaining: remaining)
            Text("Reset: \(QuotaData.resetDescription(reset, now: entry.date))")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }

}

@main
struct QuotaWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "QuotaWidget", provider: QuotaProvider()) { entry in
            QuotaWidgetView(entry: entry)
        }
        .configurationDisplayName("ChatGPT kvoter")
        .description("Felles Work/Codex-kvoter")
        .supportedFamilies([.systemMedium, .systemLarge])
    }
}
