import Foundation

/// The coders for every line (`docs/bridge.md`: snake_case keys).
enum LineCoding {
    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return encoder
    }
}

/// One line from the core.
public enum Incoming: Equatable, Sendable {
    case hello(Hello)
    case event(seq: Int, Event)
    case reply(Reply)

    /// A line that is neither an event nor a reply: the core and the app disagree.
    public struct Unreadable: Error, Equatable {
        public let line: String

        init(_ line: Data) {
            self.line = String(bytes: line, encoding: .utf8) ?? "(not UTF-8)"
        }
    }

    public init(line: Data) throws {
        let decoder = LineCoding.decoder()
        let head: Head
        do {
            head = try decoder.decode(Head.self, from: line)
        } catch {
            throw Unreadable(line)
        }
        switch (head.event, head.ok) {
        case ("hello"?, _):
            self = .hello(try decoder.decode(Hello.self, from: line))
        case (let name?, _):
            let seq = head.seq ?? 0
            let event: Event
            switch name {
            case "state": event = .state(try decoder.decode(StateEvent.self, from: line).state)
            case "recent": event = .recent(try decoder.decode(RecentEvent.self, from: line).rows)
            case "notice": event = .notice(try decoder.decode(Notice.self, from: line))
            default: event = .unknown(name: name)
            }
            self = .event(seq: seq, event)
        case (nil, _?):
            self = .reply(try Reply(line: line))
        case (nil, nil):
            throw Unreadable(line)
        }
    }

    private struct Head: Decodable {
        let event: String?
        let seq: Int?
        let ok: Bool?
    }

    private struct StateEvent: Decodable { let state: AppState }

    private struct RecentEvent: Decodable { let rows: [RecentRow] }
}

/// The core's first line.
public struct Hello: Codable, Equatable, Sendable {
    public var `protocol`: Int
    public var version: String
    public var language: String
}

public enum Event: Equatable, Sendable {
    case state(AppState)
    case recent([RecentRow])
    case notice(Notice)
    /// An event this client does not know (a core from a newer release).
    case unknown(name: String)
}

/// A recent song (`recent`): `missing` rows can only be removed.
public struct RecentRow: Codable, Equatable, Sendable {
    public var path: String
    public var title: String
    public var detail: String
    public var missing: Bool
}

/// A short message (a toast in GTK, the bar at the bottom here); `opens` a file just saved.
public struct Notice: Codable, Equatable, Sendable {
    public var text: String
    public var opens: String?

    private enum CodingKeys: String, CodingKey { case text, opens }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(text, forKey: .text)
        try container.encode(opens, forKey: .opens)  // null, as the core sends it
    }
}

/// The answer to one command. Its fields beyond `id`, `ok` and `error` depend on the command:
/// read them with `payload(_:)`.
public struct Reply: Equatable, Sendable {
    /// `nil` when the core could not read the command's `id` (`bad_request`).
    public let id: Int?
    public let error: BridgeError?
    private let line: Data

    public var ok: Bool { error == nil }

    init(line: Data) throws {
        let head = try LineCoding.decoder().decode(Head.self, from: line)
        id = head.id
        error = head.ok ? nil : head.error ?? BridgeError(code: .internal, message: "")
        self.line = line
    }

    /// The reply's fields as `T` (`Pages`, `DrumTrackCost`, …).
    public func payload<T: Decodable>(_ type: T.Type) throws -> T {
        try LineCoding.decoder().decode(type, from: line)
    }

    private struct Head: Decodable {
        let id: Int?
        let ok: Bool
        let error: BridgeError?
    }
}

/// An error reply (`docs/bridge.md`, "Errors"); `message` is translated and can be shown.
public struct BridgeError: Codable, Equatable, Sendable, Error {
    public enum Code: Equatable, Sendable, Codable {
        case badRequest, unknownCommand, badArgument, notNow, `internal`
        case other(String)

        static let names: [(Code, String)] = [
            (.badRequest, "bad_request"), (.unknownCommand, "unknown_command"),
            (.badArgument, "bad_argument"), (.notNow, "not_now"), (.internal, "internal")
        ]

        public var name: String {
            if case .other(let name) = self { return name }
            return Self.names.first { $0.0 == self }.map(\.1) ?? ""
        }

        public init(from decoder: any Decoder) throws {
            let name = try decoder.singleValueContainer().decode(String.self)
            self = Self.names.first { $0.1 == name }?.0 ?? .other(name)
        }

        public func encode(to encoder: any Encoder) throws {
            var container = encoder.singleValueContainer()
            try container.encode(name)
        }
    }

    public var code: Code
    public var message: String
}
