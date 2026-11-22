import Foundation
import SticklerCore

/// Stickler › "Back Up…" and "Restore Backup…" (SPEC.md "Release 10 (proposed): keep and
/// remove", scope A): where to save, which file, the question with what it holds; the core
/// writes and restores the zip, as in the GTK app.
@MainActor
enum Backups {
    /// The file name the save panel proposes, as the GTK app's (`backup.file_name`).
    static func name(on day: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .current
        let parts = calendar.dateComponents([.year, .month, .day], from: day)
        let year = parts.year ?? 0, month = parts.month ?? 0, date = parts.day ?? 0
        return String(format: "Stickler Backup %04d-%02d-%02d.zip", year, month, date)
    }

    static func backUp(_ model: AppModel, on day: Date = Date()) {
        guard let dest = Ask.reader.saveLocation(named: name(on: day), endings: ["zip"]) else {
            return
        }
        model.backUp(to: dest.path)
    }

    static func restore(_ model: AppModel) async {
        guard let src = Ask.reader.backup(),
            let summary = await model.backupSummary(of: src.path),
            Ask.reader.restore(summary.text)
        else { return }
        model.restore(from: src.path)
    }
}
