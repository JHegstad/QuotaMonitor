import AppKit
import SwiftUI
import WidgetKit

@MainActor final class QuotaModel: ObservableObject {
    @Published var quota = QuotaData.load()
    @Published var message = "Venter på første Codex-oppdatering"
    @Published var busy = false
    private var timer: Timer?

    init() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 120, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func refresh() {
        guard !busy else { return }
        busy = true
        message = "Henter kvoter fra Codex …"
        Task.detached(priority: .utility) {
            let result = Result { try CodexReader.read() }
            await MainActor.run {
                self.busy = false
                switch result {
                case .success(let snapshot):
                    self.quota.fiveHourRemaining = snapshot.five
                    self.quota.weeklyRemaining = snapshot.week
                    self.quota.fiveHourReset = snapshot.fiveReset
                    self.quota.weeklyReset = snapshot.weekReset
                    self.quota.lastUpdated = .now
                    self.quota.lastRefreshFailed = false
                    self.quota.save()
                    WidgetCenter.shared.reloadAllTimelines()
                    self.message = "Oppdatert: \(Date.now.formatted(date: .omitted, time: .shortened))"
                case .failure(let error):
                    self.quota.lastRefreshFailed = true
                    self.quota.save()
                    WidgetCenter.shared.reloadAllTimelines()
                    self.message = "Kunne ikke oppdatere – viser siste data (\(error.localizedDescription))"
                }
            }
        }
    }
}

@main struct QuotaMonitorApp: App {
    @StateObject private var model = QuotaModel()
    var body: some Scene {
        MenuBarExtra {
            VStack(alignment: .leading, spacing: 12) {
                Text("Work + Codex").font(.headline)
                quotaRow("5 timer", model.quota.fiveHourRemaining, model.quota.fiveHourReset)
                quotaRow("Uke", model.quota.weeklyRemaining, model.quota.weeklyReset)
                Divider()
                Text(model.message).font(.caption).foregroundStyle(.secondary)
                Text(QuotaData.lastUpdatedDescription(model.quota.lastUpdated))
                    .font(.caption).foregroundStyle(.secondary)
                Button(model.busy ? "Oppdaterer …" : "Oppdater fra Codex nå") { model.refresh() }
                    .disabled(model.busy)
                Text("Oppdateres automatisk hvert 2. minutt.")
                    .font(.caption2).foregroundStyle(.secondary)
                Text("Ingen automatisk påfylling.").font(.caption2)
                Divider()
                Button("Avslutt QuotaMonitor") { NSApplication.shared.terminate(nil) }
            }.frame(width: 320).padding(14)
        } label: {
            Label("Work \(model.quota.lowestRemaining.map { "\($0) %" } ?? "--")", systemImage: "chart.bar.xaxis")
        }.menuBarExtraStyle(.window)
    }

    @ViewBuilder
    private func quotaRow(_ title: String, _ remaining: Int?, _ reset: Date?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack { Text(title); Spacer(); Text(QuotaData.percent(remaining)).monospacedDigit() }
            QuotaProgressView(remaining: remaining)
            Text("Reset: \(QuotaData.resetDescription(reset))").font(.caption)
        }
    }

}
