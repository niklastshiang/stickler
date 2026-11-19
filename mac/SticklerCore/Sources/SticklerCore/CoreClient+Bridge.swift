import Foundation

// The Mac app's own core (SPEC.md, module `mac-package`, scope 3): the one inside the app, or
// in a development build the checkout named by `STICKLER_CHECKOUT`, and the environment each
// gets.

extension CoreClient {
    /// The variable a development build reads the Stickler checkout from.
    public static let checkoutVariable = "STICKLER_CHECKOUT"

    /// Whether this build is one for development (built for debugging): only such a build
    /// reads `STICKLER_CHECKOUT`, a released app runs nothing but its own core.
    public static let isDevelopmentBuild: Bool = {
        #if DEBUG
        true
        #else
        false
        #endif
    }()

    /// The app's core: the one in its bundle, found through `resources` (`Bundle.main`: a
    /// quarantined app may run from a random read-only path); in a development build the
    /// checkout that `environment` names, if it names one. `languages` are the user's, best
    /// first.
    public static func app(
        languages: [String],
        environment: [String: String] = ProcessInfo.processInfo.environment,
        resources: URL = Bundle.main.resourceURL ?? Bundle.main.bundleURL,
        development: Bool = CoreClient.isDevelopmentBuild
    ) -> CoreClient {
        if development, let folder = environment[checkoutVariable], !folder.isEmpty {
            return checkout(URL(fileURLWithPath: folder), languages: languages)
        }
        return bundled(core: resources.appendingPathComponent("core"), languages: languages)
    }

    /// Variables that would lead a packaged core, `uv` or Python away from Stickler's own
    /// folders and Python: set in a Terminal the app was started from, or with `launchctl
    /// setenv`. Named by their beginnings.
    public static let leadingAway = ["UV_", "XDG_", "STICKLER_", "PYTHON", "VIRTUAL_ENV"]

    /// What the core is started with: this process's `own` environment without the variables
    /// that begin with one of `drops`, then `added`.
    public static func environment(
        own: [String: String], dropping drops: [String], adding added: [String: String]
    ) -> [String: String] {
        own.filter { name, _ in !drops.contains { name.hasPrefix($0) } }
            .merging(added) { $1 }
    }

    /// The core an app brings along: the Python inside `core` runs the bridge, isolated from
    /// the Mac's own Python settings (`-I`) and writing no bytecode into the app (`-B`: a
    /// changed bundle breaks its signature). Its `PATH` is the bundle's `bin` (`uv`, ffmpeg,
    /// ffprobe) and the system's folders, nothing of Homebrew's or the reader's. Where its
    /// adapters are and where `uv` keeps its Python, the core works out itself
    /// (`paths.packaged_env`), so it gets none of the app's own variables that would say
    /// otherwise (`leadingAway`). It is not started while one of its parts is missing.
    public static func bundled(core: URL, languages: [String]) -> CoreClient {
        let python = core.appendingPathComponent("python/bin/python3")
        let parts = ["bin/uv", "bin/ffmpeg", "bin/ffprobe", "python/share/stickler/adapters"]
        return CoreClient(
            executable: python,
            arguments: ["-I", "-B", "-m", "stickler_app.bridge"],
            directory: core,
            environment: [
                "STICKLER_PACKAGED": "macos",
                "LANGUAGE": gettextLanguages(languages),
                "PATH": core.appendingPathComponent("bin").path + ":/usr/bin:/bin:/usr/sbin:/sbin"
            ],
            needs: [python] + parts.map { core.appendingPathComponent($0) },
            drops: leadingAway)
    }

    /// A development build's core: `uv run stickler-bridge` in the checkout `folder`, as an
    /// installed app (`STICKLER_PACKAGED=macos`: its files under ~/Library, its models set up
    /// from the folder's adapters). `uv`, ffmpeg and ffprobe come from the `PATH` the build
    /// was started with; the app looks for none of them.
    public static func checkout(_ folder: URL, languages: [String]) -> CoreClient {
        let adapters = folder.appendingPathComponent("adapters")
        return CoreClient(
            executable: URL(fileURLWithPath: "/usr/bin/env"),
            arguments: ["uv", "run", "--project", folder.path, "stickler-bridge"],
            directory: folder,
            environment: [
                "STICKLER_PACKAGED": "macos",
                "STICKLER_ADAPTER_SOURCES": adapters.path,
                "LANGUAGE": gettextLanguages(languages)
            ],
            needs: [adapters])
    }

    /// The licences of what the app ships (`core/licenses`, an index and a folder per part),
    /// for the Help menu; nil in a build without its core.
    public static func licences(
        resources: URL = Bundle.main.resourceURL ?? Bundle.main.bundleURL
    ) -> URL? {
        let folder = resources.appendingPathComponent("core/licenses")
        let index = folder.appendingPathComponent("README.txt").path
        return FileManager.default.fileExists(atPath: index) ? folder : nil
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

    /// What of `needs` is not there: each must exist, and a file among them must be a program
    /// that can run (an image or an archive may have dropped its executable bit).
    public static func missing(_ needs: [URL]) -> [String] {
        needs.compactMap { need in
            var isFolder: ObjCBool = false
            guard FileManager.default.fileExists(atPath: need.path, isDirectory: &isFolder) else {
                return "missing: \(need.path)"
            }
            let runs = isFolder.boolValue || FileManager.default.isExecutableFile(atPath: need.path)
            return runs ? nil : "cannot run: \(need.path)"
        }
    }
}
