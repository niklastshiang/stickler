import Foundation
import Observation

/// The sheet music's model (SPEC.md, module `mac-sheet`, scope 1): which pages to ask the core
/// for and when, and which reply wins. The view only draws `pages` and reports its width; the
/// note size is the core's setting.
@MainActor @Observable
public final class SheetModel {
    /// The shown result's pages at the sheet's width; the old ones stay while new ones come.
    public private(set) var pages: [Page] = []
    /// The note size, 1 is 100 %.
    public private(set) var zoom = 1.0
    /// The note size as the menu shows it.
    public private(set) var percent = "100%"
    /// Whether a result is shown, so the zoom items are enabled. Not while its drum track is
    /// saved: the steps are shown then, and the core engraves nothing.
    public var canZoom: Bool { music != nil && onScreen }

    /// What decides the pages of a result: a correction's new notation changes it (`sheet`),
    /// its start does not (the notes are still the old ones then), nor does an export.
    private struct Music: Equatable {
        let song: String
        let musicxml: String
        let sheet: Int
    }

    private let settle: Duration
    private let refused: @MainActor (any Error) -> Void
    private var core: (any Core)?
    private var music: Music?
    private var onScreen = false  // the result is shown, not an export's steps
    private var owed = false  // pages wanted while they could not be asked for
    private var width: Double?
    private var settling: Task<Void, Never>?
    private var request = 0  // the newest request's number; older replies are dropped

    /// `settle`: how long a width must hold before it counts (the GTK app's pause after a
    /// resize). `refused` tells the reader why a command was refused.
    init(settle: Duration, refused: @escaping @MainActor (any Error) -> Void) {
        self.settle = settle
        self.refused = refused
    }

    /// A new core (or none): the sheet starts empty and asks for the stored note size.
    func attach(_ next: (any Core)?) {
        core = next
        music = nil
        onScreen = false
        owed = false
        pages = []
        request += 1
        settling?.cancel()
        guard let next else { return }
        Task {
            do {
                let settings = try await next.send(.settings).payload(Settings.self)
                guard next === core else { return }  // a core replaced meanwhile
                zoom = settings.zoom
                percent = settings.percent
            } catch {
                refused(error)
            }
        }
    }

    /// The core's new state: a new result asks for its pages, an export keeps them, any other
    /// screen empties the sheet.
    func show(_ screen: Screen) {
        switch screen {
        case .result(let result):
            let next = Music(
                song: result.song, musicxml: result.musicxml, sheet: result.sheet)
            onScreen = true
            guard next != music || owed else { return }
            music = next
            askForPages()
        case .exporting:
            onScreen = false
        default:
            music = nil
            onScreen = false
            owed = false
            pages = []
            request += 1
        }
    }

    /// The sheet's width in points: the first one counts at once, later ones once they held
    /// for `settle`.
    public func resize(to next: Double) {
        settling?.cancel()
        guard let width else {
            width = next
            askForPages()
            return
        }
        guard next != width else { return }
        settling = Task {
            try? await Task.sleep(for: settle)
            guard !Task.isCancelled else { return }
            self.width = next
            askForPages()
        }
    }

    /// View › Zoom In.
    public func zoomIn() { change(.zoomIn) }
    /// View › Zoom Out.
    public func zoomOut() { change(.zoomOut) }
    /// View › Actual Size.
    public func actualSize() { change(.actualSize) }
    /// A note size of the reader's choice; the core keeps it within its limits.
    public func setZoom(_ size: Double) { change(.setZoom(size)) }
    /// A pinch, once the fingers rest: the shown note size times the gesture's scale.
    public func pinched(by scale: Double) { setZoom(zoom * scale) }

    private func change(_ command: Command) {
        guard let core else { return }
        Task {
            do {
                let next = try await core.send(command).payload(Zoom.self)
                guard core === self.core else { return }  // a core replaced meanwhile
                zoom = next.zoom
                percent = next.percent
                askForPages()
            } catch {
                refused(error)
            }
        }
    }

    private func askForPages() {
        guard let core, music != nil, let width else { return }
        guard onScreen else {
            owed = true  // asked for when the result is back
            return
        }
        owed = false
        request += 1
        let mine = request
        Task {
            do {
                let next = try await core.send(.pages(width: width, zoom: nil))
                    .payload(Pages.self)
                guard mine == request else { return }
                pages = next.pages
                zoom = next.zoom
            } catch {
                guard mine == request else { return }
                refused(error)
            }
        }
    }
}
