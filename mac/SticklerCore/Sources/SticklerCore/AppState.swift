/// What the window shows (`docs/bridge.md`, "States"): one screen and the commands it allows.
/// Python decides it; Swift only draws it.
public struct AppState: Codable, Equatable, Sendable {
    public var screen: Screen
    public var can: Abilities

    public init(screen: Screen, can: Abilities) {
        self.screen = screen
        self.can = can
    }

    public static let empty = AppState(screen: .empty, can: Abilities(open: true))

    private enum Keys: String, CodingKey { case kind }

    public init(from decoder: any Decoder) throws {
        let kind = try decoder.container(keyedBy: Keys.self).decode(String.self, forKey: .kind)
        can = try Abilities(from: decoder)
        switch kind {
        case "empty": screen = .empty
        case "consent": screen = .consent(try Consent(from: decoder))
        case "setting_up": screen = .settingUp(try SettingUp(from: decoder))
        case "setup_failed": screen = .setupFailed(try SetupFailed(from: decoder))
        case "analysing": screen = .analysing(try Analysing(from: decoder))
        case "result": screen = .result(try SongResult(from: decoder))
        case "exporting": screen = .exporting(try Exporting(from: decoder))
        case "failed": screen = .failed(try Failure(from: decoder))
        default: screen = .unknown(kind: kind)  // a newer core: shown as nothing new
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: Keys.self)
        try container.encode(screen.kind, forKey: .kind)
        try can.encode(to: encoder)
        switch screen {
        case .empty, .unknown: break
        case .consent(let fields): try fields.encode(to: encoder)
        case .settingUp(let fields): try fields.encode(to: encoder)
        case .setupFailed(let fields): try fields.encode(to: encoder)
        case .analysing(let fields): try fields.encode(to: encoder)
        case .result(let fields): try fields.encode(to: encoder)
        case .exporting(let fields): try fields.encode(to: encoder)
        case .failed(let fields): try fields.encode(to: encoder)
        }
    }
}

public enum Screen: Equatable, Sendable {
    case empty
    case consent(Consent)
    case settingUp(SettingUp)
    case setupFailed(SetupFailed)
    case analysing(Analysing)
    case result(SongResult)
    case exporting(Exporting)
    case failed(Failure)
    /// A kind this client does not know (a core from a newer release).
    case unknown(kind: String)

    /// The `kind` as the core names it.
    public var kind: String {
        switch self {
        case .empty: "empty"
        case .consent: "consent"
        case .settingUp: "setting_up"
        case .setupFailed: "setup_failed"
        case .analysing: "analysing"
        case .result: "result"
        case .exporting: "exporting"
        case .failed: "failed"
        case .unknown(let kind): kind
        }
    }
}

/// The `can_*` fields: which buttons and menu items are enabled.
public struct Abilities: Codable, Equatable, Sendable {
    public var open = false
    public var cancel = false
    public var retry = false
    public var close = false
    public var export = false
    public var agree = false
    public var notNow = false
    public var retrySetup = false
    public var removeModels = false

    public init(
        open: Bool = false, cancel: Bool = false, retry: Bool = false, close: Bool = false,
        export: Bool = false, agree: Bool = false, notNow: Bool = false,
        retrySetup: Bool = false, removeModels: Bool = false
    ) {
        self.open = open
        self.cancel = cancel
        self.retry = retry
        self.close = close
        self.export = export
        self.agree = agree
        self.notNow = notNow
        self.retrySetup = retrySetup
        self.removeModels = removeModels
    }

    private enum CodingKeys: String, CodingKey {
        case open = "canOpen", cancel = "canCancel", retry = "canRetry", close = "canClose"
        case export = "canExport", agree = "canAgree", notNow = "canNotNow"
        case retrySetup = "canRetrySetup", removeModels = "canRemoveModels"
    }

    /// A field the core does not send means "not allowed": a button stays disabled rather
    /// than offer a command the core may refuse.
    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        func flag(_ key: CodingKeys) throws -> Bool {
            try container.decodeIfPresent(Bool.self, forKey: key) ?? false
        }
        self.init(
            open: try flag(.open), cancel: try flag(.cancel), retry: try flag(.retry),
            close: try flag(.close), export: try flag(.export), agree: try flag(.agree),
            notNow: try flag(.notNow), retrySetup: try flag(.retrySetup),
            removeModels: try flag(.removeModels))
    }
}

/// A row of the step list (setup, analysis, drum track).
public struct Step: Codable, Equatable, Sendable {
    public enum Progress: String, Codable, Sendable { case waiting, running, done }

    public var id: String
    public var label: String
    public var detail: String
    public var state: Progress
}

/// One missing model on the consent sheet (M1).
public struct Model: Codable, Equatable, Sendable {
    public var id: String
    public var name: String
    public var does: String
    public var licence: String
    public var size: String
}

public struct Consent: Codable, Equatable, Sendable {
    public var song: String?
    public var models: [Model]
    public var totalSize: String

    /// `song` is sent as `null` when no song waits, as the core does.
    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(song, forKey: .song)
        try container.encode(models, forKey: .models)
        try container.encode(totalSize, forKey: .totalSize)
    }
}

public struct SettingUp: Codable, Equatable, Sendable {
    public var song: String?
    public var steps: [Step]

    /// `song` is sent as `null` when no song waits, as the core does.
    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(song, forKey: .song)
        try container.encode(steps, forKey: .steps)
    }
}

public struct SetupFailed: Codable, Equatable, Sendable {
    public var song: String?
    public var steps: [Step]
    public var step: String
    public var server: String
    public var details: String

    /// `song` is sent as `null` when no song waits, as the core does.
    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(song, forKey: .song)
        try container.encode(steps, forKey: .steps)
        try container.encode(step, forKey: .step)
        try container.encode(server, forKey: .server)
        try container.encode(details, forKey: .details)
    }
}

public struct Analysing: Codable, Equatable, Sendable {
    public var song: String
    public var name: String
    public var steps: [Step]
}

/// The corrections' values (for `mac-corrections`; carried now, shown later).
public struct Corrections: Codable, Equatable, Sendable {
    public var tempo: String
    public var beatsPerBar: Int?
    public var firstDownbeat: Int?
    public var simplify: Bool
    public var repeats: Bool

    private enum CodingKeys: String, CodingKey {
        case tempo, beatsPerBar, firstDownbeat, simplify, repeats
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(tempo, forKey: .tempo)
        try container.encode(beatsPerBar, forKey: .beatsPerBar)  // null, as the core sends it
        try container.encode(firstDownbeat, forKey: .firstDownbeat)
        try container.encode(simplify, forKey: .simplify)
        try container.encode(repeats, forKey: .repeats)
    }
}

/// A finished analysis (`result`).
public struct SongResult: Codable, Equatable, Sendable {
    public var song: String
    public var title: String
    public var subtitle: String
    public var artist: String
    public var seconds: Double
    public var tempo: Int
    public var meter: [Int]
    public var musicxml: String
    public var corrections: Corrections
    public var correcting: Bool
    /// The detected hits as clicks, as long as the song; nil when there are none.
    public var clicks: String?
    /// The song's bars in played order (`docs/bridge.md`, `result`).
    public var bars: [SongBar] = []
}

extension SongResult {
    private enum Keys: String, CodingKey {
        case song, title, subtitle, artist, seconds, tempo, meter, musicxml, corrections
        case correcting, clicks, bars
    }

    /// `clicks` and `bars` came with `mac-playback`: an older line without them plays nothing.
    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: Keys.self)
        song = try container.decode(String.self, forKey: .song)
        title = try container.decode(String.self, forKey: .title)
        subtitle = try container.decode(String.self, forKey: .subtitle)
        artist = try container.decode(String.self, forKey: .artist)
        seconds = try container.decode(Double.self, forKey: .seconds)
        tempo = try container.decode(Int.self, forKey: .tempo)
        meter = try container.decode([Int].self, forKey: .meter)
        musicxml = try container.decode(String.self, forKey: .musicxml)
        corrections = try container.decode(Corrections.self, forKey: .corrections)
        correcting = try container.decode(Bool.self, forKey: .correcting)
        clicks = try container.decodeIfPresent(String.self, forKey: .clicks)
        bars = try container.decodeIfPresent([SongBar].self, forKey: .bars) ?? []
    }

    /// `clicks` is sent as `null` when there are none, as the core does.
    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: Keys.self)
        try container.encode(song, forKey: .song)
        try container.encode(title, forKey: .title)
        try container.encode(subtitle, forKey: .subtitle)
        try container.encode(artist, forKey: .artist)
        try container.encode(seconds, forKey: .seconds)
        try container.encode(tempo, forKey: .tempo)
        try container.encode(meter, forKey: .meter)
        try container.encode(musicxml, forKey: .musicxml)
        try container.encode(corrections, forKey: .corrections)
        try container.encode(correcting, forKey: .correcting)
        try container.encode(clicks, forKey: .clicks)
        try container.encode(bars, forKey: .bars)
    }
}

/// One bar of the song in played order: when it sounds, the written bar it is engraved as
/// (`BarBox.bar`), and what the controls say while it sounds ("Bar 3 of 110").
public struct SongBar: Codable, Equatable, Sendable {
    public var start: Double
    public var end: Double
    public var bar: Int
    public var label: String

    public init(start: Double, end: Double, bar: Int, label: String) {
        self.start = start
        self.end = end
        self.bar = bar
        self.label = label
    }
}

public struct Exporting: Codable, Equatable, Sendable {
    public var song: String
    public var title: String
    public var subtitle: String
    public var dest: String
    public var steps: [Step]
}

/// Something went wrong with a song (`failed`).
public struct Failure: Codable, Equatable, Sendable {
    public enum Reason: String, Codable, Sendable { case unreadable, analysis, export }

    public var song: String
    public var name: String
    public var reason: Reason
    public var title: String
    public var description: String
    public var details: String
}
