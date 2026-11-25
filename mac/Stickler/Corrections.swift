import SticklerCore
import SwiftUI

/// The corrections inspector's decisions (SPEC.md "Mac corrections", scopes 3 to 5): when it
/// can be on the window, what View › Show Corrections says and its key, and when the toolbar's
/// small spinner turns. What the controls show and every change's range are the core's.
@MainActor
enum CorrectionsMenu {
    /// Where open or closed is kept across launches (owner, 2026-11-25: as in Xcode and Pages).
    static let shownKey = "CorrectionsShown"
    /// ⌃⌘I, the key of Apple's `InspectorCommands`.
    static let key: KeyEquivalent = "i"
    static let modifiers: EventModifiers = [.control, .command]

    /// The shown result's controls; nil while there is nothing to correct: no result, an
    /// export's steps (the core would refuse), or a core from before `mac-corrections`.
    static func controls(_ model: AppModel) -> CorrectionControls? {
        guard model.phase == .running, case .result(let result) = model.state.screen else {
            return nil
        }
        return result.controls
    }

    static func enabled(_ model: AppModel) -> Bool {
        controls(model) != nil
    }

    /// The inspector is on the window when it was left open and there is something to
    /// correct; without a result it stays away but is remembered as open.
    static func presented(shown: Bool, _ model: AppModel) -> Bool {
        shown && enabled(model)
    }

    /// The menu item says what it does now, a key of the String Catalog.
    static func title(presented: Bool) -> String {
        presented ? "Hide Corrections" : "Show Corrections"
    }

    /// The core is writing a correction's notes: the old sheet stays, a spinner turns.
    static func correcting(_ model: AppModel) -> Bool {
        guard model.phase == .running, case .result(let result) = model.state.screen else {
            return false
        }
        return result.correcting
    }
}

/// View › Show Corrections / Hide Corrections (⌃⌘I), between the note size and Full Screen.
struct CorrectionsItem: View {
    let model: AppModel
    @AppStorage(CorrectionsMenu.shownKey) private var shown = false

    var body: some View {
        let presented = CorrectionsMenu.presented(shown: shown, model)
        Button(LocalizedStringKey(CorrectionsMenu.title(presented: presented))) {
            shown = !presented
        }
        .keyboardShortcut(CorrectionsMenu.key, modifiers: CorrectionsMenu.modifiers)
        .disabled(!CorrectionsMenu.enabled(model))
    }
}
