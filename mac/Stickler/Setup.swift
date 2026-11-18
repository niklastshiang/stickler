import AppKit
import SticklerCore
import SwiftUI

/// A text of the String Catalog (from po/) with its placeholders filled: `%1$@` with a string,
/// `%1$lld` with a count (the catalog picks the plural form for the reader's language).
func localized(_ key: String, _ arguments: any CVarArg...) -> String {
    let format = Bundle.main.localizedString(forKey: key, value: key, table: nil)
    return String(format: format, locale: Locale.current, arguments: arguments)
}

/// The first start's sheets over the empty window (design screens M1–M3), as the core's state
/// says; only the core's next state closes them.
enum SetupSheet: String, Identifiable {
    case consent, download, failed

    /// One identity for all three, so the sheet stays up from consent to download to a
    /// failure instead of closing and opening again; its content follows the state.
    var id: String { "setup" }

    init?(_ screen: Screen) {
        switch screen {
        case .consent: self = .consent
        case .settingUp: self = .download
        case .setupFailed: self = .failed
        default: return nil
        }
    }
}

struct SetupSheetView: View {
    let model: AppModel

    var body: some View {
        Group {
            switch model.state.screen {
            case .consent(let consent):
                ConsentSheet(model: model, consent: consent)
            case .settingUp(let settingUp):
                StepsPage(
                    title: "Downloading the Models",
                    subtitle: LocalizedStringKey(
                        "If this is interrupted, Stickler picks up where it stopped the next "
                            + "time you open it."),
                    steps: settingUp.steps, canCancel: model.state.can.cancel,
                    cancel: model.cancel)
            case .setupFailed(let failed):
                SetupFailedSheet(model: model, failed: failed)
            default:
                EmptyView()
            }
        }
        .frame(width: 560)
        .interactiveDismissDisabled()
    }
}

/// M1: what is downloaded, what each model does, its licence and size; "Not Now" and the
/// download.
struct ConsentSheet: View {
    let model: AppModel
    let consent: Consent

    var body: some View {
        VStack(spacing: 18) {
            Image(nsImage: NSApplication.shared.applicationIconImage)
                .resizable()
                .frame(width: 64, height: 64)
            Text("Welcome to Stickler")
                .font(.title2.bold())
            Text(verbatim: intro)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            GroupBox {
                VStack(spacing: 0) {
                    ForEach(consent.models, id: \.id) { item in
                        HStack(alignment: .firstTextBaseline) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: "\(item.name) · \(item.does)")
                                Text(verbatim: item.licence)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer()
                            Text(verbatim: item.size)
                                .monospacedDigit()
                        }
                        .padding(.vertical, 6)
                        Divider()
                    }
                    HStack {
                        Text("Together, on disk")
                        Spacer()
                        Text(verbatim: localized("about %1$@", consent.totalSize))
                            .font(.headline)
                            .monospacedDigit()
                    }
                    .padding(.vertical, 6)
                }
            }
            if consent.models.contains(where: { $0.id == "adtof" }) {
                Text(
                    LocalizedStringKey(
                        "By downloading, you accept that ADTOF’s model is used for "
                            + "non-commercial purposes only."))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            HStack {
                Spacer()
                Button("Not Now") { model.notNow() }
                    .keyboardShortcut(.cancelAction)
                    .disabled(!model.state.can.notNow)
                Button(localized("Download %1$@", consent.totalSize)) { model.agree() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!model.state.can.agree)
            }
        }
        .padding(24)
    }

    private var intro: String {
        localized(
            "To hear the drums, Stickler needs %1$lld trained models. They are downloaded once; "
                + "after that, everything runs on this computer, offline.",
            consent.models.count)
    }
}

/// M3: which server did not answer; what is done stays; "Later" and "Try Again".
struct SetupFailedSheet: View {
    let model: AppModel
    let failed: SetupFailed
    @State private var showsDetails = false

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text("A Download Server Is Not Answering")
                .font(.title2.bold())
            Text(
                verbatim: localized(
                    "Stickler could not reach %1$@. Everything that is done stays downloaded.",
                    failed.server)
            )
            .multilineTextAlignment(.center)
            .foregroundStyle(.secondary)
            GroupBox {
                VStack(spacing: 0) {
                    ForEach(Array(failed.steps.enumerated()), id: \.element.id) { index, step in
                        if index > 0 {
                            Divider()
                        }
                        HStack {
                            let done = step.state == .done
                            Image(systemName: done ? "checkmark.circle.fill" : "xmark.circle")
                                .foregroundStyle(done ? .green : .secondary)
                            Text(verbatim: step.label)
                            Spacer()
                            Text(step.state == .done ? "Ready" : "Not reached")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 6)
                    }
                }
            }
            DisclosureGroup("Technical Details", isExpanded: $showsDetails) {
                Text(verbatim: failed.details)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                Spacer()
                Button("Later") { model.notNow() }
                    .keyboardShortcut(.cancelAction)
                    .disabled(!model.state.can.notNow)
                Button("Try Again") { model.retrySetup() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!model.state.can.retrySetup)
            }
        }
        .padding(24)
    }
}

/// Stickler › "Remove Downloaded Models…": the sizes first, then the question (`Asking`), with
/// the checkbox for everything else.
@MainActor
enum Removal {
    static func ask(_ model: AppModel) async {
        guard let sizes = await model.removalSizes(), let everything = Ask.reader.removal(sizes)
        else { return }
        model.removeModels(everything: everything)
    }
}
