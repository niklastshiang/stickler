import AppKit
import SticklerCore
import SwiftUI

/// Design screen M7: the Export menu, in the toolbar and in File. Each item has the GTK
/// menu's second line.
struct ExportMenu: View {
    let model: AppModel

    var body: some View {
        Button {
            Task { await Exports.pdf(model) }
        } label: {
            Text("Sheet Music (PDF)…")
            Text("To print or to read on a tablet")
        }
        Button {
            Exports.musicXML(model)
        } label: {
            Text("MusicXML…")
            Text("To edit in MuseScore or another notation program")
        }
        Button {
            Task { await Exports.drumTrack(model) }
        } label: {
            Text("Drum Track…")
            Text("As FLAC or WAV")
        }
        Divider()
        Button {
            Exports.openWith(model)
        } label: {
            Text("Open With…")
            Text("The MusicXML in another program")
        }
    }
}

/// What the Export items do: a save panel with the GTK app's name, then one command.
@MainActor
enum Exports {
    /// The result being shown, if any.
    static func result(_ model: AppModel) -> SongResult? {
        if case .result(let result) = model.state.screen, model.state.can.export {
            return result
        }
        return nil
    }

    /// The sheet music as an A4 PDF, written by the app (the core engraves the pages).
    static func pdf(_ model: AppModel) async {
        guard let result = result(model), let dest = save(ExportName.pdf(result.song)),
            let pages = await model.a4Pages()
        else { return }
        do {
            try await SheetPDF.make(pages).write(to: dest)
            let saved = localized("Saved “%1$@”", dest.lastPathComponent)
            model.tell(Notice(text: saved, opens: dest.path))
        } catch {
            let failed = localized("Could not save: %1$@", error.localizedDescription)
            model.tell(Notice(text: failed, opens: nil))
        }
    }

    static func musicXML(_ model: AppModel) {
        guard let result = result(model),
            let dest = save(ExportName.musicXML(result.song))
        else { return }
        model.exportMusicXML(to: dest.path)
    }

    /// The cost first (Demucs may be downloaded before), then where to save.
    static func drumTrack(_ model: AppModel) async {
        guard let result = result(model), let cost = await model.drumTrackCost() else { return }
        let alert = NSAlert()
        alert.messageText = localized("Save the Drum Track?")
        alert.informativeText = cost.text
        alert.addButton(withTitle: localized("Choose Where to Save…"))
        alert.addButton(withTitle: localized("Cancel"))
        guard alert.runModal() == .alertFirstButtonReturn,
            let dest = save(drumTrackName(result.song))
        else { return }
        model.exportDrumTrack(to: dest.path)
    }

    /// "Eye of the Tiger (drums).flac", "(drums)" in the reader's language.
    static func drumTrackName(_ song: String) -> String {
        localized("%1$@ (drums)", ExportName.base(of: song)) + ".flac"
    }

    /// The MusicXML in a program the reader picks.
    static func openWith(_ model: AppModel) {
        guard let result = result(model) else { return }
        let panel = NSOpenPanel()
        panel.title = localized("Open With…")
        panel.directoryURL = URL(fileURLWithPath: "/Applications")
        panel.allowedContentTypes = [.application]
        if panel.runModal() == .OK, let app = panel.url {
            NSWorkspace.shared.open(
                [URL(fileURLWithPath: result.musicxml)], withApplicationAt: app,
                configuration: NSWorkspace.OpenConfiguration())
        }
    }

    static func save(_ name: String) -> URL? {
        let panel = NSSavePanel()
        panel.title = localized("Save As")
        panel.nameFieldStringValue = name
        panel.canCreateDirectories = true
        return panel.runModal() == .OK ? panel.url : nil
    }
}

/// The bar at the bottom of the window (M7): the newest notice, with "Show in Finder" for a
/// file just saved; it goes after a few seconds or with its close button.
struct NoticeBar: View {
    let model: AppModel
    let notice: Notice

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: notice.opens == nil ? "info.circle" : "checkmark.circle.fill")
                .foregroundStyle(notice.opens == nil ? Color.secondary : Color.green)
            Text(verbatim: notice.text)
                .lineLimit(2)
            Spacer()
            if let opens = notice.opens {
                Button("Show in Finder") {
                    NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: opens)])
                }
            }
            Button {
                model.dismissNotice()
            } label: {
                Image(systemName: "xmark")
            }
            .buttonStyle(.borderless)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.bar)
        .task(id: model.noticeSerial) {
            let shown = model.noticeSerial
            try? await Task.sleep(for: .seconds(8))
            if model.noticeSerial == shown {
                model.dismissNotice()
            }
        }
    }
}
