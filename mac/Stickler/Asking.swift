import AppKit
import SticklerCore

/// What the app asks the reader through AppKit's modal panels and alerts (task 117). The logic
/// around them (`Exports`, `Removal`, `Panels`) asks through `Ask.reader`: the app answers with
/// the real panels (`SystemAsking`), the tests with fixed answers, so that logic is tested.
@MainActor
protocol Asking {
    /// Where to save a file offered as `name`; nil when the reader cancels.
    func saveLocation(named name: String) -> URL?
    /// A song to open; nil when cancelled.
    func song() -> URL?
    /// The Stickler folder; nil when cancelled.
    func folder() -> URL?
    /// A program to open the MusicXML with; nil when cancelled.
    func application() -> URL?
    /// Whether to go on after reading the drum track's cost.
    func drumTrack(cost: String) -> Bool
    /// nil: keep everything; false: remove the models; true: remove everything else too.
    func removal(_ sizes: RemovalSizes) -> Bool?
    /// Opens `file` with `application`.
    func open(_ file: URL, with application: URL)
}

/// Who answers the app's questions: the reader through AppKit, or a test.
@MainActor
enum Ask {
    static var reader: any Asking = SystemAsking()
}

/// The real panels and alerts: AppKit only, every decision is made by the callers.
@MainActor
struct SystemAsking: Asking {
    func saveLocation(named name: String) -> URL? {
        let panel = NSSavePanel()
        panel.title = localized("Save As")
        panel.nameFieldStringValue = name
        panel.canCreateDirectories = true
        return panel.runModal() == .OK ? panel.url : nil
    }

    func song() -> URL? {
        let panel = NSOpenPanel()
        panel.title = String(localized: "Open a Song")
        panel.allowedContentTypes = [.audio]
        return panel.runModal() == .OK ? panel.url : nil
    }

    func folder() -> URL? {
        let panel = NSOpenPanel()
        panel.title = String(localized: "Choose Stickler Folder…")
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        return panel.runModal() == .OK ? panel.url : nil
    }

    func application() -> URL? {
        let panel = NSOpenPanel()
        panel.title = localized("Open With…")
        panel.directoryURL = URL(fileURLWithPath: "/Applications")
        panel.allowedContentTypes = [.application]
        return panel.runModal() == .OK ? panel.url : nil
    }

    func drumTrack(cost: String) -> Bool {
        let alert = NSAlert()
        alert.messageText = localized("Save the Drum Track?")
        alert.informativeText = cost
        alert.addButton(withTitle: localized("Choose Where to Save…"))
        alert.addButton(withTitle: localized("Cancel"))
        return alert.runModal() == .alertFirstButtonReturn
    }

    func removal(_ sizes: RemovalSizes) -> Bool? {
        let question = RemovalQuestion(sizes: sizes)
        return question.run() ? question.everything : nil
    }

    func open(_ file: URL, with application: URL) {
        NSWorkspace.shared.open(
            [file], withApplicationAt: application, configuration: NSWorkspace.OpenConfiguration())
    }
}

/// Stickler › "Remove Downloaded Models…": the question with the checkbox for everything else;
/// the body says what each choice frees.
@MainActor
final class RemovalQuestion: NSObject {
    let sizes: RemovalSizes
    let alert = NSAlert()
    let checkbox: NSButton

    init(sizes: RemovalSizes) {
        self.sizes = sizes
        checkbox = NSButton(
            checkboxWithTitle: localized("Also remove settings, recent songs and corrections"),
            target: nil, action: nil)
        super.init()
        alert.messageText = localized("Remove Downloaded Models?")
        alert.informativeText = sizes.modelsText
        alert.alertStyle = .warning
        alert.accessoryView = checkbox
        let remove = alert.addButton(withTitle: localized("Remove"))
        remove.hasDestructiveAction = true
        alert.addButton(withTitle: localized("Cancel"))
        checkbox.target = self
        checkbox.action = #selector(toggled)
    }

    var everything: Bool { checkbox.state == .on }

    /// The body for the choice as it stands.
    var body: String { everything ? sizes.everythingText : sizes.modelsText }

    @objc func toggled() {
        alert.informativeText = body
    }

    /// Whether the reader chose Remove.
    func run() -> Bool {
        alert.runModal() == .alertFirstButtonReturn
    }
}
