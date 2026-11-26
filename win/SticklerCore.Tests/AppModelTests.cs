using System.ComponentModel;

namespace Stickler.Core.Tests;

/// <summary>A core that records the commands and answers as told; the test sends its events.</summary>
internal sealed class FakeCore : ICore
{
    private readonly Lock gate = new();
    private readonly List<Command> commands = [];
    private readonly Dictionary<string, string> answers = [];
    private Action<Incoming> onEvent = _ => { };
    private Action<CoreEnd> onEnd = _ => { };

    /// <summary>The commands sent, without the sheet's <c>settings</c> at start (it asks for the
    /// stored note size beside the actions: <see cref="All"/> has it, SheetModelTests checks it).</summary>
    public IReadOnlyList<string> Sent
    {
        get
        {
            lock (gate)
            {
                return [.. commands.Where(c => c.Name != "settings").Select(c => c.Line(0))];
            }
        }
    }

    public IReadOnlyList<string> All
    {
        get
        {
            lock (gate)
            {
                return [.. commands.Select(c => c.Line(0))];
            }
        }
    }

    public double? QuitWith { get; private set; }

    /// <summary>The reply's fields after <c>"id": 1, </c> for <paramref name="command"/>.</summary>
    public void Answer(string command, string fields)
    {
        lock (gate)
        {
            answers[command] = fields;
        }
    }

    public void Start(Action<Incoming> onEvent, Action<CoreEnd> onEnd)
    {
        this.onEvent = onEvent;
        this.onEnd = onEnd;
    }

    public Task<Reply> SendAsync(Command command, CancellationToken cancel = default)
    {
        string fields;
        lock (gate)
        {
            commands.Add(command);
            fields = answers.GetValueOrDefault(command.Name, "\"ok\": true");
        }
        if (fields == "not running")
        {
            return Task.FromException<Reply>(new CoreNotRunningException());
        }
        var reply = Reply.Parse($"{{\"id\": 1, {fields}}}");
        return reply.Error is { } error
            ? Task.FromException<Reply>(new CoreRefusedException(error))
            : Task.FromResult(reply);
    }

    public Task QuitAsync(double seconds)
    {
        QuitWith = seconds;
        return Task.CompletedTask;
    }

    public void Emit(string line) => onEvent(Incoming.Parse(line));

    public void Stop(CoreEnd how) => onEnd(how);
}

[TestClass]
public sealed class AppModelTests
{
    private const string Empty = "{\"kind\": \"empty\", \"can_open\": true}";
    private const string Analysing =
        "{\"kind\": \"analysing\", \"song\": \"/m/a.flac\", \"name\": \"a\", \"steps\": [], \"can_open\": true, \"can_cancel\": true, \"can_close\": true}";
    private const string Result =
        "{\"kind\": \"result\", \"song\": \"/m/a.flac\", \"title\": \"Song A\", \"subtitle\": \"Band · ♩ = 90 · 4/4\", \"artist\": \"Band\", "
        + "\"seconds\": 10.0, \"tempo\": 90, \"meter\": [4, 4], \"musicxml\": \"/c/a.musicxml\", \"can_open\": true, \"can_export\": true}";

    private readonly List<FakeCore> cores = [];

    private AppModel Model() => new(["de-DE", "en"], languages =>
    {
        var core = new FakeCore();
        cores.Add(core);
        return core;
    }, work => work());

    private static string State(int seq, string state) => $"{{\"event\": \"state\", \"seq\": {seq}, \"state\": {state}}}";

    private static async Task<bool> Settled(Func<bool> condition) => await Recorder.Eventually(condition, 10);

    [TestMethod]
    public async Task LaunchStartsTheCoreAndSendsStartThenEveryActionInOrder()
    {
        var model = Model();
        Assert.AreEqual(Phase.Launching, model.Phase);
        model.Launch();
        Assert.AreEqual(Phase.Running, model.Phase);
        var core = cores.Single();
        model.Open("/m/a.flac");
        model.Cancel();
        model.Retry();
        model.Close();
        model.Agree();
        model.NotNow();
        model.RetrySetup();
        model.ExportMusicXml("/d/a.musicxml");
        model.ExportDrumTrack("/d/a.flac");
        model.RemoveModels(everything: true);
        model.BackUp("/d/b.zip");
        model.Restore("/d/b.zip");
        Assert.IsTrue(await Settled(() => core.Sent.Count == 13));
        Assert.AreEqual(
            "start open cancel retry close agree not_now retry_setup export_musicxml export_drum_track remove_models back_up restore",
            string.Join(" ", core.Sent.Select(line => System.Text.Json.JsonElement.Parse(line).GetProperty("cmd").GetString())));
        // the sheet asks for the stored note size once, beside the actions' line
        Assert.AreEqual(1, core.All.Count(line => line.Contains("\"settings\"", StringComparison.Ordinal)));
    }

    [TestMethod]
    public void StatesRecentSongsAndNoticesReachTheWindowAndLateEventsAreDropped()
    {
        var model = Model();
        var changed = new List<string?>();
        model.PropertyChanged += (_, e) => changed.Add(e.PropertyName);
        model.Launch();
        var core = cores.Single();
        core.Emit("{\"event\": \"hello\", \"protocol\": 1, \"version\": \"11\", \"language\": \"de\"}");
        Assert.AreEqual("de", model.Language);
        Assert.AreEqual("11", model.Version);
        core.Emit(State(2, Analysing));
        Assert.IsInstanceOfType<AnalysingScreen>(model.State.Screen);
        Assert.AreEqual("a", model.Title);
        Assert.AreEqual("", model.Subtitle);
        core.Emit(State(1, Empty)); // late: an older state
        Assert.IsInstanceOfType<AnalysingScreen>(model.State.Screen);
        core.Emit(State(3, Result));
        Assert.AreEqual("Song A", model.Title);
        Assert.AreEqual("Band · ♩ = 90 · 4/4", model.Subtitle);
        core.Emit("{\"event\": \"recent\", \"seq\": 4, \"rows\": [{\"path\": \"/m/a.flac\", \"title\": \"Song A\", \"detail\": \"today\", \"missing\": false}]}");
        Assert.AreEqual("Song A", model.Recent.Single().Title);
        core.Emit("{\"event\": \"notice\", \"seq\": 5, \"text\": \"Saved\", \"opens\": \"/d/a.musicxml\"}");
        Assert.AreEqual(new Notice("Saved", "/d/a.musicxml"), model.Notice);
        var serial = model.NoticeSerial;
        core.Emit("{\"event\": \"notice\", \"seq\": 6, \"text\": \"Saved\", \"opens\": \"/d/a.musicxml\"}");
        Assert.AreEqual(serial + 1, model.NoticeSerial); // the same text again is shown again
        core.Emit("{\"event\": \"progress\", \"seq\": 7}");
        core.Emit(State(7, Empty)); // the unknown event took 7
        Assert.IsInstanceOfType<ResultScreen>(model.State.Screen);
        core.Emit("{\"id\": 3, \"ok\": true}"); // a reply goes to its SendAsync, not here
        model.DismissNotice();
        Assert.IsNull(model.Notice);
        model.Tell(new Notice("mine", null));
        Assert.AreEqual("mine", model.Notice!.Text);
        foreach (var name in "Language State Title Subtitle Recent Notice NoticeSerial".Split(' '))
        {
            CollectionAssert.Contains(changed, name);
        }
    }

    [TestMethod]
    public void ExportingAndFailedNameTheSongInTheHeader()
    {
        var model = Model();
        model.Launch();
        cores[0].Emit(State(1, "{\"kind\": \"exporting\", \"song\": \"/a\", \"title\": \"T\", \"subtitle\": \"S\", \"dest\": \"/d\", \"steps\": []}"));
        Assert.AreEqual(("T", "S"), (model.Title, model.Subtitle));
        cores[0].Emit(State(2, "{\"kind\": \"failed\", \"song\": \"/a\", \"name\": \"N\", \"reason\": \"analysis\", \"title\": \"\", \"description\": \"\", \"details\": \"\"}"));
        Assert.AreEqual(("N", ""), (model.Title, model.Subtitle));
        cores[0].Emit(State(3, Empty));
        Assert.AreEqual("Stickler", model.Title);
    }

    [TestMethod]
    public async Task ARefusedCommandSaysWhyAsTheNotice()
    {
        var model = Model();
        model.Launch();
        cores[0].Answer("retry", "\"ok\": false, \"error\": {\"code\": \"not_now\", \"message\": \"Not now.\"}");
        model.Retry();
        Assert.IsTrue(await Settled(() => model.Notice?.Text == "Not now."));
    }

    [TestMethod]
    public async Task QuestionsReturnTheirPayloadOrNullWithTheReason()
    {
        var model = Model();
        Assert.IsNull(await model.DrumTrackCostAsync()); // no core yet
        model.Launch();
        var core = cores[0];
        core.Answer("drum_track_cost", "\"ok\": true, \"minutes\": 3, \"text\": \"About 3 minutes.\", \"download\": false");
        core.Answer("removal_sizes", "\"ok\": true, \"models\": 10, \"everything\": 12, \"models_text\": \"M\", \"everything_text\": \"E\"");
        core.Answer("uninstall_sizes", "\"ok\": true, \"keep\": 10, \"everything\": 12, \"keep_text\": \"K\", \"everything_text\": \"E\"");
        core.Answer("backup_summary", "\"ok\": false, \"error\": {\"code\": \"not_a_backup\", \"message\": \"No backup.\"}");
        core.Answer("uninstall", "not running");
        Assert.AreEqual(3, (await model.DrumTrackCostAsync())!.Minutes);
        Assert.AreEqual("E", (await model.RemovalSizesAsync())!.EverythingText);
        Assert.AreEqual("K", (await model.UninstallSizesAsync())!.KeepText);
        Assert.IsNull(await model.BackupSummaryAsync("/d/x.zip"));
        Assert.AreEqual("No backup.", model.Notice!.Text);
        Assert.IsFalse(await model.UninstallAsync(everything: false));
        core.Answer("uninstall", "\"ok\": true");
        Assert.IsTrue(await model.UninstallAsync(everything: true));
    }

    [TestMethod]
    public async Task TheCoreStoppedShowsItsPageAndStartAgainMakesANewOne()
    {
        var model = Model();
        model.Launch();
        var first = cores[0];
        first.Emit(State(5, Analysing));
        var end = new CoreEnd(CoreEndReason.Exited, 1, "", ["boom"]);
        first.Stop(end);
        Assert.AreEqual(Phase.Stopped, model.Phase);
        Assert.AreEqual(end, model.End);
        model.Open("/m/b.flac"); // nothing to send to
        model.StartAgain();
        Assert.AreEqual(Phase.Running, model.Phase);
        Assert.IsNull(model.End);
        Assert.AreEqual(AppState.Empty, model.State);
        var second = cores[1];
        second.Emit(State(1, Analysing)); // a new core counts from 1 again
        Assert.IsInstanceOfType<AnalysingScreen>(model.State.Screen);
        first.Emit(State(9, Empty)); // the old core is not listened to
        first.Stop(end);
        Assert.AreEqual(Phase.Running, model.Phase);
        Assert.IsTrue(await Settled(() => second.Sent.Count == 1));
        CollectionAssert.DoesNotContain(first.Sent.ToList(), Command.Open("/m/b.flac").Line(0));
    }

    [TestMethod]
    public async Task ARunningCoreIsToldToQuitWhenReplacedAndOnQuit()
    {
        var model = Model();
        await model.QuitAsync(); // nothing runs yet
        model.Launch();
        model.StartAgain();
        Assert.AreEqual(3, cores[0].QuitWith);
        await model.QuitAsync();
        Assert.AreEqual(3, cores[1].QuitWith);
    }

    [TestMethod]
    public async Task ClearRecentForgetsEveryRow()
    {
        var model = Model();
        model.Launch();
        cores[0].Emit("{\"event\": \"recent\", \"seq\": 1, \"rows\": ["
            + "{\"path\": \"/a\", \"title\": \"A\", \"detail\": \"\", \"missing\": false},"
            + "{\"path\": \"/b\", \"title\": \"B\", \"detail\": \"\", \"missing\": true}]}");
        model.ClearRecent();
        model.Forget("/c");
        Assert.IsTrue(await Settled(() => cores[0].Sent.Count == 4));
        CollectionAssert.AreEqual(
            new[] { Command.ForgetRecent("/a").Line(0), Command.ForgetRecent("/b").Line(0), Command.ForgetRecent("/c").Line(0) },
            cores[0].Sent.Skip(1).ToArray());
    }
}
