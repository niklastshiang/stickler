import AppKit
import SticklerCore
import SwiftUI

/// The menu bar (design screen M8): File with Open, Open Recent and the Stickler folder; Help.
/// The app menu, Edit, View (Full Screen) and Window are the system's.
struct SticklerCommands: Commands {
    let model: AppModel

    static let help = URL(string: "https://github.com/niklastshiang/stickler#readme")

    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Divider()
            Button("Remove Downloaded Models…") {
                Task { await Removal.ask(model) }
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
            Divider()
            Button("Choose Stickler Folder…") { Panels.chooseFolder(model) }
        }
        CommandGroup(replacing: .help) {
            Button("Stickler Help") {
                if let help = Self.help {
                    NSWorkspace.shared.open(help)
                }
            }
        }
    }
}
