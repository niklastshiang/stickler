namespace Stickler.Core.Tests;

/// <summary>Answers the questions as told and records what was asked.</summary>
internal sealed class FakeAsk : IAsk
{
    public List<string> Asked { get; } = [];

    public string? Save { get; set; } = @"C:\Out\file";

    public string? Open { get; set; } = @"C:\In\song.flac";

    public bool Yes { get; set; } = true;

    public bool? Box { get; set; } = false;

    public Task<string?> SaveFileAsync(string name, IReadOnlyList<string> endings)
    {
        Asked.Add($"save {name} [{string.Join(",", endings)}]");
        return Task.FromResult(Save);
    }

    public Task<string?> OpenFileAsync(IReadOnlyList<string> endings)
    {
        Asked.Add($"open [{string.Join(",", endings)}]");
        return Task.FromResult(Open);
    }

    public Task<bool> ConfirmAsync(string title, string text, string action)
    {
        Asked.Add($"confirm {title} | {text} | {action}");
        return Task.FromResult(Yes);
    }

    public Task<bool?> ConfirmWithBoxAsync(string title, string text, string action, string box)
    {
        Asked.Add($"confirm {title} | {text} | {action} | {box}");
        return Task.FromResult(Box);
    }

    public Task OpenWithAsync(string file)
    {
        Asked.Add($"open with {file}");
        return Task.CompletedTask;
    }
}

[TestClass]
public sealed class FlowsTests
{
    private const string Result =
        "{\"kind\": \"result\", \"song\": \"C:\\\\Music\\\\Eye of the Tiger.flac\", \"title\": \"Eye of the Tiger\", \"subtitle\": \"\", \"artist\": \"\", "
        + "\"seconds\": 10.0, \"tempo\": 90, \"meter\": [4, 4], \"musicxml\": \"C:\\\\Cache\\\\a.musicxml\", \"can_open\": true, \"can_export\": true}";

    private readonly FakeCore core = new();
    private readonly FakeAsk ask = new();
    private AppModel model = null!;
    private Flows flows = null!;

    [TestInitialize]
    public void Launch()
    {
        model = new AppModel(["en"], _ => core, work => work());
        model.Launch();
        flows = new Flows(model, ask, Strings.English);
    }

    private void ShowResult() => core.Emit($"{{\"event\": \"state\", \"seq\": 1, \"state\": {Result}}}");

    private async Task<IReadOnlyList<string>> SentAfterStart(int count)
    {
        Assert.IsTrue(await Recorder.Eventually(() => core.Sent.Count >= count + 1, 10));
        return [.. core.Sent.Skip(1)];
    }

    [TestMethod]
    public async Task ASongIsOpenedFromTheOpenDialogOrNotAtAll()
    {
        await flows.OpenSongAsync();
        ask.Open = null;
        await flows.OpenSongAsync();
        Assert.AreEqual(Command.Open(@"C:\In\song.flac").Line(0), (await SentAfterStart(1)).Single());
        StringAssert.StartsWith(ask.Asked[0], "open [mp3,flac,wav");
    }

    [TestMethod]
    public async Task NothingIsExportedWithoutAResult()
    {
        await flows.ExportMusicXmlAsync();
        await flows.ExportDrumTrackAsync();
        await flows.OpenWithAsync();
        Assert.IsEmpty(ask.Asked);
        Assert.IsNull(flows.Result);
    }

    [TestMethod]
    public async Task TheMusicXmlIsSavedUnderTheSongsName()
    {
        ShowResult();
        await flows.ExportMusicXmlAsync();
        CollectionAssert.AreEqual(new List<string> { "save Eye of the Tiger.musicxml [musicxml]" }, ask.Asked);
        Assert.AreEqual(Command.ExportMusicXml(@"C:\Out\file").Line(0), (await SentAfterStart(1)).Single());
        ask.Save = null;
        await flows.ExportMusicXmlAsync();
        Assert.HasCount(2, core.Sent);
    }

    [TestMethod]
    public async Task TheDrumTrackSaysItsCostFirstAndCanBeLeft()
    {
        ShowResult();
        core.Answer("drum_track_cost", "\"ok\": true, \"minutes\": 8, \"text\": \"About 8 minutes.\", \"download\": true");
        await flows.ExportDrumTrackAsync();
        Assert.AreEqual("confirm Save the Drum Track? | About 8 minutes. | Choose Where to Save…", ask.Asked[0]);
        Assert.AreEqual("save Eye of the Tiger (drums).flac [flac,wav]", ask.Asked[1]);
        var sent = await SentAfterStart(2);
        Assert.AreEqual(Command.ExportDrumTrack(@"C:\Out\file").Line(0), sent[1]);
        ask.Yes = false;
        await flows.ExportDrumTrackAsync();
        Assert.HasCount(3, ask.Asked); // no save dialog after Cancel
        core.Answer("drum_track_cost", "\"ok\": false, \"error\": {\"code\": \"not_now\", \"message\": \"No.\"}");
        await flows.ExportDrumTrackAsync();
        Assert.HasCount(3, ask.Asked); // the refusal is the notice, no question
    }

    [TestMethod]
    public async Task OpenWithShowsWindowsChooserForTheMusicXml()
    {
        ShowResult();
        await flows.OpenWithAsync();
        Assert.AreEqual(@"open with C:\Cache\a.musicxml", ask.Asked.Single());
    }

    [TestMethod]
    public async Task ABackupGetsTheDaysNameAndARestoreAsksWithWhatItHolds()
    {
        await flows.BackUpAsync(new DateOnly(2026, 11, 25));
        Assert.AreEqual("save Stickler Backup 2026-11-25.zip [zip]", ask.Asked[0]);
        await SentAfterStart(1); // back_up goes through the model's sender, the summary not
        core.Answer("backup_summary", "\"ok\": true, \"created\": \"2026-11-22\", \"songs\": 12, \"size\": 4, \"text\": \"Made on 2026-11-22.\"");
        ask.Open = @"C:\B\backup.zip";
        await flows.RestoreAsync();
        Assert.AreEqual("confirm Restore Backup? | Made on 2026-11-22. | Restore", ask.Asked[2]);
        var sent = await SentAfterStart(3);
        Assert.AreEqual(Command.BackUp(@"C:\Out\file").Line(0), sent[0]);
        Assert.AreEqual(Command.Restore(@"C:\B\backup.zip").Line(0), sent[2]);
        ask.Yes = false;
        await flows.RestoreAsync();
        ask.Open = null;
        await flows.RestoreAsync();
        ask.Save = null;
        await flows.BackUpAsync(new DateOnly(2026, 11, 25));
        Assert.HasCount(5, core.Sent); // start, back_up, backup_summary, restore, backup_summary
    }

    [TestMethod]
    public async Task RemovingAsksWithTheSizesAndTheBoxDecidesEverything()
    {
        core.Answer("removal_sizes", "\"ok\": true, \"models\": 1, \"everything\": 2, \"models_text\": \"This frees 2.2 GB.\", \"everything_text\": \"E\"");
        ask.Box = true;
        await flows.RemoveModelsAsync();
        Assert.AreEqual(
            "confirm Remove Downloaded Models? | This frees 2.2 GB. | Remove | Also remove settings, recent songs and corrections",
            ask.Asked.Single());
        var sent = await SentAfterStart(2);
        Assert.AreEqual(Command.RemoveModels(true).Line(0), sent[1]);
        ask.Box = null;
        await flows.RemoveModelsAsync();
        core.Answer("removal_sizes", "not running");
        await flows.RemoveModelsAsync();
        Assert.HasCount(2, ask.Asked);
    }
}

[TestClass]
public sealed class WindowViewTests
{
    private readonly FakeCore core = new();

    private AppModel Shown(string state)
    {
        var model = new AppModel(["en"], _ => core, work => work());
        model.Launch();
        core.Emit($"{{\"event\": \"state\", \"seq\": 1, \"state\": {state}}}");
        return model;
    }

    [TestMethod]
    public void EachStateHasItsPageDialogAndHeader()
    {
        var cases = new (string State, Page Page, SetupDialog Dialog, bool Header)[]
        {
            ("{\"kind\": \"empty\"}", Page.Empty, SetupDialog.None, false),
            ("{\"kind\": \"consent\", \"song\": null, \"models\": [], \"total_size\": \"2 GB\"}", Page.Empty, SetupDialog.Consent, false),
            ("{\"kind\": \"setting_up\", \"song\": null, \"steps\": []}", Page.Empty, SetupDialog.Download, false),
            ("{\"kind\": \"setup_failed\", \"song\": null, \"steps\": [], \"step\": \"a\", \"server\": \"s\", \"details\": \"d\"}", Page.Empty, SetupDialog.Failed, false),
            ("{\"kind\": \"analysing\", \"song\": \"/a\", \"name\": \"a\", \"steps\": []}", Page.Steps, SetupDialog.None, true),
            ("{\"kind\": \"exporting\", \"song\": \"/a\", \"title\": \"a\", \"subtitle\": \"\", \"dest\": \"/d\", \"steps\": []}", Page.Steps, SetupDialog.None, true),
            ("{\"kind\": \"failed\", \"song\": \"/a\", \"name\": \"a\", \"reason\": \"analysis\", \"title\": \"\", \"description\": \"\", \"details\": \"\"}", Page.Failed, SetupDialog.None, true),
            ("{\"kind\": \"result\", \"song\": \"/a\", \"title\": \"a\", \"subtitle\": \"\", \"artist\": \"\", \"seconds\": 1, \"tempo\": 90, \"meter\": [4, 4], \"musicxml\": \"/m\"}", Page.Result, SetupDialog.None, true),
            ("{\"kind\": \"tuning\"}", Page.Empty, SetupDialog.None, false),
        };
        foreach (var (state, page, dialog, header) in cases)
        {
            var model = Shown(state);
            Assert.AreEqual(page, WindowView.Page(model), state);
            Assert.AreEqual(dialog, WindowView.Dialog(model), state);
            Assert.AreEqual(header, WindowView.ShowsHeader(model), state);
        }
    }

    [TestMethod]
    public void AStoppedCoreShowsItsPageAndNoSetupDialogOverIt()
    {
        var model = Shown("{\"kind\": \"setting_up\", \"song\": null, \"steps\": []}");
        Assert.AreEqual(SetupDialog.Download, WindowView.Dialog(model));
        core.Stop(new CoreEnd(CoreEndReason.Exited, 1, "", []));
        Assert.AreEqual(Page.Stopped, WindowView.Page(model));
        Assert.AreEqual(SetupDialog.None, WindowView.Dialog(model));
        Assert.IsFalse(WindowView.ShowsHeader(model));
    }

    [TestMethod]
    public void StepsConsentAndNamesAreWordedAsTheOtherAppsWordThem()
    {
        var english = Strings.English;
        Assert.AreEqual("Done Running Waiting", string.Join(" ", new[] { StepProgress.Done, StepProgress.Running, StepProgress.Waiting }.Select(s => WindowView.StepState(s, english))));
        var adtof = new Model("adtof", "ADTOF", "detects the hits", "NC", "1.3 GB");
        var beats = new Model("beat_this", "Beat This!", "finds the beat", "MIT", "0.9 GB");
        var one = new ConsentScreen(null, [beats], "0.9 GB");
        var two = new ConsentScreen(null, [adtof, beats], "2.2 GB");
        Assert.StartsWith("To hear the drums, Stickler needs a trained model.", WindowView.ConsentIntro(one, english));
        var german = Strings.Load(Path.Combine(Repo.Root, "win", "Stickler", "Strings"), ["de"]);
        Assert.Contains("2", WindowView.ConsentIntro(two, german));
        Assert.IsTrue(WindowView.NamesNonCommercialUse(two));
        Assert.IsFalse(WindowView.NamesNonCommercialUse(one));
        Assert.AreEqual("Eye of the Tiger", WindowView.BaseName(@"C:\Music\Eye of the Tiger.flac"));
        Assert.AreEqual("song.musicxml", WindowView.MusicXmlName("/m/song.mp3"));
        Assert.EndsWith(".flac", WindowView.DrumTrackName("/m/song.mp3", german));
        Assert.AreNotEqual("song (drums).flac", WindowView.DrumTrackName("/m/song.mp3", german));
    }
}
