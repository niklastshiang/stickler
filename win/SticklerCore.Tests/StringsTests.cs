namespace Stickler.Core.Tests;

[TestClass]
public sealed class StringsTests
{
    private static readonly string Tables = Path.Combine(Repo.Root, "win", "Stickler", "Strings");

    [TestMethod]
    public void TheReadersFirstLanguageWithATableIsChosen()
    {
        Assert.AreEqual("de", Strings.Load(Tables, ["de-DE", "en-US"]).Language);
        Assert.AreEqual("es", Strings.Load(Tables, ["fr-FR", "es-MX"]).Language);
        Assert.AreEqual("en", Strings.Load(Tables, ["en-GB", "de-DE"]).Language); // English first means English
        Assert.AreEqual("en", Strings.Load(Tables, ["fr"]).Language);
    }

    [TestMethod]
    public void TheWindowsAppsOwnTextsAreTranslatedFromPo()
    {
        var german = Strings.Load(Tables, ["de-DE"]);
        Assert.AreEqual("In Ordner anzeigen", german.Text("Show in Folder"));
        Assert.AreEqual("Beenden", german.Text("Exit"));
        Assert.AreEqual("Salir", Strings.Load(Tables, ["es"]).Text("Exit"));
        Assert.AreEqual("Exit", Strings.Load(Tables, ["en"]).Text("Exit"));
    }

    [TestMethod]
    public void PlaceholdersAreFilledByNameAndAnUnknownOneStays()
    {
        var english = Strings.English;
        Assert.AreEqual("Saved “a.pdf”", english.Text("Saved “{name}”", ("name", "a.pdf")));
        Assert.AreEqual("Download 2.2 GB", english.Text("Download {size:n}", ("size", "2.2 GB")));
        Assert.AreEqual("Saved “{name}”", english.Text("Saved “{name}”"));
        Assert.AreNotEqual("Saved “a.pdf”", Strings.Load(Tables, ["de"]).Text("Saved “{name}”", ("name", "a.pdf")));
        Assert.Contains("a.pdf", Strings.Load(Tables, ["de"]).Text("Saved “{name}”", ("name", "a.pdf")));
    }

    [TestMethod]
    public void ATextWithACountTakesItsFormInEveryLanguage()
    {
        var english = Strings.Load(Tables, ["en"]);
        Assert.AreEqual("1 page", english.Plural("{count} page", 1, ("count", "1")));
        Assert.AreEqual("3 pages", english.Plural("{count} page", 3, ("count", "3")));
        Assert.AreEqual("3 Seiten", Strings.Load(Tables, ["de"]).Plural("{count} page", 3, ("count", "3")));
        Assert.AreEqual("{count} thing", Strings.English.Plural("{count} thing", 2)); // nowhere: as given
    }

    [TestMethod]
    public void AFolderWithoutTablesGivesEnglish()
    {
        var empty = Strings.Load(Path.Combine(Path.GetTempPath(), $"no-strings-{Guid.NewGuid():N}"), ["de"]);
        Assert.AreEqual("en", empty.Language);
        Assert.AreEqual("Exit", empty.Text("Exit"));
    }
}

[TestClass]
public sealed class CoreLaunchTests
{
    [TestMethod]
    public void GettextGetsTheReadersLanguagesUpToEnglish()
    {
        Assert.AreEqual("de_DE:es:en", CoreLaunch.GettextLanguages(["de-DE", "es", "en-US", "fr"]));
        Assert.AreEqual("en", CoreLaunch.GettextLanguages(["en"]));
        Assert.AreEqual("en", CoreLaunch.GettextLanguages([]));
    }

    [TestMethod]
    public void TheCheckoutIsNamedOrFoundAboveTheApp()
    {
        var below = Path.Combine(Repo.Root, "win", "Stickler", "bin");
        Assert.AreEqual(Repo.Root, CoreLaunch.FindCheckout(new Dictionary<string, string?>(), below));
        var named = new Dictionary<string, string?> { [CoreLaunch.CheckoutVariable] = Repo.Root };
        Assert.AreEqual(Path.GetFullPath(Repo.Root), CoreLaunch.FindCheckout(named, Path.GetTempPath()));
        var wrong = new Dictionary<string, string?> { [CoreLaunch.CheckoutVariable] = Path.GetTempPath() };
        Assert.IsNull(CoreLaunch.FindCheckout(wrong, below)); // a wrong folder is not searched around
        Assert.IsNull(CoreLaunch.FindCheckout(new Dictionary<string, string?>(), Path.GetPathRoot(Path.GetTempPath())!));
    }

    [TestMethod]
    public void UvIsFoundOnThePathOrWhereItsInstallersPutIt()
    {
        var home = Path.Combine(Path.GetTempPath(), $"stickler-home-{Guid.NewGuid():N}");
        var winget = Path.Combine(home, "AppData", "Local", "Microsoft", "WinGet", "Links");
        var local = Path.Combine(home, ".local", "bin");
        Directory.CreateDirectory(winget);
        Directory.CreateDirectory(local);
        File.WriteAllText(Path.Combine(winget, "uv.exe"), "");
        File.WriteAllText(Path.Combine(local, "uv"), "");
        var windows = new Dictionary<string, string?>
        {
            ["PATH"] = "\"C:\\nowhere\";",
            ["LOCALAPPDATA"] = Path.Combine(home, "AppData", "Local"),
            ["USERPROFILE"] = home,
        };
        Assert.AreEqual(Path.Combine(winget, "uv.exe"), CoreLaunch.FindUv(windows, windows: true));
        Assert.AreEqual(Path.Combine(local, "uv"), CoreLaunch.FindUv(new Dictionary<string, string?> { ["HOME"] = home }, windows: false));
        var onPath = new Dictionary<string, string?> { ["PATH"] = Repo.Windows ? winget : local };
        Assert.AreEqual(Path.Combine(Repo.Windows ? winget : local, Repo.Windows ? "uv.exe" : "uv"), CoreLaunch.FindUv(onPath, Repo.Windows));
        Assert.IsNull(CoreLaunch.FindUv(new Dictionary<string, string?>(), windows: true));
        Directory.Delete(home, recursive: true);
    }

    [TestMethod]
    public void TheCheckoutsCoreRunsUvAsAnInstalledWindowsAppWithTheSystemsCertificates()
    {
        var core = CoreLaunch.Checkout(@"C:\stickler", @"C:\uv\uv.exe", ["de-DE"]);
        Assert.AreEqual(@"C:\uv\uv.exe", core.Executable);
        Assert.AreEqual(@"run --project C:\stickler python -m stickler_app.bridge", string.Join(" ", core.Arguments));
        Assert.AreEqual(@"C:\stickler", core.Directory);
        Assert.AreEqual("windows", core.Environment["STICKLER_PACKAGED"]);
        Assert.AreEqual("1", core.Environment["UV_SYSTEM_CERTS"]);
        Assert.AreEqual("de_DE:en", core.Environment["LANGUAGE"]);
        Assert.AreEqual(Path.Combine(@"C:\stickler", "adapters"), core.Environment["STICKLER_ADAPTER_SOURCES"]);
        CollectionAssert.Contains(core.Needs.ToList(), @"C:\uv\uv.exe");
    }

    [TestMethod]
    public void TheAppsCoreIsTheCheckoutOrOneThatSaysWhatIsMissing()
    {
        var found = CoreLaunch.ForApp(Repo.Environment, Repo.Root, Repo.Windows, ["en"]);
        Assert.AreEqual(Repo.Root, found.Directory);
        var lost = CoreLaunch.ForApp(new Dictionary<string, string?>(), Path.GetPathRoot(Path.GetTempPath())!, Repo.Windows, ["en"]);
        var recorder = new Recorder();
        recorder.Start(lost);
        Assert.IsTrue(recorder.Ended!.NeverStarted);
        Assert.HasCount(2, recorder.Ended.Details);
        Assert.Contains(CoreLaunch.CheckoutVariable, recorder.Ended.Details[0]);
    }
}
