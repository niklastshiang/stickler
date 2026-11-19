/// A trackpad pinch on the sheet (SPEC.md, module `mac-sheet`, scope 3): it gathers the
/// gesture's steps and gives one scale when the fingers lift, so the core engraves once, not
/// for every step.
public struct Pinch {
    private var scale: Double?

    public init() {}

    /// The fingers touched.
    public mutating func begin() {
        scale = 1
    }

    /// A step of the gesture: `magnification` is what AppKit adds to the scale (0.1 is 10 %
    /// larger). Ignored outside a gesture.
    public mutating func change(by magnification: Double) {
        if let now = scale {
            scale = now * (1 + magnification)
        }
    }

    /// The fingers lifted: the whole gesture's scale, or nothing when it changed nothing.
    public mutating func end() -> Double? {
        defer { scale = nil }
        guard let scale, scale > 0, scale != 1 else { return nil }
        return scale
    }

    /// The system took the gesture away: nothing changes.
    public mutating func cancel() {
        scale = nil
    }
}
