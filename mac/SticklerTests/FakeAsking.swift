import Foundation
import SticklerCore

@testable import Stickler

/// The reader's answers, fixed by each test; what was asked is kept.
@MainActor
final class FakeAsking: Asking {
    var save: URL?
    var chosenSong: URL?
    var program: URL?
    var goOn = true
    var remove: Bool?
    private(set) var offered: [String] = []
    private(set) var costs: [String] = []
    private(set) var sizes: [RemovalSizes] = []
    private(set) var opened: [(URL, URL)] = []

    private(set) var endings: [[String]] = []

    func saveLocation(named name: String, endings: [String]) -> URL? {
        offered.append(name)
        self.endings.append(endings)
        return save
    }

    func song() -> URL? { chosenSong }

    func application() -> URL? { program }

    func drumTrack(cost: String) -> Bool {
        costs.append(cost)
        return goOn
    }

    func removal(_ sizes: RemovalSizes) -> Bool? {
        self.sizes.append(sizes)
        return remove
    }

    var chosenBackup: URL?
    var restoreIt = true
    private(set) var questions: [String] = []

    func backup() -> URL? { chosenBackup }

    func restore(_ text: String) -> Bool {
        questions.append(text)
        return restoreIt
    }

    func open(_ file: URL, with application: URL) {
        opened.append((file, application))
    }
}
