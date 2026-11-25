import AppKit
import SticklerCore
import SwiftUI

/// The Controls menu between View and Window (SPEC.md "Mac playback", scope 6; named as in
/// Apple's Music): Play or Pause (Space), Previous Bar (←), Next Bar (→), Go to the Start
/// (⌥←, as in QuickTime Player; Home too, as on Linux), then Song, Hits and Both with a
/// checkmark. Each item only tells the playback model; it decides.
@MainActor
enum ControlsMenu {
    struct Item: Identifiable {
        /// The item's text, a key of the String Catalog.
        let title: String
        let key: KeyEquivalent
        let modifiers: EventModifiers
        let act: @MainActor (PlaybackModel) -> Void

        var id: String { title }
    }

    /// The first item says what Space does now.
    static func playTitle(_ playback: PlaybackModel) -> String {
        playback.playing ? "Pause" : "Play"
    }

    static func items(_ playback: PlaybackModel) -> [Item] {
        [
            Item(title: playTitle(playback), key: .space, modifiers: []) { $0.toggle() },
            Item(title: "Previous Bar", key: .leftArrow, modifiers: []) { $0.previousBar() },
            Item(title: "Next Bar", key: .rightArrow, modifiers: []) { $0.nextBar() },
            Item(title: "Go to the Start", key: .leftArrow, modifiers: .option) {
                $0.goToStart()
            }
        ]
    }

    /// What to hear, in the menu's order, with each one's text.
    static let hearing: [(hear: Hear, title: String)] = [
        (.song, "Song"), (.hits, "Hits"), (.both, "Both")
    ]

    /// Only a shown result plays.
    static func enabled(_ model: AppModel) -> Bool {
        model.phase == .running && model.playback.canPlay
    }

    /// The Home key (key code 115) without modifiers goes to the start, as on Linux: a menu
    /// item has one key, and ⌥← is the Mac's.
    static let homeKey: UInt16 = 115

    /// Whether a key press is Home for the playback: Home alone, in the app's own window
    /// (not a panel's text field), while a result plays or can play.
    static func goesToStart(
        keyCode: UInt16, modifiers: NSEvent.ModifierFlags, inMainWindow: Bool, canPlay: Bool
    ) -> Bool {
        let held = modifiers.intersection([.command, .option, .control, .shift])
        return keyCode == homeKey && held.isEmpty && inMainWindow && canPlay
    }
}

/// The Controls menu, drawn from `ControlsMenu`.
struct ControlsItems: View {
    let model: AppModel

    var body: some View {
        let enabled = ControlsMenu.enabled(model)
        ForEach(ControlsMenu.items(model.playback)) { item in
            Button(LocalizedStringKey(item.title)) { item.act(model.playback) }
                .keyboardShortcut(item.key, modifiers: item.modifiers)
                .disabled(!enabled)
        }
        Divider()
        Picker(
            "What to Hear",
            selection: Binding(
                get: { model.playback.hear }, set: { model.playback.setHear($0) })
        ) {
            ForEach(ControlsMenu.hearing, id: \.hear) { choice in
                Text(LocalizedStringKey(choice.title)).tag(choice.hear)
            }
        }
        .pickerStyle(.inline)
        .labelsHidden()
        .disabled(!enabled)
    }
}
