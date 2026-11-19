import Foundation
import Testing

@testable import SticklerCore

// Which core the app starts (SPEC.md, module `mac-package`, scope 3): the one in its bundle,
// or in a development build the checkout named by `STICKLER_CHECKOUT`. The bundles here are
// made up: folders with the parts' names, their Python a shell script.

/// A made-up app's `Contents/Resources` with a core whose Python is `script`.
func madeUpBundle(
    python script: String = "#!/bin/sh\n", without left: [String] = []
) throws -> URL {
    let resources = FileManager.default.temporaryDirectory
        .appendingPathComponent("stickler-bundle-\(UUID().uuidString)/Contents/Resources")
    let core = resources.appendingPathComponent("core")
    let files = FileManager.default
    for folder in ["python/bin", "bin", "python/share/stickler/adapters", "licenses/uv"] {
        try files.createDirectory(
            at: core.appendingPathComponent(folder), withIntermediateDirectories: true)
    }
    for program in ["python/bin/python3", "bin/uv", "bin/ffmpeg", "bin/ffprobe"] {
        let file = core.appendingPathComponent(program)
        try Data((program.hasSuffix("python3") ? script : "#!/bin/sh\n").utf8).write(to: file)
        try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: file.path)
    }
    try Data("Stickler ships these parts.\n".utf8)
        .write(to: core.appendingPathComponent("licenses/README.txt"))
    for part in left {
        try files.removeItem(at: core.appendingPathComponent(part))
    }
    return resources
}

@Suite struct TheAppsCore {
    let checkout = [CoreClient.checkoutVariable: "/Users/me/stickler"]

    @Test func theAppStartsTheCoreInItsOwnBundle() {
        let resources = URL(fileURLWithPath: "/Applications/Stickler.app/Contents/Resources")
        let client = CoreClient.app(
            languages: ["es-ES"], environment: [:], resources: resources, development: false)
        #expect(client.executable.path == resources.path + "/core/python/bin/python3")
        #expect(client.environment["PATH"]
            == resources.path + "/core/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        #expect(client.environment["LANGUAGE"] == "es_ES:en")
    }

    @Test func thePackagedCoreGetsNothingThatLeadsAwayFromSticklersFolders() {
        let resources = URL(fileURLWithPath: "/Applications/Stickler.app/Contents/Resources")
        let client = CoreClient.app(
            languages: ["en"], environment: [:], resources: resources, development: false)
        let own = [
            "HOME": "/Users/me", "PATH": "/opt/homebrew/bin:/usr/bin", "HTTPS_PROXY": "http://p",
            "UV_CACHE_DIR": "/elsewhere", "UV_PYTHON_INSTALL_DIR": "/elsewhere",
            "XDG_DATA_HOME": "/elsewhere", "STICKLER_ADAPTER_SOURCES": "/elsewhere",
            "STICKLER_PACKAGED": "appimage", "PYTHONPATH": "/elsewhere", "VIRTUAL_ENV": "/venv"
        ]
        let given = CoreClient.environment(
            own: own, dropping: client.drops, adding: client.environment)
        #expect(given["HOME"] == "/Users/me")
        #expect(given["HTTPS_PROXY"] == "http://p")  // a proxy is the reader's to set
        #expect(given["PATH"] == resources.path + "/core/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        #expect(given["STICKLER_PACKAGED"] == "macos")
        #expect(Set(given.keys) == ["HOME", "HTTPS_PROXY", "PATH", "STICKLER_PACKAGED", "LANGUAGE"])
    }

    @Test func aDevelopmentBuildsCoreKeepsTheEnvironmentItWasStartedWith() {
        let resources = URL(fileURLWithPath: "/Applications/Stickler.app/Contents/Resources")
        let client = CoreClient.app(
            languages: ["en"], environment: checkout, resources: resources, development: true)
        #expect(client.drops.isEmpty)
        let given = CoreClient.environment(
            own: ["UV_CACHE_DIR": "/mine"], dropping: client.drops, adding: client.environment)
        #expect(given["UV_CACHE_DIR"] == "/mine")
    }

    @Test func aDevelopmentBuildTakesTheCheckoutFromItsEnvironment() {
        #expect(CoreClient.checkoutVariable == "STICKLER_CHECKOUT")
        let resources = URL(fileURLWithPath: "/Stickler.app/Contents/Resources")
        let client = CoreClient.app(
            languages: ["en"], environment: checkout, resources: resources, development: true)
        #expect(client.arguments
            == ["uv", "run", "--project", "/Users/me/stickler", "stickler-bridge"])
        #expect(client.directory?.path == "/Users/me/stickler")
        // without the variable, or with an empty one, it is the bundle's core as for everyone
        for environment in [[:], [CoreClient.checkoutVariable: ""]] {
            let bundled = CoreClient.app(
                languages: ["en"], environment: environment, resources: resources,
                development: true)
            #expect(bundled.executable.path == resources.path + "/core/python/bin/python3")
        }
    }

    @Test func aReleasedAppIgnoresTheCheckout() {
        let resources = URL(fileURLWithPath: "/Stickler.app/Contents/Resources")
        let client = CoreClient.app(
            languages: ["en"], environment: checkout, resources: resources, development: false)
        #expect(client.executable.path == resources.path + "/core/python/bin/python3")
        #expect(client.arguments == ["-I", "-B", "-m", "stickler_app.bridge"])
    }

    @Test func theTestsAreADevelopmentBuild() {
        // `swift test` and Xcode's tests build for debugging; a release is built without it
        #expect(CoreClient.isDevelopmentBuild)
    }

    /// What the bundle's Python is started with, sent back as a notice: its arguments, the
    /// folder it runs in, and the environment the app gives it.
    static let echo = """
        #!/bin/sh
        text="$*|$(pwd)|$PATH|$STICKLER_PACKAGED|$LANGUAGE"
        printf '{"event": "notice", "seq": 1, "text": "%s", "opens": null}\\n' "$text"

        """

    @Test(.timeLimit(.minutes(1)))
    func theBundlesPythonGetsTheCommandLineAndEnvironment() async throws {
        let resources = try madeUpBundle(python: Self.echo)
        let core = resources.appendingPathComponent("core")
        let client = CoreClient.app(
            languages: ["de-DE"], environment: checkout, resources: resources, development: false)
        let seen = Recorder()
        seen.start(client)
        #expect(await eventually(10) { seen.ended != nil })
        guard case .event(1, .notice(let notice))? = seen.events.first else {
            Issue.record("no notice: \(seen.events) \(String(describing: seen.ended))")
            return
        }
        let got = notice.text.split(separator: "|", omittingEmptySubsequences: false)
            .map(String.init)
        #expect(got.count == 5)
        #expect(got.first == "-I -B -m stickler_app.bridge")
        #expect(got.dropFirst().first?.hasSuffix("/Contents/Resources/core") == true)
        // the bundle's helpers and the system's folders: nothing of Homebrew's or the reader's
        #expect(got.dropFirst(2).first == core.path + "/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        #expect(Array(got.dropFirst(3)) == ["macos", "de_DE:en"])
        #expect(seen.ended?.reason == .exited(0))
    }

    @Test func anAppWithoutItsCoreSaysWhatIsMissing() throws {
        let empty = FileManager.default.temporaryDirectory
            .appendingPathComponent("stickler-bare-\(UUID().uuidString)")
        let seen = Recorder()
        seen.start(
            CoreClient.app(
                languages: ["en"], environment: [:], resources: empty, development: false))
        let end = try #require(seen.ended)
        #expect(end.reason == .notStarted("parts of it are missing"))
        #expect(end.details.count == 5)
        #expect(end.technicalDetails.hasPrefix(
            "The core could not be started: parts of it are missing\n"
                + "missing: \(empty.path)/core/python/bin/python3\n"))
    }

    @Test func aBrokenBundleNamesTheBrokenPartOnly() throws {
        let resources = try madeUpBundle(without: ["bin/ffprobe"])
        let uv = resources.appendingPathComponent("core/bin/uv")
        try FileManager.default.setAttributes([.posixPermissions: 0o644], ofItemAtPath: uv.path)
        let seen = Recorder()
        seen.start(
            CoreClient.app(
                languages: ["en"], environment: [:], resources: resources, development: false))
        #expect(seen.ended?.details == [
            "cannot run: \(uv.path)",
            "missing: \(resources.path)/core/bin/ffprobe"
        ])
    }

    @Test func aCheckoutThatIsNotThereIsNamed() {
        let seen = Recorder()
        let gone = URL(fileURLWithPath: "/nonexistent/stickler")
        seen.start(CoreClient.checkout(gone, languages: []))
        #expect(seen.ended?.details == ["missing: /nonexistent/stickler/adapters"])
    }

    @Test func theShippedLicencesAreFoundInTheBundle() throws {
        let resources = try madeUpBundle()
        #expect(CoreClient.licences(resources: resources)?.path
            == resources.appendingPathComponent("core/licenses").path)
        // a build without its core (a development build) has none to show
        let bare = try madeUpBundle(without: ["licenses"])
        #expect(CoreClient.licences(resources: bare) == nil)
    }
}
