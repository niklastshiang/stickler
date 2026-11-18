import Foundation

/// Cuts a byte stream into lines at "\n". A read may end in the middle of a line (a long
/// `pages` reply arrives in many reads), so the rest waits for the next chunk.
struct LineSplitter {
    private var pending = Data()

    /// The complete lines in `chunk` and what was pending, without their "\n"; empty lines
    /// are skipped.
    mutating func feed(_ chunk: Data) -> [Data] {
        pending.append(chunk)
        var lines: [Data] = []
        while let end = pending.firstIndex(of: UInt8(ascii: "\n")) {
            let line = pending[pending.startIndex..<end]
            if !line.isEmpty {
                lines.append(Data(line))
            }
            pending.removeSubrange(pending.startIndex...end)
        }
        return lines
    }

    /// What is left when the stream ends: a last line without "\n", if any.
    mutating func finish() -> Data? {
        defer { pending = Data() }
        return pending.isEmpty ? nil : pending
    }
}

/// The last lines of a stream (the core's stderr), for "Technical Details".
struct Tail {
    let limit: Int
    private(set) var lines: [String] = []
    private var splitter = LineSplitter()

    init(limit: Int) {
        self.limit = limit
    }

    mutating func feed(_ chunk: Data) {
        for line in splitter.feed(chunk) {
            keep(line)
        }
    }

    mutating func finish() {
        if let line = splitter.finish() {
            keep(line)
        }
    }

    private mutating func keep(_ line: Data) {
        append(String(bytes: line, encoding: .utf8) ?? "(not UTF-8)")
    }

    private mutating func append(_ line: String) {
        lines.append(line)
        if lines.count > limit {
            lines.removeFirst(lines.count - limit)
        }
    }
}
