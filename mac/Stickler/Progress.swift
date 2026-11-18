import SticklerCore
import SwiftUI

/// Design screen M5: what runs, step by step, with Cancel (an analysis, a drum track).
struct StepsPage: View {
    let title: LocalizedStringKey
    let subtitle: LocalizedStringKey?
    let steps: [Step]
    let cancel: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 6) {
                Text(title)
                    .font(.title2.bold())
                if let subtitle {
                    Text(subtitle)
                        .foregroundStyle(.secondary)
                }
            }
            GroupBox {
                VStack(spacing: 0) {
                    ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                        if index > 0 {
                            Divider()
                        }
                        StepRow(step: step)
                    }
                }
            }
            .frame(maxWidth: 460)
            Button("Cancel", action: cancel)
                .controlSize(.large)
                .keyboardShortcut(.cancelAction)
        }
        .padding(32)
    }
}

struct StepRow: View {
    let step: Step

    var body: some View {
        HStack(spacing: 12) {
            mark
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: step.label)
                if !step.detail.isEmpty {
                    Text(verbatim: step.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Text(status)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 8)
        .opacity(step.state == .waiting ? 0.6 : 1)
    }

    @ViewBuilder private var mark: some View {
        switch step.state {
        case .done:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .running:
            ProgressView()
                .controlSize(.small)
        case .waiting:
            Image(systemName: "circle.dotted")
                .foregroundStyle(.tertiary)
        }
    }

    private var status: LocalizedStringKey {
        switch step.state {
        case .done: "Done"
        case .running: "Running"
        case .waiting: "Waiting"
        }
    }
}

/// A song that went wrong: what happened, its technical details, and the way on.
struct FailurePage: View {
    let model: AppModel
    let failure: Failure

    var body: some View {
        TroublePage(
            title: Text(verbatim: failure.title),
            description: Text(verbatim: failure.description),
            details: failure.details
        ) {
            Button("Open Another Song…") { Panels.openSong(model) }
                .controlSize(.large)
            if model.state.can.retry {
                Button("Try Again") { model.retry() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
            }
        }
    }
}

/// The core has ended: the window says so and starts a new one on request.
struct StoppedPage: View {
    let model: AppModel
    let end: CoreEnd

    var body: some View {
        TroublePage(
            title: Text("Stickler Stopped Unexpectedly"),
            description: Text(
                LocalizedStringKey(
                    "The part of Stickler that listens to the songs has ended. A song it was "
                        + "writing has to be opened again; finished ones are kept.")),
            details: end.technicalDetails
        ) {
            Button("Start Again") { model.startAgain() }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
    }
}

/// A warning with a title, a line, "Technical Details" to unfold, and buttons.
struct TroublePage<Actions: View>: View {
    let title: Text
    let description: Text
    let details: String
    @ViewBuilder let actions: () -> Actions
    @State private var showsDetails = false

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
            title
                .font(.title2.bold())
            description
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            DisclosureGroup("Technical Details", isExpanded: $showsDetails) {
                ScrollView {
                    Text(verbatim: details)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 160)
            }
            .frame(maxWidth: 520)
            HStack(spacing: 12, content: actions)
        }
        .padding(32)
        .frame(maxWidth: 600)
    }
}
