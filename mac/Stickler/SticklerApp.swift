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
                .frame(minWidth: 640, minHeight: 480)
        }
        .commands {
            SticklerCommands(model: delegate.model)
        }
    }
}

/// Starts the core at launch and ends it politely when the app quits.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel()

    func applicationDidFinishLaunching(_: Notification) {
        // the tests host the app: they build their own models, and no core is started
        if ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil {
            model.launch()
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
