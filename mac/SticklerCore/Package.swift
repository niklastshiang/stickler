// swift-tools-version: 6.0
// The Mac app's link to the Python core (SPEC.md, module `mac-shell`): Foundation only, so it
// builds and tests on Linux too.
import PackageDescription

let package = Package(
    name: "SticklerCore",
    platforms: [.macOS("26.0")],
    products: [.library(name: "SticklerCore", targets: ["SticklerCore"])],
    targets: [
        .target(name: "SticklerCore"),
        .testTarget(name: "SticklerCoreTests", dependencies: ["SticklerCore"])
    ]
)
