// Task 150 (SPEC.md "Release 10 (proposed): keep and remove", open question 4): can a running
// Mac app move its own bundle to the Bin? Built into a bare .app by the mac workflow, started,
// and checked from outside: the bundle is gone from its folder and is in ~/.Trash.
import Foundation

let bundle = Bundle.main.bundleURL
do {
    var landed: NSURL?
    try FileManager.default.trashItem(at: bundle, resultingItemURL: &landed)
    print("trashed:", landed?.path ?? "?")
    exit(0)
} catch {
    print("refused:", error)
    exit(1)
}
