import Foundation

/// A command to the core (`docs/bridge.md`, "Commands"). Each gets exactly one reply.
public enum Command: Equatable, Sendable {
    case start
    case agree
    case notNow
    case retrySetup
    case open(path: String)
    case cancel
    case retry
    case close
    case pages(width: Double, zoom: Double?)
    case a4Pages
    case exportMusicXML(dest: String)
    case drumTrackCost
    case exportDrumTrack(dest: String)
    case forgetRecent(path: String)
    case settings
    case setZoom(Double)
    case zoomIn
    case zoomOut
    case actualSize
    case removalSizes
    case removeModels(everything: Bool)
    case backUp(dest: String)
    case backupSummary(src: String)
    case restore(src: String)
    case uninstallSizes
    case uninstall(everything: Bool)
    case jump(bar: Int, from: Double)
    case step(from: Double, count: Int)
    case volumes(hear: Hear, song: Double?, hits: Double?)
    case playable
    case correct(Correction)
    case quit

    /// The command's name on the wire.
    public var name: String {
        switch self {
        case .start: "start"
        case .agree: "agree"
        case .notNow: "not_now"
        case .retrySetup: "retry_setup"
        case .open: "open"
        case .cancel: "cancel"
        case .retry: "retry"
        case .close: "close"
        case .pages: "pages"
        case .a4Pages: "a4_pages"
        case .exportMusicXML: "export_musicxml"
        case .drumTrackCost: "drum_track_cost"
        case .exportDrumTrack: "export_drum_track"
        case .forgetRecent: "forget_recent"
        case .settings: "settings"
        case .setZoom: "set_zoom"
        case .zoomIn: "zoom_in"
        case .zoomOut: "zoom_out"
        case .actualSize: "actual_size"
        case .removalSizes: "removal_sizes"
        case .removeModels: "remove_models"
        case .backUp: "back_up"
        case .backupSummary: "backup_summary"
        case .restore: "restore"
        case .uninstallSizes: "uninstall_sizes"
        case .uninstall: "uninstall"
        case .jump: "jump"
        case .step: "step"
        case .volumes: "volumes"
        case .playable: "playable"
        case .correct: "correct"
        case .quit: "quit"
        }
    }

    /// The command as one line (no newline) with its `id`.
    public func line(id: Int) throws -> Data {
        try LineCoding.encoder().encode(CommandWire(id: id, command: self))
    }
}

/// One change from the corrections inspector (`correct`): a value, a stepper's step (counted
/// by the core from its newest values, so quick clicks are never lost), or Back to Detected.
public enum Correction: Equatable, Sendable {
    case tempo(Tempo)
    case beatsPerBar(Int)
    case beatsPerBarBy(Int)
    case firstOne(Int)
    case firstOneBy(Int)
    case simplify(Bool)
    case repeats(Bool)
    case detected
}

/// A command with its `id`, as the core reads it.
private struct CommandWire: Encodable {
    let id: Int
    let command: Command

    private enum Keys: String, CodingKey {
        case id, cmd, path, dest, src, width, zoom, everything, bar, hear, song, hits
        case from = "at", count = "by"  // the protocol's names
        case tempo, simplify, repeats, detected
        case beatsPerBar = "beats_per_bar", beatsPerBarBy = "beats_per_bar_by"
        case firstOne = "first_one", firstOneBy = "first_one_by"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: Keys.self)
        try container.encode(id, forKey: .id)
        try container.encode(command.name, forKey: .cmd)
        switch command {
        case .open(let path), .forgetRecent(let path):
            try container.encode(path, forKey: .path)
        case .exportMusicXML(let dest), .exportDrumTrack(let dest), .backUp(let dest):
            try container.encode(dest, forKey: .dest)
        case .pages(let width, let zoom):
            try container.encode(width, forKey: .width)
            try container.encodeIfPresent(zoom, forKey: .zoom)  // the stored size without
        case .setZoom(let zoom):
            try container.encode(zoom, forKey: .zoom)
        case .removeModels(let everything), .uninstall(let everything):
            try container.encode(everything, forKey: .everything)
        case .backupSummary(let src), .restore(let src):
            try container.encode(src, forKey: .src)
        case .jump(let bar, let from):
            try container.encode(bar, forKey: .bar)
            try container.encode(from, forKey: .from)
        case .step(let from, let count):
            try container.encode(from, forKey: .from)
            try container.encode(count, forKey: .count)
        case .volumes(let hear, let song, let hits):
            try container.encode(hear, forKey: .hear)
            try container.encodeIfPresent(song, forKey: .song)  // the stored volume without
            try container.encodeIfPresent(hits, forKey: .hits)
        case .correct(let change):
            try encode(change, into: &container)
        default:
            break
        }
    }

    private func encode(_ change: Correction, into container: inout KeyedEncodingContainer<Keys>)
        throws
    {
        switch change {
        case .tempo(let tempo): try container.encode(tempo, forKey: .tempo)
        case .beatsPerBar(let beats): try container.encode(beats, forKey: .beatsPerBar)
        case .beatsPerBarBy(let step): try container.encode(step, forKey: .beatsPerBarBy)
        case .firstOne(let beat): try container.encode(beat, forKey: .firstOne)
        case .firstOneBy(let step): try container.encode(step, forKey: .firstOneBy)
        case .simplify(let on): try container.encode(on, forKey: .simplify)
        case .repeats(let on): try container.encode(on, forKey: .repeats)
        case .detected: try container.encode(true, forKey: .detected)
        }
    }
}
