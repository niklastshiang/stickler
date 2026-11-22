import AppKit
import Foundation
import SticklerCore

/// Stickler › "Uninstall Stickler…" (SPEC.md "Release 10 (proposed): keep and remove", scope
/// B2): the sizes, the question with the box (off), then the core removes Stickler's folders
/// and replies once they are gone; the app clears what macOS keeps for it, moves its own bundle
/// to the Bin (a running app may: task 150) and quits. An app running from a translocated path
/// (started from the download without moving it) cannot move itself: its data goes all the
/// same, and it says to drag it to the Bin.
@MainActor
enum Uninstalling {
    /// The bundle to the Bin; replaced in tests, which must not remove their own host.
    static var trash: (URL) throws -> Void = { bundle in
        try FileManager.default.trashItem(at: bundle, resultingItemURL: nil)
    }
    static var quit: () -> Void = { NSApp.terminate(nil) }
    /// What macOS keeps for the app; replaced in tests, which must not clear their own host's.
    static var clearLeftovers: () -> Void = { Leftovers.remove() }
    static var bundle: URL = Bundle.main.bundleURL

    /// macOS runs a quarantined app it was not allowed to move from a random read-only path.
    static var translocated: Bool { bundle.path.contains("/AppTranslocation/") }

    static func ask(_ model: AppModel) async {
        guard let sizes = await model.uninstallSizes(),
            let everything = Ask.reader.uninstall(sizes),
            await model.uninstall(everything: everything)
        else { return }
        Removal.everything = true  // what macOS keeps for the app goes once more on quitting
        clearLeftovers()
        if translocated {
            Ask.reader.tell(localized(steps))
        } else {
            do {
                try trash(bundle)
            } catch {
                Ask.reader.tell(localized(steps))
            }
        }
        quit()
    }

    /// For an app that cannot move itself to the Bin.
    static let steps =
        "Stickler’s data is removed. To remove the app too, drag Stickler to the Bin."
}
