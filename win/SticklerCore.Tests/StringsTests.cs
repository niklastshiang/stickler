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
    public void ModelsSetUpElsewhereAreNotOverwrittenWithTheCheckoutsAdapters()
    {
        var environment = System.Environment.GetEnvironmentVariables()
            .Cast<System.Collections.DictionaryEntry>()
            .ToDictionary(e => (string)e.Key, e => (string?)e.Value, StringComparer.OrdinalIgnoreCase);
        environment[CoreLaunch.CheckoutVariable] = Repo.Root;
        environment.Remove("STICKLER_ADAPTERS");
        var windows = OperatingSystem.IsWindows();
        using var shipping = CoreLaunch.ForApp(environment, Repo.Root, windows, ["en"], development: true);
        Assert.AreEqual(Path.Combine(Path.GetFullPath(Repo.Root), "adapters"), shipping.Environment["STICKLER_ADAPTER_SOURCES"]);
        environment["STICKLER_ADAPTERS"] = Path.Combine(Path.GetTempPath(), "stand-ins");
        using var standIns = CoreLaunch.ForApp(environment, Repo.Root, windows, ["en"], development: true);
        Assert.IsFalse(standIns.Environment.ContainsKey("STICKLER_ADAPTER_SOURCES"));
        Assert.AreEqual("windows", standIns.Environment["STICKLER_PACKAGED"]);
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
        var found = CoreLaunch.ForApp(Repo.Environment, Repo.Root, Repo.Windows, ["en"], development: true);
        Assert.AreEqual(Repo.Root, found.Directory);
        var lost = CoreLaunch.ForApp(new Dictionary<string, string?>(), Path.GetPathRoot(Path.GetTempPath())!, Repo.Windows, ["en"], development: true);
        var recorder = new Recorder();
        recorder.Start(lost);
        Assert.IsTrue(recorder.Ended!.NeverStarted);
        Assert.HasCount(2, recorder.Ended.Details);
        Assert.Contains(CoreLaunch.CheckoutVariable, recorder.Ended.Details[0]);
    }

    /// <summary>The parts of the installer's layout the core needs (SPEC.md, module
    /// <c>win-package</c>, scope 1), as paths below the app's folder.</summary>
    private static readonly string[][] Parts =
    [
        ["core", "python", "python.exe"],
        ["core", "bin", "uv.exe"],
        ["core", "bin", "ffmpeg.exe"],
        ["core", "bin", "ffprobe.exe"],
        ["core", "python", "share", "stickler", "adapters"],
    ];

    /// <summary>A made-up install folder without the part <paramref name="leaveOut"/> (an index
    /// into <see cref="Parts"/>, or -1 for none).</summary>
    private static string Installed(int leaveOut = -1)
    {
        var app = Path.Combine(Path.GetTempPath(), $"stickler-app-{Guid.NewGuid():N}");
        Directory.CreateDirectory(Path.Combine(app, CoreLaunch.CoreFolder));
        for (var i = 0; i < Parts.Length; i++)
        {
            if (i == leaveOut)
            {
                continue;
            }
            var path = Path.Combine([app, .. Parts[i]]);
            if (Parts[i][^1].EndsWith(".exe", StringComparison.Ordinal))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllBytes(path, []);
            }
            else
            {
                Directory.CreateDirectory(path);
            }
        }
        return app;
    }

    [TestMethod]
    public void TheInstalledCoreRunsItsOwnPythonWithItsOwnProgramsFirst()
    {
        var app = Installed();
        var environment = new Dictionary<string, string?> { ["SystemRoot"] = "W", ["PATH"] = "elsewhere" };
        var core = CoreLaunch.Installed(app, environment, ["de-DE", "en-GB"]);
        var folder = Path.Combine(app, "core");
        Assert.AreEqual(Path.Combine(folder, "python", "python.exe"), core.Executable);
        Assert.AreEqual("-m stickler_app.bridge", string.Join(" ", core.Arguments));
        Assert.AreEqual(folder, core.Directory);
        Assert.AreEqual("windows", core.Environment["STICKLER_PACKAGED"]);
        Assert.AreEqual("de_DE:en", core.Environment["LANGUAGE"]);
        Assert.AreEqual("1", core.Environment["UV_SYSTEM_CERTS"]);
        Assert.AreEqual("1", core.Environment["PYTHONUTF8"]);
        // Stickler's own uv and ffmpeg first, then only Windows' folders: never the user's
        var path = core.Environment["PATH"].Split(';');
        Assert.AreEqual(Path.Combine(folder, "bin"), path[0]);
        Assert.AreEqual(string.Join(";", Path.Combine("W", "System32"), "W", Path.Combine("W", "System32", "Wbem")), string.Join(";", path[1..]));
        Assert.AreEqual("PYTHON VIRTUAL_ENV CONDA UV_", string.Join(" ", core.Drops));
        Assert.HasCount(0, CoreClient.Missing(core.Needs));
        Assert.IsFalse(core.Environment.ContainsKey("STICKLER_ADAPTER_SOURCES")); // the core finds them
        Assert.StartsWith(@"C:\Windows", CoreLaunch.Installed(app, new Dictionary<string, string?>(), ["en"]).Environment["PATH"].Split(';')[2]);
        Directory.Delete(app, recursive: true);
    }

    [TestMethod]
    public void EachMissingPartOfTheInstalledCoreIsNamed()
    {
        for (var i = 0; i < Parts.Length; i++)
        {
            var app = Installed(leaveOut: i);
            var recorder = new Recorder();
            recorder.Start(CoreLaunch.Installed(app, new Dictionary<string, string?>(), ["en"]));
            Assert.IsTrue(recorder.Ended!.NeverStarted);
            Assert.HasCount(1, recorder.Ended.Details);
            Assert.EndsWith(Path.Combine(Parts[i]), recorder.Ended.Details[0]);
            Directory.Delete(app, recursive: true);
        }
    }

    [TestMethod]
    public void TheAppTakesItsInstalledCoreBeforeAnyCheckout()
    {
        var app = Installed();
        var named = new Dictionary<string, string?> { [CoreLaunch.CheckoutVariable] = Repo.Root };
        foreach (var development in new[] { true, false })
        {
            var core = CoreLaunch.ForApp(named, app, windows: true, ["en"], development);
            Assert.AreEqual(Path.Combine(app, "core"), core.Directory);
        }
        Directory.Delete(app, recursive: true);
    }

    [TestMethod]
    public void TheInstallersBuildWithoutItsCoreNeverLooksForACheckout()
    {
        var empty = Path.Combine(Path.GetTempPath(), $"stickler-app-{Guid.NewGuid():N}");
        Directory.CreateDirectory(empty);
        var named = new Dictionary<string, string?> { [CoreLaunch.CheckoutVariable] = Repo.Root };
        var recorder = new Recorder();
        recorder.Start(CoreLaunch.ForApp(named, empty, windows: true, ["en"], development: false));
        Assert.IsTrue(recorder.Ended!.NeverStarted);
        Assert.Contains("install Stickler again", recorder.Ended.Details[0]);
        Directory.Delete(empty);
    }
}
