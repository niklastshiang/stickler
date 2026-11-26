using System.Text.Json;

namespace Stickler.Core.Tests;

/// <summary>A core whose replies the test gives, one command at a time and in any order.</summary>
internal sealed class ScriptedCore : ICore
{
    private readonly Lock gate = new();
    private readonly List<(Command Command, TaskCompletionSource<Reply> Reply)> asked = [];

    public IReadOnlyList<string> Sent
    {
        get
        {
            lock (gate)
            {
                return [.. asked.Select(a => a.Command.Line(0))];
            }
        }
    }

    /// <summary>The commands named <paramref name="name"/> so far, oldest first.</summary>
    public int Count(string name)
    {
        lock (gate)
        {
            return asked.Count(a => a.Command.Name == name);
        }
    }

    /// <summary>The argument <paramref name="key"/> of the <paramref name="index"/>-th command named <paramref name="name"/>.</summary>
    public double Argument(string name, int index, string key)
    {
        lock (gate)
        {
            var line = asked.Where(a => a.Command.Name == name).ElementAt(index).Command.Line(0);
            return JsonElement.Parse(line).GetProperty(key).GetDouble();
        }
    }

    /// <summary>Answers the <paramref name="index"/>-th command named <paramref name="name"/>
    /// with the reply's fields after <c>"id": 1, </c>.</summary>
    public void Answer(string name, int index, string fields)
    {
        TaskCompletionSource<Reply> reply;
        lock (gate)
        {
            reply = asked.Where(a => a.Command.Name == name).ElementAt(index).Reply;
        }
        var parsed = Reply.Parse($"{{\"id\": 1, {fields}}}");
        if (parsed.Error is { } error)
        {
            reply.SetException(new CoreRefusedException(error));
        }
        else
        {
            reply.SetResult(parsed);
        }
    }

    public void Gone(string name, int index)
    {
        lock (gate)
        {
            asked.Where(a => a.Command.Name == name).ElementAt(index).Reply.SetException(new CoreNotRunningException());
        }
    }

    public void Start(Action<Incoming> onEvent, Action<CoreEnd> onEnd)
    {
    }

    public Task<Reply> SendAsync(Command command, CancellationToken cancel = default)
    {
        var reply = new TaskCompletionSource<Reply>(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (gate)
        {
            asked.Add((command, reply));
        }
        return reply.Task;
    }

    public Task QuitAsync(double seconds) => Task.CompletedTask;
}

[TestClass]
public sealed class SheetModelTests
{
    private const string Settings = "\"ok\": true, \"appearance\": \"system\", \"zoom\": 1.5, \"song_volume\": 0.7, \"hits_volume\": 1.0, \"setup_agreed\": true, \"percent\": \"150%\"";

    private static readonly ResultScreen Groove = Result("/m/groove.wav", 0);

    private readonly Lock gate = new();
    private readonly List<BridgeError> refusals = [];

    private static ResultScreen Result(string song, int sheet) =>
        new(song, "Groove", "", "", 8.0, 120, [4, 4], "/c/groove.musicxml", null, [], sheet);

    private static string PagesReply(double width, double zoom = 1.5, string svg = "<svg/>") =>
        $"\"ok\": true, \"zoom\": {zoom.ToString(System.Globalization.CultureInfo.InvariantCulture)}, \"pages\": [{{\"svg\": \"{svg}\", \"width\": {width.ToString(System.Globalization.CultureInfo.InvariantCulture)}, \"height\": 300.0, \"bars\": []}}]";

    private static Task<bool> Settled(Func<bool> condition) => Recorder.Eventually(condition, 10);

    /// <summary>A sheet model whose work runs at once, under one lock, as the window's thread would.</summary>
    private SheetModel Model(TimeSpan? settle = null) =>
        new(work =>
        {
            lock (gate)
            {
                work();
            }
        }, settle ?? TimeSpan.FromMilliseconds(50), error =>
        {
            lock (gate)
            {
                refusals.Add(error);
            }
        });

    private static async Task<(SheetModel Sheet, ScriptedCore Core)> Shown(SheetModel sheet, double width = 800)
    {
        var core = new ScriptedCore();
        sheet.Attach(core);
        core.Answer("settings", 0, Settings);
        Assert.IsTrue(await Settled(() => sheet.Zoom == 1.5));
        sheet.Show(Groove);
        sheet.Resize(width);
        Assert.IsTrue(await Settled(() => core.Count("pages") == 1));
        core.Answer("pages", 0, PagesReply(width));
        Assert.IsTrue(await Settled(() => sheet.Pages.Count == 1));
        return (sheet, core);
    }

    [TestMethod]
    public async Task TheFirstPagesComeAtTheWidthAndTheStoredSize()
    {
        var sheet = Model();
        Assert.IsFalse(sheet.CanZoom);
        var (_, core) = await Shown(sheet);
        Assert.AreEqual("150%", sheet.Percent);
        Assert.IsTrue(sheet.CanZoom);
        Assert.AreEqual(800.0, core.Argument("pages", 0, "width"));
        // the stored size is the core's: pages are asked for without a zoom of their own
        Assert.IsFalse(JsonElement.Parse(core.Sent[^1]).TryGetProperty("zoom", out _));
        Assert.AreEqual(800.0, sheet.Pages.Single().Width);
    }

    [TestMethod]
    public async Task NothingIsAskedBeforeAWidthOrAResult()
    {
        var sheet = Model();
        var core = new ScriptedCore();
        sheet.Attach(core);
        sheet.Show(Groove); // no width yet
        Assert.AreEqual(0, core.Count("pages"));
        var other = Model();
        var second = new ScriptedCore();
        other.Attach(second);
        other.Resize(800); // no result yet
        Assert.AreEqual(0, second.Count("pages"));
        other.Show(Groove);
        Assert.AreEqual(1, second.Count("pages"));
        // a sheet without a core asks nothing and changes nothing
        var alone = Model();
        alone.Show(Groove);
        alone.Resize(800);
        alone.ZoomIn();
        Assert.IsEmpty(alone.Pages);
        await Task.CompletedTask;
    }

    [TestMethod]
    public async Task ANewSongOrANewNotationAsksAgainTheSameResultDoesNot()
    {
        var (sheet, core) = await Shown(Model());
        sheet.Show(Groove); // the same state again (a correction starting, a notice)
        Assert.AreEqual(1, core.Count("pages"));
        sheet.Show(Result("/m/groove.wav", 1)); // a correction's new notation
        Assert.AreEqual(2, core.Count("pages"));
        sheet.Show(Result("/m/other.wav", 1)); // another song
        Assert.AreEqual(3, core.Count("pages"));
    }

    [TestMethod]
    public async Task AnExportKeepsThePagesAndPausesTheZoom()
    {
        var (sheet, core) = await Shown(Model());
        sheet.Show(new ExportingScreen("/m/groove.wav", "Groove", "", "/d/x.flac", []));
        Assert.AreEqual(1, sheet.Pages.Count);
        Assert.IsFalse(sheet.CanZoom);
        // a resize meanwhile is owed and asked for when the result is back
        sheet.Resize(600);
        await Task.Delay(200);
        Assert.AreEqual(1, core.Count("pages"));
        sheet.Show(Groove);
        Assert.IsTrue(sheet.CanZoom);
        Assert.AreEqual(2, core.Count("pages"));
        Assert.AreEqual(600.0, core.Argument("pages", 1, "width"));
    }

    [TestMethod]
    public async Task AnotherScreenEmptiesTheSheet()
    {
        var (sheet, _) = await Shown(Model());
        sheet.Show(new AnalysingScreen("/m/b.wav", "b", []));
        Assert.IsEmpty(sheet.Pages);
        Assert.IsFalse(sheet.CanZoom);
    }

    [TestMethod]
    public async Task AQuickSeriesOfWidthsMakesOneRequestAfterThePause()
    {
        var (sheet, core) = await Shown(Model(TimeSpan.FromMilliseconds(150)));
        sheet.Resize(700);
        sheet.Resize(650);
        sheet.Resize(600);
        Assert.IsTrue(await Settled(() => core.Count("pages") == 2));
        await Task.Delay(400);
        Assert.AreEqual(2, core.Count("pages"));
        Assert.AreEqual(600.0, core.Argument("pages", 1, "width"));
        sheet.Resize(600); // the same width again: nothing
        await Task.Delay(300);
        Assert.AreEqual(2, core.Count("pages"));
    }

    [TestMethod]
    public async Task TheZoomEntriesSendTheirCommandsAndAskForPagesAtTheNewSize()
    {
        var (sheet, core) = await Shown(Model());
        sheet.ZoomIn();
        core.Answer("zoom_in", 0, "\"ok\": true, \"zoom\": 1.875, \"percent\": \"188%\"");
        Assert.IsTrue(await Settled(() => core.Count("pages") == 2));
        Assert.AreEqual("188%", sheet.Percent);
        sheet.ZoomOut();
        core.Answer("zoom_out", 0, "\"ok\": true, \"zoom\": 1.5, \"percent\": \"150%\"");
        Assert.IsTrue(await Settled(() => core.Count("pages") == 3));
        sheet.ActualSize();
        core.Answer("actual_size", 0, "\"ok\": true, \"zoom\": 1.0, \"percent\": \"100%\"");
        Assert.IsTrue(await Settled(() => core.Count("pages") == 4));
        sheet.SetZoom(2);
        Assert.IsTrue(await Settled(() => core.Count("set_zoom") == 1));
        Assert.AreEqual(2.0, core.Argument("set_zoom", 0, "zoom"));
        core.Answer("set_zoom", 0, "\"ok\": true, \"zoom\": 2.0, \"percent\": \"200%\"");
        Assert.IsTrue(await Settled(() => core.Count("pages") == 5));
        core.Answer("pages", 4, PagesReply(800, zoom: 2.0));
        Assert.IsTrue(await Settled(() => sheet.Zoom == 2.0));
        Assert.AreEqual("200%", sheet.Percent);
    }

    [TestMethod]
    public async Task AReplyANewerRequestOvertookIsDropped()
    {
        var (sheet, core) = await Shown(Model());
        sheet.Show(Result("/m/groove.wav", 1));
        sheet.Show(Result("/m/groove.wav", 2));
        Assert.AreEqual(3, core.Count("pages"));
        core.Answer("pages", 2, PagesReply(800, svg: "<svg id='new'/>"));
        Assert.IsTrue(await Settled(() => sheet.Pages.Single().Svg.Contains("new", StringComparison.Ordinal)));
        core.Answer("pages", 1, PagesReply(800, svg: "<svg id='old'/>"));
        await Task.Delay(200);
        Assert.Contains("new", sheet.Pages.Single().Svg);
    }

    [TestMethod]
    public async Task ARefusalKeepsTheOldPagesAndSaysWhy()
    {
        var (sheet, core) = await Shown(Model());
        sheet.Show(Result("/m/groove.wav", 1));
        core.Answer("pages", 1, "\"ok\": false, \"error\": {\"code\": \"not_now\", \"message\": \"This is not possible right now.\"}");
        Assert.IsTrue(await Settled(() =>
        {
            lock (gate)
            {
                return refusals.Count == 1;
            }
        }));
        Assert.AreEqual("not_now", refusals.Single().Code);
        Assert.AreEqual(1, sheet.Pages.Count);
        // a refused zoom says why as well; a refusal of an overtaken request says nothing
        sheet.ZoomIn();
        core.Answer("zoom_in", 0, "\"ok\": false, \"error\": {\"code\": \"not_now\", \"message\": \"No.\"}");
        Assert.IsTrue(await Settled(() =>
        {
            lock (gate)
            {
                return refusals.Count == 2;
            }
        }));
        sheet.Show(Result("/m/groove.wav", 2));
        sheet.Show(Result("/m/groove.wav", 3));
        core.Answer("pages", 2, "\"ok\": false, \"error\": {\"code\": \"not_now\", \"message\": \"Late.\"}");
        await Task.Delay(200);
        Assert.HasCount(2, refusals);
    }

    [TestMethod]
    public async Task ANewCoreStartsEmptyAndRepliesOfTheOldOneAreDropped()
    {
        var (sheet, core) = await Shown(Model());
        sheet.Show(Result("/m/groove.wav", 1));
        var next = new ScriptedCore();
        sheet.Attach(next);
        Assert.IsEmpty(sheet.Pages);
        Assert.IsFalse(sheet.CanZoom);
        core.Answer("pages", 1, PagesReply(800));
        await Task.Delay(200);
        Assert.IsEmpty(sheet.Pages);
        next.Gone("settings", 0); // the new core ended before its reply: nothing to tell
        sheet.Attach(null);
        sheet.ZoomIn();
        Assert.AreEqual(0, next.Count("zoom_in"));
    }
}
