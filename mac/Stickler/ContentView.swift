import SticklerCore
import SwiftUI
import UniformTypeIdentifiers

/// The window: the toolbar with title and Open, and the page the model's phase and the core's
/// state call for.
struct ContentView: View {
    let model: AppModel
    /// The corrections inspector left open or closed (M11), kept across launches.
    @AppStorage(CorrectionsMenu.shownKey) private var correctionsShown = false

    var body: some View {
        page
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if let notice = model.notice, !controls {
                    NoticeBar(model: model, notice: notice)
                }
            }
            // the controls float over the sheet; the notice sits above them (M10)
            .overlay(alignment: .bottom) {
                if controls {
                    PlaybackOverlay(model: model)
                }
            }
            // the corrections at the trailing edge, with a result only (M11)
            .inspector(isPresented: inspectorShown) {
                if let controls = CorrectionsMenu.controls(model) {
                    CorrectionsInspector(model: model, controls: controls)
                }
            }
            .navigationTitle(model.title)
            .navigationSubtitle(model.subtitle)
            .toolbar {
                // a correction's notes being written (owner, 2026-11-25: before Open and
                // Export, as the system puts its own items only before the title)
                if CorrectionsMenu.correcting(model) {
                    ToolbarItem(placement: .primaryAction) {
                        ProgressView()
                            .controlSize(.small)
                            .accessibilityLabel(Text("Write the notes"))
                    }
                    .sharedBackgroundVisibility(.hidden)
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Panels.openSong(model)
                    } label: {
                        Label("Open…", systemImage: "folder")
                    }
                    .help(Text("Open a Song"))
                    .disabled(!canOpen)
                }
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        ExportMenu(model: model)
                    } label: {
                        Label("Export", systemImage: "square.and.arrow.up")
                    }
                    .help(Text("Export"))
                    // said again for VoiceOver: built with the macOS 26 SDK and run on
                    // macOS 27, the menu button's name was its arrow's, "chevron.pulldown"
                    .accessibilityLabel(Text("Export"))
                    .disabled(Exports.result(model) == nil)
                }
                ToolbarSpacer(.fixed, placement: .primaryAction)
                ToolbarItem(placement: .primaryAction) {
                    Toggle(isOn: inspectorShown) {
                        Label("Corrections", systemImage: "sidebar.trailing")
                    }
                    .toggleStyle(.button)
                    .help(Text("Corrections"))
                    .disabled(!CorrectionsMenu.enabled(model))
                }
            }
            .sheet(item: setupSheet) { _ in
                SetupSheetView(model: model)
            }
            .dropDestination(for: URL.self) { urls, _ in
                guard canOpen, let song = urls.first(where: Panels.isSong) else { return false }
                model.open(song.path)
                return true
            }
    }

    /// The first start's sheet the core's state calls for; only its next state closes it.
    private var setupSheet: Binding<SetupSheet?> {
        Binding(
            get: { model.phase == .running ? SetupSheet(model.state.screen) : nil },
            set: { _ in })
    }

    /// The inspector is on the window when left open and there is a result to correct.
    private var inspectorShown: Binding<Bool> {
        Binding(
            get: { CorrectionsMenu.presented(shown: correctionsShown, model) },
            set: { correctionsShown = $0 })
    }

    /// A shown result can be played: its controls are on the window (M10).
    private var controls: Bool {
        model.phase == .running && model.playback.canPlay
    }

    private var canOpen: Bool {
        model.phase == .running && model.state.can.open
    }

    @ViewBuilder private var page: some View {
        switch model.phase {
        case .launching:
            Color.clear  // the core starts with the app; its first state follows at once
        case .stopped(let end):
            StoppedPage(model: model, end: end)
        case .running:
            switch model.state.screen {
            case .analysing(let analysing):
                StepsPage(
                    title: "Writing the Drum Part", subtitle: "Takes about 15 seconds",
                    steps: analysing.steps, canCancel: model.state.can.cancel,
                    cancel: model.cancel)
            case .exporting(let exporting):
                StepsPage(
                    title: "Saving the Drum Track", subtitle: nil, steps: exporting.steps,
                    canCancel: model.state.can.cancel, cancel: model.cancel)
            case .failed(let failure):
                FailurePage(model: model, failure: failure)
            case .result:
                SheetView(model: model)
            default:
                EmptyWindowView(model: model)
            }
        }
    }
}

/// The open panels of the window and the File menu.
@MainActor
enum Panels {
    static func openSong(_ model: AppModel) {
        if let song = Ask.reader.song() {
            model.open(song.path)
        }
    }

    /// A dropped file the core can read: a sound file by its type.
    nonisolated static func isSong(_ url: URL) -> Bool {
        UTType(filenameExtension: url.pathExtension)?.conforms(to: .audio) ?? false
    }
}
