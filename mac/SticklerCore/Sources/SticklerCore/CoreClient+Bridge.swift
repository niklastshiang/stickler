import Foundation

// The Mac app's own core: how `CoreClient` is started for a Stickler folder, and the
// environment it gets (SPEC.md, module `mac-shell`, "Where the core is").

extension CoreClient {
    /// The core of the Mac app: `uv run stickler-bridge` in the Stickler folder, as an
    /// installed app (`STICKLER_PACKAGED=macos`: its files under ~/Library, its models set up
    /// from the folder's adapters). `languages` are the user's, best first; `path` is this
    /// process's `PATH`, which the core's starts from (`toolPath`).
    public static func bridge(
        in folder: URL, uv tool: URL, languages: [String],
        path: String = ProcessInfo.processInfo.environment["PATH"] ?? ""
    ) -> CoreClient {
        CoreClient(
            executable: tool, arguments: ["run", "--project", folder.path, "stickler-bridge"],
            directory: folder,
            environment: [
                "STICKLER_PACKAGED": "macos",
                "STICKLER_ADAPTER_SOURCES": folder.appendingPathComponent("adapters").path,
                "LANGUAGE": gettextLanguages(languages),
                "PATH": toolPath(uv: tool, inherited: path)
            ])
    }

    /// The core an app brings along (SPEC.md, module `mac-package`, scope 3): the Python inside
    /// `core` runs the bridge, isolated from the Mac's own Python settings (`-I`) and writing
    /// no bytecode into the app (`-B`: a changed bundle breaks its signature). Its `PATH` is
    /// the bundle's `bin` (`uv`, ffmpeg, ffprobe) and the system's folders, nothing of
    /// Homebrew's or the reader's. Where its adapters are and where `uv` keeps its Python,
    /// the core works out itself (`paths.packaged_env`).
    public static func bundled(core: URL, languages: [String]) -> CoreClient {
        CoreClient(
            executable: core.appendingPathComponent("python/bin/python3"),
            arguments: ["-I", "-B", "-m", "stickler_app.bridge"],
            directory: core,
            environment: [
                "STICKLER_PACKAGED": "macos",
                "LANGUAGE": gettextLanguages(languages),
                "PATH": core.appendingPathComponent("bin").path + ":/usr/bin:/bin:/usr/sbin:/sbin"
            ])
    }

    /// The core inside the app's resources, when the app brings one (its Python is there and
    /// can run).
    public static func bundledCore(resources: URL? = Bundle.main.resourceURL) -> URL? {
        guard let core = resources?.appendingPathComponent("core") else { return nil }
        let python = core.appendingPathComponent("python/bin/python3").path
        return FileManager.default.isExecutableFile(atPath: python) ? core : nil
    }

    /// `LANGUAGE` as gettext reads it, from the user's languages (BCP 47, best first):
    /// `de-DE` becomes `de_DE`, and the list ends with `en` at the first English entry.
    /// English is the source's language and has no catalogue, so gettext would go on to a
    /// later language; without any entry it would follow `LANG`.
    public static func gettextLanguages(_ languages: [String]) -> String {
        let translated = languages.prefix { $0 != "en" && !$0.hasPrefix("en-") }
        return (translated.map { $0.replacingOccurrences(of: "-", with: "_") } + ["en"])
            .joined(separator: ":")
    }

    /// The core's `PATH`: the folder of the `uv` that was found (the core calls `uv` itself
    /// for the models), Homebrew's two prefixes (ffmpeg and ffprobe), then `inherited`, each
    /// folder once. An app started from the Finder inherits only the system's folders.
    public static func toolPath(uv tool: URL, inherited: String) -> String {
        let folders =
            [tool.deletingLastPathComponent().path, "/opt/homebrew/bin", "/usr/local/bin"]
            + inherited.split(separator: ":").map(String.init)
        var seen = Set<String>()
        return folders.filter { seen.insert($0).inserted }.joined(separator: ":")
    }
}
