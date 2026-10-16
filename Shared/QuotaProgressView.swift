import SwiftUI

/// Draw the fill directly so the app and WidgetKit use the same status colors
/// instead of relying on the system progress control's accent color.
struct QuotaProgressView: View {
    let remaining: Int?

    private var fraction: CGFloat {
        CGFloat(max(0, min(100, remaining ?? 0))) / 100
    }

    private var statusColor: Color {
        switch QuotaData.status(for: remaining) {
        case .green: .green
        case .yellow: .yellow
        case .red: .red
        case .unknown: .gray
        }
    }

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.18))
                Capsule()
                    .fill(statusColor)
                    .frame(width: geometry.size.width * fraction)
            }
        }
        .frame(height: 5)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Gjenværende kvote")
        .accessibilityValue(remaining.map { "\($0) %" } ?? "Ikke tilgjengelig")
    }
}
