import AppKit
import SticklerCore
import SwiftUI

/// The Mac app (SPEC.md, module `mac-shell`): one window over the core, which decides what
/// it shows (design screens M4 and M8).
@main
struct SticklerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        Window("Stickler", id: "main") {
            ContentView(model: delegate.model)
        }
        .commands {
            SticklerCommands(model: delegate.model)
        }
    }
}

/// Starts the core at launch and ends it politely when the app quits.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel(player: Player())
    private var homeKey: Any?

    func applicationDidFinishLaunching(_: Notification) {
        // the tests host the app: they build their own models, and no core is started
        if ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil {
            model.launch()
        }
        // Home goes to the start too (the Controls menu's key is ⌥←); a panel's text field
        // keeps its Home
        homeKey = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            let elsewhere =
                event.window is NSPanel || event.window?.isMainWindow != true
                || event.window?.firstResponder is NSText
            guard
                ControlsMenu.goesToStart(
                    keyCode: event.keyCode, modifiers: event.modifierFlags,
                    inMainWindow: !elsewhere, canPlay: ControlsMenu.enabled(model))
            else { return event }
            model.playback.goToStart()
            return nil
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        Task {
            await model.quit()
            if Removal.everything {
                Leftovers.remove()  // the reader removed everything: nothing is kept at quit
            }
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    func applicationShouldTerminateAfterLastWindowClosed(_: NSApplication) -> Bool {
        true
    }
}
