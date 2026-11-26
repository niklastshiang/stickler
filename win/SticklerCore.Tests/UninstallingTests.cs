namespace Stickler.Core.Tests;

/// <summary>Records what the app would do on Windows for "Uninstall Stickler…".</summary>
internal sealed class FakeUninstaller : IUninstaller
{
    public List<string> Done { get; } = [];

    public bool Starts { get; set; } = true;

    public bool StartUninstaller()
    {
        Done.Add("start uninstaller");
        return Starts;
    }

    public Task TellAsync(string text)
    {
        Done.Add($"tell {text}");
        return Task.CompletedTask;
    }

    public void EndApp() => Done.Add("exit");
}

/// <summary>SPEC.md, module <c>win-package</c>, scope 5.</summary>
[TestClass]
public sealed class UninstallingTests
{
    private const string Sizes =
        "\"ok\": true, \"keep\": 2213000000, \"everything\": 2213400000, "
        + "\"keep_text\": \"This removes Stickler and frees 2.2 GB. Your songs and exports stay.\", \"everything_text\": \"E\"";

    private readonly FakeCore core = new();
    private readonly FakeAsk ask = new();
    private readonly FakeUninstaller windows = new();
    private AppModel model = null!;
    private Uninstalling uninstalling = null!;

    [TestInitialize]
    public void Launch()
    {
        model = new AppModel(["en"], _ => core, work => work());
        model.Launch();
        uninstalling = new Uninstalling(model, ask, windows, Strings.English);
        core.Answer("uninstall_sizes", Sizes);
    }

    private IReadOnlyList<string> SentAfterStart => [.. core.Sent.Skip(1)];

    [TestMethod]
    public async Task TheCoreRemovesTheDataThenTheUninstallerRemovesTheProgramAndTheAppEnds()
    {
        ask.Box = false;
        await uninstalling.RunAsync();
        Assert.AreEqual(
            "confirm Uninstall Stickler? | This removes Stickler and frees 2.2 GB. Your songs and exports stay. | Uninstall | Also remove my settings, recent songs and corrections",
            ask.Asked.Single());
        CollectionAssert.AreEqual(
            new List<string> { Command.UninstallSizes.Line(0), Command.Uninstall(false).Line(0) },
            SentAfterStart.ToList());
        Assert.AreEqual(3.0, core.QuitWith); // the core is stopped before the uninstaller starts
        CollectionAssert.AreEqual(new List<string> { "start uninstaller", "exit" }, windows.Done);
    }

    [TestMethod]
    public async Task TheBoxRemovesEverything()
    {
        ask.Box = true;
        await uninstalling.RunAsync();
        Assert.AreEqual(Command.Uninstall(true).Line(0), SentAfterStart[^1]);
    }

    [TestMethod]
    public async Task CancelRemovesNothing()
    {
        ask.Box = null;
        await uninstalling.RunAsync();
        CollectionAssert.AreEqual(new List<string> { Command.UninstallSizes.Line(0) }, SentAfterStart.ToList());
        Assert.IsNull(core.QuitWith);
        Assert.IsEmpty(windows.Done);
    }

    [TestMethod]
    public async Task ARefusedUninstallLeavesTheProgramAndTheAppRunning()
    {
        core.Answer("uninstall", "\"ok\": false, \"error\": {\"code\": \"not_now\", \"message\": \"Not now.\"}");
        await uninstalling.RunAsync();
        Assert.IsNull(core.QuitWith);
        Assert.IsEmpty(windows.Done);
        core.Answer("uninstall_sizes", "not running");
        await uninstalling.RunAsync();
        Assert.HasCount(1, ask.Asked); // no question without the sizes
    }

    [TestMethod]
    public async Task AnUninstallerWindowsDoesNotStartIsNamedWithWhereToRemoveTheProgram()
    {
        windows.Starts = false;
        await uninstalling.RunAsync();
        CollectionAssert.AreEqual(
            new List<string>
            {
                "start uninstaller",
                "tell Stickler’s data is removed. Remove the program later in Settings › Apps.",
                "exit",
            },
            windows.Done);
    }

    [TestMethod]
    public void OnlyAnInstalledAppWithItsUninstallerOffersIt()
    {
        var app = Path.Combine(Path.GetTempPath(), $"stickler-app-{Guid.NewGuid():N}");
        Directory.CreateDirectory(Path.Combine(app, CoreLaunch.CoreFolder));
        Assert.IsFalse(Uninstalling.Offered(app));
        File.WriteAllBytes(Uninstalling.UninstallerPath(app), []);
        Assert.IsTrue(Uninstalling.Offered(app));
        Assert.AreEqual("unins000.exe", Path.GetFileName(Uninstalling.UninstallerPath(app)));
        Assert.IsFalse(Uninstalling.Offered(Repo.Root));
        Assert.AreEqual("/VERYSILENT /SUPPRESSMSGBOXES /NORESTART", string.Join(" ", Uninstalling.SilentSwitches));
        Directory.Delete(app, recursive: true);
    }
}
