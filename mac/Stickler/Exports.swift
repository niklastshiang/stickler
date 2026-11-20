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

/// What the Export items do: where to save (`Asking`) with the GTK app's name, then one
/// command.
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
        guard let result = result(model),
            let dest = Ask.reader.saveLocation(named: ExportName.pdf(result.song), endings: []),
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
            let dest = Ask.reader.saveLocation(named: ExportName.musicXML(result.song), endings: [])
        else { return }
        model.exportMusicXML(to: dest.path)
    }

    /// The cost first (Demucs may be downloaded before), then where to save.
    static func drumTrack(_ model: AppModel) async {
        guard let result = result(model), let cost = await model.drumTrackCost(),
            Ask.reader.drumTrack(cost: cost.text),
            let dest = Ask.reader.saveLocation(
                named: drumTrackName(result.song), endings: drumTrackEndings)
        else { return }
        model.exportDrumTrack(to: dest.path)
    }

    /// What a drum track can be saved as: the app's own ffmpeg writes these two only (SPEC.md,
    /// module `mac-package`, decision 2), while the core would take `.mp3` and `.ogg` too and
    /// fail at the last step, after minutes of separating.
    static let drumTrackEndings = ["flac", "wav"]

    /// "Eye of the Tiger (drums).flac", "(drums)" in the reader's language.
    static func drumTrackName(_ song: String) -> String {
        localized("%1$@ (drums)", ExportName.base(of: song)) + ".flac"
    }

    /// The MusicXML in a program the reader picks.
    static func openWith(_ model: AppModel) {
        guard let result = result(model), let app = Ask.reader.application() else { return }
        Ask.reader.open(URL(fileURLWithPath: result.musicxml), with: app)
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
