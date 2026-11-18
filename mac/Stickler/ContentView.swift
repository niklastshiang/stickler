import SticklerCore
import SwiftUI
import UniformTypeIdentifiers

/// The window: the toolbar with title and Open, and the page the model's phase and the core's
/// state call for.
struct ContentView: View {
    let model: AppModel

    var body: some View {
        page
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .navigationTitle(model.title)
            .navigationSubtitle(model.subtitle)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Panels.openSong(model)
                    } label: {
                        Label("Open…", systemImage: "folder")
                    }
                    .help(Text("Open a Song"))
                    .disabled(!canOpen)
                }
            }
            .dropDestination(for: URL.self) { urls, _ in
                guard canOpen, let song = urls.first(where: Panels.isSong) else { return false }
                model.open(song.path)
                return true
            }
    }

    private var canOpen: Bool {
        model.phase == .running && model.state.can.open
    }

    @ViewBuilder private var page: some View {
        switch model.phase {
        case .needsFolder(let problem):
            FolderView(problem: problem) { Panels.chooseFolder(model) }
        case .running, .stopped:
            switch model.state.screen {
            case .result:
                ResultPlaceholder()
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
        let panel = NSOpenPanel()
        panel.title = String(localized: "Open a Song")
        panel.allowedContentTypes = [.audio]
        if panel.runModal() == .OK, let song = panel.url {
            model.open(song.path)
        }
    }

    static func chooseFolder(_ model: AppModel) {
        let panel = NSOpenPanel()
        panel.title = String(localized: "Choose Stickler Folder…")
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        if panel.runModal() == .OK, let folder = panel.url {
            model.choose(folder: folder)
        }
    }

    /// A dropped file the core can read: a sound file by its type.
    nonisolated static func isSong(_ url: URL) -> Bool {
        UTType(filenameExtension: url.pathExtension)?.conforms(to: .audio) ?? false
    }
}
