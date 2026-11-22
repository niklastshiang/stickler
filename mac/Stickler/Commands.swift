import AppKit
import SticklerCore
import SwiftUI

/// The menu bar (design screen M8): File with Open, Open Recent, Export and Close Song; View
/// with the note size; Help with the guide and the licences of what the app ships.
/// The app menu, Edit, the rest of View (Full Screen) and Window are the system's.
struct SticklerCommands: Commands {
    let model: AppModel

    static let help = URL(string: "https://github.com/niklastshiang/stickler#readme")
    /// The licences inside the app (SPEC.md, module `mac-package`, scope 2); a development
    /// build has no core of its own and so none to show.
    static let licences = CoreClient.licences()

    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Divider()
            Button("Back Up…") { Backups.backUp(model) }
                .disabled(model.phase != .running)
            Button("Restore Backup…") {
                Task { await Backups.restore(model) }
            }
            .disabled(!(model.phase == .running && model.state.can.removeModels))
            Button("Remove Downloaded Models…") {
                Task { await Removal.ask(model) }
            }
            .disabled(!(model.phase == .running && model.state.can.removeModels))
            Button("Uninstall Stickler…") {
                Task { await Uninstalling.ask(model) }
            }
            .disabled(!(model.phase == .running && model.state.can.removeModels))
        }
        CommandGroup(replacing: .newItem) {
            Button("Open…") { Panels.openSong(model) }
                .keyboardShortcut("o")
                .disabled(!(model.phase == .running && model.state.can.open))
            Menu("Open Recent") {
                ForEach(model.recent.filter { !$0.missing }, id: \.path) { row in
                    Button(row.title) { model.open(row.path) }
                        .disabled(!model.state.can.open)
                }
                Divider()
                Button("Clear Menu") { model.clearRecent() }
                    .disabled(model.recent.isEmpty)
            }
            .disabled(model.phase != .running)
            Menu("Export") {
                ExportMenu(model: model)
            }
            .disabled(Exports.result(model) == nil)
        }
        CommandGroup(replacing: .saveItem) {
            CloseItem(model: model)
        }
        CommandGroup(before: .toolbar) {
            ZoomItems(model: model)
            Divider()
        }
        CommandGroup(replacing: .help) {
            Button("Stickler Help") {
                if let help = Self.help {
                    NSWorkspace.shared.open(help)
                }
            }
            Button("Licences") {
                if let licences = Self.licences {
                    NSWorkspace.shared.open(licences)
                }
            }
            .disabled(Self.licences == nil)
        }
    }
}

/// ⌘W: closes the song back to the empty window (`can_close`); on the empty window, or under a
/// setup sheet, the window itself, which quits the app.
struct CloseItem: View {
    let model: AppModel

    private var closesSong: Bool {
        model.phase == .running && model.state.can.close
    }

    var body: some View {
        Button(closesSong ? LocalizedStringKey("Close Song") : "Close Window") {
            if closesSong {
                model.close()
            } else {
                NSApp.mainWindow?.performClose(nil)
            }
        }
        .keyboardShortcut("w")
    }
}

/// View › Zoom In ⌘+, Zoom Out ⌘−, Actual Size ⌘0 (SPEC.md, module `mac-sheet`, scope 3): the
/// note size is the core's setting, so each item only sends its command.
@MainActor
enum ZoomMenu {
    struct Item: Identifiable {
        /// The item's text, a key of the String Catalog.
        let title: String
        /// Pressed with ⌘.
        let key: Character
        let act: @MainActor (SheetModel) -> Void

        var id: String { title }
    }

    static let items = [
        Item(title: "Zoom In", key: "+") { $0.zoomIn() },
        Item(title: "Zoom Out", key: "-") { $0.zoomOut() },
        Item(title: "Actual Size", key: "0") { $0.actualSize() }
    ]

    /// Only a shown result has a note size to change.
    static func enabled(_ model: AppModel) -> Bool {
        model.phase == .running && model.sheet.canZoom
    }
}

/// The View menu's zoom items, drawn from `ZoomMenu`.
struct ZoomItems: View {
    let model: AppModel

    var body: some View {
        ForEach(ZoomMenu.items) { item in
            Button(LocalizedStringKey(item.title)) { item.act(model.sheet) }
                .keyboardShortcut(KeyEquivalent(item.key))
                .disabled(!ZoomMenu.enabled(model))
        }
    }
}
