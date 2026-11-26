namespace Stickler.Core.Tests;

[TestClass]
public sealed class PlaybackTests
{
    private static readonly double[] SameBar = [0.5, 1.0, 1.5, 1.9];
    private static readonly double[] JustZero = [0.0];

    private static IReadOnlyList<SongBar> SongBars => TimelineTests.SongBars;

    private static string Volumes(Hear hear, double? song = null, double? hits = null) => Command.Volumes(hear, song, hits).Line(0);

    private static string Step(double at, int by) => Command.StepBy(at, by).Line(0);

    private static string Jump(int bar, double at) => Command.Jump(bar, at).Line(0);

    /// <summary>A model with a result shown and ready to play.</summary>
    private static async Task<PlaybackHarness> Ready(FakePlayer player, string? clicks = "/c/e.wav", string song = "/m/e.flac")
    {
        var harness = PlaybackHarness.Playing(player);
        harness.Core.Emit(PlaybackHarness.PlayingResult(1, song, clicks));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        return harness;
    }

    private static async Task<PlaybackHarness> Started(FakePlayer player)
    {
        var harness = await Ready(player);
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        return harness;
    }

    [TestMethod]
    public async Task WithoutAResultOrAPlayerNothingPlays()
    {
        var player = new FakePlayer();
        var harness = PlaybackHarness.Playing(player);
        var playback = harness.Playback;
        Assert.IsFalse(harness.Read(() => playback.CanPlay));
        harness.Ui(() =>
        {
            playback.Toggle();
            playback.NextBar();
            playback.Jump(2);
            playback.GoToStart();
            playback.Seek(3);
        });
        Assert.IsTrue(await harness.Settled(() => harness.Core.Actions.SequenceEqual([Command.Start.Line(0)])));
        Assert.IsEmpty(player.Loads);
        Assert.AreEqual(0, harness.Read(() => playback.Position));
        Assert.AreEqual("", harness.Read(() => playback.Label));
        Assert.IsNull(harness.Read(() => playback.Marked));

        var silent = new PlaybackHarness(null);
        silent.Ui(silent.Model.Launch);
        silent.Core.Emit(PlaybackHarness.PlayingResult(1));
        Assert.IsTrue(await silent.Settled(() => silent.Playback.Length == 12));
        Assert.IsFalse(silent.Read(() => silent.Playback.CanPlay)); // no player
        silent.Ui(silent.Playback.Toggle);
        Assert.AreEqual(0, silent.Core.Asked("settings").Count - 1); // only the sheet asked for the settings
    }

    [TestMethod]
    public async Task TheStoredVolumesComeWithTheCore()
    {
        var harness = new PlaybackHarness(new FakePlayer());
        harness.Preset("settings", PlaybackHarness.SettingsReply);
        harness.Ui(harness.Model.Launch);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.SongVolume == 0.4));
        Assert.AreEqual(0.9, harness.Read(() => harness.Playback.HitsVolume));
    }

    [TestMethod]
    public async Task AResultIsReadyAtItsStart()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        var playback = harness.Playback;
        Assert.AreEqual(12, harness.Read(() => playback.Length));
        Assert.AreEqual("0:12", harness.Read(() => playback.LengthText));
        Assert.AreEqual("0:00", harness.Read(() => playback.Time));
        Assert.AreEqual("Bar 1 of 6", harness.Read(() => playback.Label));
        Assert.AreEqual(1, harness.Read(() => playback.Marked));
        CollectionAssert.AreEqual(SongBars.ToList(), harness.Read(() => playback.Bars).ToList());
        Assert.IsFalse(harness.Read(() => playback.Playing));
        Assert.IsEmpty(player.Loads); // loaded on the first play
    }

    [TestMethod]
    public async Task TheMarkedBarChangesOnlyWithTheBar()
    {
        var harness = PlaybackHarness.Playing(new FakePlayer());
        var playback = harness.Playback;
        Assert.IsNull(harness.Read(() => playback.Marked));
        harness.Core.Emit(PlaybackHarness.PlayingResult(1));
        Assert.IsTrue(await harness.Settled(() => playback.Marked == 1));
        var changed = new List<string?>();
        playback.PropertyChanged += (_, e) => changed.Add(e.PropertyName);
        foreach (var second in SameBar)
        {
            harness.Ui(() => playback.Seek(second)); // the same bar: the sheet is not drawn again
        }
        CollectionAssert.DoesNotContain(changed, "Marked");
        harness.Ui(() => playback.Seek(2.5));
        CollectionAssert.Contains(changed, "Marked");
        Assert.AreEqual(2, harness.Read(() => playback.Marked));
        harness.Ui(() => playback.Seek(12)); // after the last bar: nothing sounds
        Assert.IsTrue(await harness.Settled(() => playback.Marked is null));
        harness.Core.Emit(PlaybackHarness.EmptyEvent(2));
        harness.Ui(() => playback.Seek(0));
        Assert.IsTrue(await harness.Settled(() => playback.Length == 0));
        Assert.IsNull(harness.Read(() => playback.Marked));
    }

    [TestMethod]
    public async Task PlayLoadsBothSourcesAtTheCoresGainsAndFollowsThePosition()
    {
        var player = new FakePlayer();
        var ticker = new ManualTicker();
        var harness = PlaybackHarness.Playing(player, ticker.Start);
        harness.Core.Emit(PlaybackHarness.PlayingResult(1));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        var playback = harness.Playback;
        Assert.AreEqual(0, ticker.Started); // nothing ticks while stopped
        harness.Ui(playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => playback.Playing));
        CollectionAssert.AreEqual(new[] { ("/m/e.flac", "/c/e.wav") }, player.Loads.ToArray());
        CollectionAssert.AreEqual(new[] { Volumes(Hear.Both) }, harness.VolumesAsked().ToArray());
        CollectionAssert.AreEqual(new[] { new Gains(0.7, 1.0) }, player.GainsSet.ToArray());
        Assert.IsTrue(player.IsPlaying);
        CollectionAssert.AreEqual(JustZero, player.Seeks.ToArray());
        Assert.AreEqual(1, ticker.Live);
        player.Position = 5;
        harness.Ui(ticker.Fire);
        Assert.AreEqual(5, harness.Read(() => playback.Position));
        Assert.AreEqual("Bar 3 of 6", harness.Read(() => playback.Label));
        Assert.AreEqual(1, harness.Read(() => playback.Marked));
        Assert.AreEqual("0:05", harness.Read(() => playback.Time));

        harness.Ui(playback.Toggle); // pause
        Assert.IsFalse(harness.Read(() => playback.Playing));
        Assert.IsFalse(player.IsPlaying);
        Assert.AreEqual(5, harness.Read(() => playback.Position));
        Assert.AreEqual(0, ticker.Live);
        player.Position = 7; // a tick after the pause changes nothing
        harness.Ui(ticker.Fire);
        Assert.AreEqual(5, harness.Read(() => playback.Position));
        harness.Ui(playback.Toggle); // on from where it paused, nothing loaded again
        Assert.IsTrue(await harness.Settled(() => playback.Playing));
        Assert.HasCount(1, player.Loads);
        Assert.AreEqual(5, player.Seeks[^1]);
        Assert.HasCount(1, harness.VolumesAsked());
    }

    [TestMethod]
    public async Task TheRealTimerFollowsThePositionOnlyWhilePlaying()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        player.Position = 3;
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Position == 3));
        harness.Ui(harness.Playback.Toggle);
        player.Position = 9;
        harness.Flush(); // what a tick posted before the pause could still do has run
        Assert.AreEqual(3, harness.Read(() => harness.Playback.Position));
    }

    [TestMethod]
    public async Task ASongWithoutClicksPlaysAlone()
    {
        var player = new FakePlayer();
        var harness = await Ready(player, clicks: null);
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.IsNull(player.Loads[0].Clicks);
    }

    [TestMethod]
    public async Task TheArrowsAndABarClickGoWhereTheCoreSays()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        var playback = harness.Playback;
        harness.Ui(() => playback.Seek(5));
        harness.Core.Answer("step", "\"ok\": true, \"seconds\": 2.0");
        harness.Ui(playback.PreviousBar);
        Assert.IsTrue(await harness.Settled(() => playback.Position == 2));
        harness.Ui(playback.NextBar);
        Assert.IsTrue(await harness.Settled(() => harness.Count("step") == 2));
        CollectionAssert.AreEqual(new[] { Step(5, -1), Step(2, 1) }, harness.Core.Asked("step").ToArray());

        harness.Core.Answer("jump", "\"ok\": true, \"seconds\": 8.0");
        harness.Ui(() => playback.Jump(3)); // stopped: the position moves, nothing plays
        Assert.IsTrue(await harness.Settled(() => playback.Position == 8));
        CollectionAssert.Contains(harness.Core.Asked("jump").ToList(), Jump(3, 2));
        Assert.IsFalse(harness.Read(() => playback.Playing));
        Assert.IsEmpty(player.Loads);

        harness.Core.Answer("jump", "\"ok\": true, \"seconds\": null");
        harness.Ui(() => playback.Jump(9)); // never played: nowhere to go
        var held = new Gate();
        harness.Core.Queue("step", "\"ok\": true, \"seconds\": 1.0", held.Opened);
        harness.Ui(playback.NextBar); // asked only when the jump is done
        Assert.IsTrue(await harness.Settled(() => harness.Count("step") == 3));
        Assert.AreEqual(8, harness.Read(() => playback.Position));
        held.Release();
        Assert.IsTrue(await harness.Settled(() => playback.Position == 1));

        harness.Ui(playback.GoToStart);
        Assert.AreEqual(0, harness.Read(() => playback.Position));
        harness.Ui(() => playback.Seek(99)); // kept inside the song
        Assert.AreEqual(12, harness.Read(() => playback.Position));
        harness.Ui(() => playback.Seek(-3));
        Assert.AreEqual(0, harness.Read(() => playback.Position));
    }

    [TestMethod]
    public async Task WhilePlayingTheArrowsAskFromThePlayersPosition()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        player.Position = 6.5;
        harness.Core.Answer("step", "\"ok\": true, \"seconds\": 8.0");
        harness.Ui(harness.Playback.NextBar);
        Assert.IsTrue(await harness.Settled(() => player.Seeks[^1] == 8));
        CollectionAssert.Contains(harness.Core.Asked("step").ToList(), Step(6.5, 1));
    }

    [TestMethod]
    public async Task ARefusedCommandSaysWhy()
    {
        var harness = await Ready(new FakePlayer());
        harness.Core.Answer("step", PlaybackHarness.Refusal("Not now."));
        harness.Ui(harness.Playback.NextBar);
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "Not now."));
        harness.Core.Answer("volumes", PlaybackHarness.Refusal("No volumes."));
        harness.Ui(() => harness.Playback.SetHear(Hear.Song));
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "No volumes."));
        harness.Preset("settings", PlaybackHarness.Refusal("No settings."));
        harness.Ui(harness.Model.StartAgain);
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "No settings."));
    }

    [TestMethod]
    public async Task AnAnswerThatCannotBeReadOrACoreThatIsGoneChangesNothing()
    {
        var harness = await Ready(new FakePlayer());
        harness.Core.Answer("step", "\"ok\": true"); // no `seconds` field at all
        harness.Core.Answer("volumes", "not running");
        harness.Core.Answer("jump", "\"ok\": true, \"seconds\": \"soon\"");
        harness.Ui(harness.Playback.NextBar);
        harness.Ui(() => harness.Playback.SetHear(Hear.Hits));
        harness.Ui(() => harness.Playback.Jump(2));
        Assert.IsTrue(await harness.Settled(() => harness.Count("step") + harness.Count("volumes") + harness.Count("jump") == 3));
        // one more of each, held back: it is asked only when the one before is done with
        var held = new Gate();
        harness.Core.Queue("step", "\"ok\": true, \"seconds\": 5.0", held.Opened);
        harness.Core.Queue("volumes", PlaybackHarness.GainsReply, held.Opened);
        harness.Ui(harness.Playback.NextBar);
        harness.Ui(() => harness.Playback.SetHear(Hear.Both));
        Assert.IsTrue(await harness.Settled(() => harness.Count("step") == 2 && harness.Count("volumes") == 2));
        Assert.AreEqual(0, harness.Read(() => harness.Playback.Position));
        Assert.IsNull(harness.Read(() => harness.Model.Notice));
        Assert.AreEqual(Hear.Both, harness.Read(() => harness.Playback.Hear));
        held.Release();
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Position == 5));
    }

    [TestMethod]
    public async Task TheEndStopsAndPlayStartsAgainAtTheBeginning()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        player.Position = 12;
        player.Pauses(PlayerPause.Ended); // from the device's thread
        harness.Flush();
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.AreEqual(12, harness.Read(() => harness.Playback.Position));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual(0, player.Seeks[^1]);
        Assert.AreEqual(0, harness.Read(() => harness.Playback.Position));
    }

    [TestMethod]
    public async Task AnOutputThatChangedPausesWhereItWas()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        player.Position = 3;
        player.Pauses(PlayerPause.Interrupted);
        harness.Flush();
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.AreEqual(3, harness.Read(() => harness.Playback.Position));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual(3, player.Seeks[^1]);
    }

    [TestMethod]
    public async Task ANewSongCloseAndAStoppedCoreStopTheSound()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        var playback = harness.Playback;
        player.Position = 4;

        // a correction of the same song goes on with its new bars
        var corrected = SongBars.Take(3).ToList();
        harness.Core.Emit(PlaybackHarness.PlayingResult(2, bars: corrected));
        Assert.IsTrue(await harness.Settled(() => playback.Bars.Count == 3));
        CollectionAssert.AreEqual(corrected, harness.Read(() => playback.Bars).ToList());
        Assert.IsTrue(harness.Read(() => playback.Playing));
        Assert.AreEqual(0, player.Releases);

        harness.Core.Emit(PlaybackHarness.PlayingResult(3, song: "/m/other.flac"));
        Assert.IsTrue(await harness.Settled(() => player.Releases == 1));
        Assert.IsFalse(harness.Read(() => playback.Playing));
        Assert.AreEqual(0, harness.Read(() => playback.Position));
        harness.Ui(playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => playback.Playing));
        Assert.AreEqual("/m/other.flac", player.Loads[^1].Song);

        harness.Core.Emit(PlaybackHarness.EmptyEvent(4));
        Assert.IsTrue(await harness.Settled(() => player.Releases == 2));
        Assert.IsFalse(harness.Read(() => playback.Playing));
        Assert.IsFalse(harness.Read(() => playback.CanPlay));

        harness.Core.Emit(PlaybackHarness.PlayingResult(5));
        Assert.IsTrue(await harness.Settled(() => playback.CanPlay));
        harness.Ui(playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => playback.Playing));
        harness.Core.Stop(new CoreEnd(CoreEndReason.Exited, 9, "", []));
        Assert.IsTrue(await harness.Settled(() => player.Releases == 3));
        Assert.IsFalse(harness.Read(() => playback.Playing));
        Assert.IsFalse(harness.Read(() => playback.CanPlay));
    }

    [TestMethod]
    public async Task AnExportPausesAndHidesTheControls()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        harness.Core.Emit(PlaybackHarness.ExportingEvent(2));
        Assert.IsTrue(await harness.Settled(() => !harness.Playback.CanPlay));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.IsFalse(player.IsPlaying);
        Assert.AreEqual(0, player.Releases);
        harness.Core.Emit(PlaybackHarness.PlayingResult(3)); // back: the song is still loaded
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.HasCount(1, player.Loads);
    }

    [TestMethod]
    public async Task ADifferentScreenWhileStoppedOnlyForgetsTheSong()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        harness.Core.Emit(PlaybackHarness.ExportingEvent(2)); // stopped: nothing to pause
        Assert.IsTrue(await harness.Settled(() => !harness.Playback.CanPlay));
        Assert.AreEqual(0, player.Releases);
        harness.Core.Emit(PlaybackHarness.EmptyEvent(3));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsEmpty(player.Loads);
    }

    // what the core decides for playback: a copy of the song, the gains

    [TestMethod]
    public async Task ASongTheSystemCannotReadPlaysFromTheCoresCopy()
    {
        var player = new FakePlayer();
        player.Unreadable("/m/e.ogg");
        var harness = PlaybackHarness.Playing(player);
        harness.Core.Answer("playable", "\"ok\": true, \"path\": \"/c/e.flac\"");
        harness.Core.Emit(PlaybackHarness.PlayingResult(1, song: "/m/e.ogg"));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual("/c/e.flac", player.Loads.Single().Song);
        CollectionAssert.Contains(harness.Core.Asked("playable").ToList(), Command.Playable.Line(0));
    }

    [TestMethod]
    public async Task ASongThatPlaysNowhereSaysWhy()
    {
        var player = new FakePlayer();
        player.Unreadable("/m/e.ogg");
        var harness = PlaybackHarness.Playing(player);
        harness.Core.Answer("playable", PlaybackHarness.Refusal("“e.ogg” cannot be played."));
        harness.Core.Emit(PlaybackHarness.PlayingResult(1, song: "/m/e.ogg"));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "“e.ogg” cannot be played."));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));

        player.Unreadable();
        player.FailToLoad(new PlayerFailedException("No sound device."));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "No sound device."));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));

        player.FailToLoad(null);
        player.FailToPlay(new PlayerFailedException("The output is busy."));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "The output is busy."));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
    }

    [TestMethod]
    public async Task ACopyThatCannotBeAskedForBecauseTheCoreIsGoneSaysNothing()
    {
        var player = new FakePlayer();
        player.Unreadable("/m/e.ogg");
        var harness = PlaybackHarness.Playing(player);
        harness.Core.Emit(PlaybackHarness.PlayingResult(1, song: "/m/e.ogg"));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Core.Answer("playable", "not running");
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Count("playable") == 1));
        Assert.IsTrue(await harness.Settled(() => !harness.Playback.Starting)); // the answer is dealt with
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.IsNull(harness.Read(() => harness.Model.Notice));
        harness.Ui(() => harness.Playback.Toggle()); // not stuck: it tries again
        Assert.IsTrue(await harness.Settled(() => harness.Count("playable") == 2));
    }

    [TestMethod]
    public async Task WhatToHearAndTheVolumesAreTheCoresGains()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        var playback = harness.Playback;

        harness.Core.Answer("volumes", "\"ok\": true, \"song\": 0.0, \"hits\": 1.0");
        harness.Ui(() => playback.SetHear(Hear.Hits));
        Assert.AreEqual(Hear.Hits, harness.Read(() => playback.Hear));
        Assert.IsTrue(await harness.Settled(() => player.GainsSet[^1] == new Gains(0, 1)));
        harness.Core.Answer("volumes", "\"ok\": true, \"song\": 0.0, \"hits\": 0.5");
        harness.Ui(() => playback.SetHitsVolume(0.5));
        Assert.AreEqual(0.5, harness.Read(() => playback.HitsVolume));
        Assert.IsTrue(await harness.Settled(() => player.GainsSet[^1] == new Gains(0, 0.5)));
        harness.Ui(() => playback.SetSongVolume(0.3));
        Assert.AreEqual(0.3, harness.Read(() => playback.SongVolume));
        Assert.IsTrue(await harness.Settled(() => harness.VolumesAsked().Count == 4));
        CollectionAssert.AreEqual(
            new[] { Volumes(Hear.Hits), Volumes(Hear.Hits, hits: 0.5), Volumes(Hear.Hits, song: 0.3) },
            harness.VolumesAsked().Skip(1).ToArray());
    }

    [TestMethod]
    public async Task AnAnswerANewerChangeOvertookIsDropped()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        var late = new Gate();
        harness.Core.Queue("volumes", "\"ok\": true, \"song\": 0.1, \"hits\": 0.1", late.Opened);
        harness.Core.Queue("volumes", "\"ok\": true, \"song\": 0.2, \"hits\": 0.2");
        harness.Ui(() =>
        {
            harness.Playback.SetSongVolume(0.1);
            harness.Playback.SetSongVolume(0.2);
        });
        late.Release();
        await harness.Quiet(); // both answers are in; the older one came first
        Assert.AreEqual(new Gains(0.2, 0.2), player.GainsSet[^1]);
        Assert.DoesNotContain(new Gains(0.1, 0.1), player.GainsSet);
    }

    [TestMethod]
    public async Task TheVolumesBeforeAPlayAreUsedWhenItLoads()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        harness.Core.Answer("volumes", "\"ok\": true, \"song\": 0.3, \"hits\": 1.0");
        harness.Ui(() => harness.Playback.SetSongVolume(0.3));
        Assert.IsTrue(await harness.Settled(() => harness.VolumesAsked().Count == 1));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        CollectionAssert.AreEqual(new[] { new Gains(0.3, 1.0) }, player.GainsSet.ToArray());
        Assert.HasCount(1, harness.VolumesAsked()); // the gains were known
    }

    // the edges, found by the review of the Mac's task 167

    [TestMethod]
    public async Task PlayingFromTheEndEndsAtOnceAndPlayStartsAgainAtTheBeginning()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        harness.Ui(() => harness.Playback.Seek(12)); // the slider at its end
        player.EndsAtOnce = true;
        harness.Ui(harness.Playback.Toggle);
        await player.EndTold; // the device stopped, from its own thread, after Play returned
        harness.Flush();
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing), "nothing was left to play");
        player.EndsAtOnce = false;
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual(0, player.Seeks[^1]);
    }

    [TestMethod]
    public async Task QuickArrowsGoAsManyBarsOn()
    {
        var harness = await Ready(new FakePlayer());
        harness.Core.Queue("step", "\"ok\": true, \"seconds\": 2.0", TimeSpan.FromMilliseconds(40));
        harness.Core.Queue("step", "\"ok\": true, \"seconds\": 4.0");
        harness.Ui(() =>
        {
            harness.Playback.NextBar();
            harness.Playback.NextBar(); // before the first answer came
        });
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Position == 4));
        CollectionAssert.AreEqual(new[] { Step(0, 1), Step(2, 1) }, harness.Core.Asked("step").ToArray());
    }

    [TestMethod]
    public async Task ASecondPressCallsOffAPlayThatWaits()
    {
        var player = new FakePlayer();
        player.Unreadable("/m/e.ogg");
        var harness = PlaybackHarness.Playing(player);
        var making = new Gate();
        harness.Core.Queue("playable", "\"ok\": true, \"path\": \"/c/e.flac\"", making.Opened);
        harness.Core.Emit(PlaybackHarness.PlayingResult(1, song: "/m/e.ogg"));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Count("playable") == 1));
        harness.Ui(harness.Playback.Toggle); // the copy is still being made
        making.Release();
        Assert.IsTrue(await harness.Settled(() => !harness.Playback.Starting));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.IsFalse(player.IsPlaying);
        harness.Ui(harness.Playback.Toggle); // the copy is loaded now: it plays at once
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
    }

    [TestMethod]
    public async Task ACopyThePlayerCannotReadEitherSaysWhy()
    {
        var player = new FakePlayer();
        player.Unreadable("/m/e.ogg", "/c/e.flac");
        var harness = PlaybackHarness.Playing(player);
        harness.Core.Answer("playable", "\"ok\": true, \"path\": \"/c/e.flac\"");
        harness.Core.Emit(PlaybackHarness.PlayingResult(1, song: "/m/e.ogg"));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "Cannot read e.flac."));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
    }

    [TestMethod]
    public async Task ACopyOfAnotherSongIsNotLoadedWhenTheSongChangedMeanwhile()
    {
        var player = new FakePlayer();
        player.Unreadable("/m/e.ogg");
        var harness = PlaybackHarness.Playing(player);
        var making = new Gate();
        harness.Core.Queue("playable", "\"ok\": true, \"path\": \"/c/e.flac\"", making.Opened);
        harness.Core.Emit(PlaybackHarness.PlayingResult(1, song: "/m/e.ogg"));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Count("playable") == 1));
        harness.Core.Emit(PlaybackHarness.PlayingResult(2, song: "/m/f.flac", bars: SongBars.Take(3).ToList()));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Bars.Count == 3)); // the other song is shown
        making.Release();
        Assert.IsTrue(await harness.Settled(() => !harness.Playback.Starting));
        Assert.IsEmpty(player.Loads);
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
    }

    [TestMethod]
    public async Task AnAnswerForASongThatIsGoneIsNotUsedAndNothingMoreIsAskedForIt()
    {
        var harness = await Ready(new FakePlayer());
        var waiting = new Gate();
        var afterwards = new Gate();
        harness.Core.Queue("step", "\"ok\": true, \"seconds\": 2.0", waiting.Opened);
        harness.Core.Queue("step", "\"ok\": true, \"seconds\": 3.0", afterwards.Opened);
        harness.Ui(() =>
        {
            harness.Playback.NextBar();
            harness.Playback.NextBar(); // waits for the first one
        });
        Assert.IsTrue(await harness.Settled(() => harness.Count("step") == 1));
        harness.Core.Emit(PlaybackHarness.PlayingResult(2, song: "/m/f.flac", bars: SongBars.Take(3).ToList()));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Bars.Count == 3));
        waiting.Release();
        harness.Ui(harness.Playback.NextBar); // of the new song: asked only when both older ones are done with
        Assert.IsTrue(await harness.Settled(() => harness.Count("step") == 2));
        Assert.AreEqual(0, harness.Read(() => harness.Playback.Position));
        afterwards.Release();
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Position == 3));
    }

    [TestMethod]
    public async Task TheControlsDoNothingOnceTheCoreHasStopped()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        harness.Core.Stop(new CoreEnd(CoreEndReason.Exited, 9, "", []));
        Assert.IsTrue(await harness.Settled(() => harness.Model.Phase == Phase.Stopped));
        var asked = harness.Core.All.Count;
        harness.Ui(() =>
        {
            harness.Playback.SetHear(Hear.Song);
            harness.Playback.SetSongVolume(0.2);
            harness.Playback.Toggle();
        });
        await harness.Quiet();
        Assert.AreEqual(Hear.Song, harness.Read(() => harness.Playback.Hear));
        Assert.AreEqual(asked, harness.Core.All.Count);
        Assert.IsEmpty(player.Loads);
    }

    [TestMethod]
    public async Task ASliderMovedBeforeTheStoredVolumesCameIsKept()
    {
        var harness = new PlaybackHarness(new FakePlayer());
        harness.Preset("volumes", PlaybackHarness.GainsReply);
        var stored = new Gate();
        harness.Preset("settings", PlaybackHarness.SettingsReply, stored);
        harness.Ui(harness.Model.Launch);
        harness.Ui(() => harness.Playback.SetSongVolume(0.2));
        stored.Release();
        await harness.Quiet(); // the stored volumes are in
        Assert.IsTrue(await harness.Settled(() => harness.Core.Asked("settings").Count == 2));
        Assert.AreEqual(0.2, harness.Read(() => harness.Playback.SongVolume));
        Assert.AreEqual(1.0, harness.Read(() => harness.Playback.HitsVolume));
    }

    [TestMethod]
    public async Task ASettingsAnswerForAReplacedCoreIsDropped()
    {
        var harness = new PlaybackHarness(new FakePlayer());
        var stored = new Gate();
        harness.Preset("settings", PlaybackHarness.SettingsReply, stored);
        harness.Ui(harness.Model.Launch);
        harness.Ui(harness.Model.StartAgain); // the first core's answer is late
        stored.Release();
        await harness.Quiet();
        Assert.IsTrue(await harness.Settled(() => harness.Playback.SongVolume == 0.4));
        harness.Ui(() => harness.Playback.SetSongVolume(0.6));
        Assert.AreEqual(0.6, harness.Read(() => harness.Playback.SongVolume));
    }

    // what the review of the Windows player found

    [TestMethod]
    public async Task ASeekThatCannotReopenTheDeviceTellsWhyAndStopsPlayingButPlayWorksAgain()
    {
        var player = new FakePlayer();
        var ticker = new ManualTicker();
        var harness = PlaybackHarness.Playing(player, ticker.Start);
        harness.Core.Emit(PlaybackHarness.PlayingResult(1));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        player.Position = 4;
        harness.Ui(harness.Playback.Toggle);
        harness.Ui(harness.Playback.Toggle); // paused at 4 and playing again
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));

        player.FailToSeek(new PlayerFailedException("No sound device."));
        harness.Ui(() => harness.Playback.Seek(9));

        Assert.AreEqual("No sound device.", harness.Read(() => harness.Model.Notice?.Text));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.AreEqual(0, ticker.Live);
        Assert.AreEqual(4, harness.Read(() => harness.Playback.Position));

        player.FailToSeek(null);
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual(4, player.Seeks[^1]);
    }

    [TestMethod]
    public async Task AnArrowWhoseSeekFailsDoesNotBlockTheNextOne()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        player.FailToSeek(new PlayerFailedException("No sound device."));
        harness.Core.Answer("step", "\"ok\": true, \"seconds\": 8.0");
        harness.Ui(harness.Playback.NextBar);
        Assert.IsTrue(await harness.Settled(() => harness.Model.Notice?.Text == "No sound device."));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));

        player.FailToSeek(null);
        harness.Core.Answer("step", "\"ok\": true, \"seconds\": 3.0");
        harness.Ui(harness.Playback.NextBar);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Position == 3));
        Assert.AreEqual(2, harness.Count("step"));
    }

    [TestMethod]
    public async Task AJobThatFailsDoesNotStopTheOnesAfterIt()
    {
        var player = new FakePlayer();
        var harness = PlaybackHarness.Playing(player, new ManualTicker().Start); // no ticks reading the position
        harness.Core.Emit(PlaybackHarness.PlayingResult(1));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        player.FailToTellPosition(true);
        harness.Ui(harness.Playback.NextBar); // asks from a position that cannot be read
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => harness.Read(() => harness.Playback.Idle));
        player.FailToTellPosition(false);
        harness.Core.Answer("step", "\"ok\": true, \"seconds\": 4.0");
        harness.Ui(harness.Playback.NextBar);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Position == 4));

        var lane = new PlaybackModel.Lane();
        var ran = new List<string>();
        var failing = lane.Run(() => throw new InvalidOperationException("broken"));
        var after = lane.Run(() =>
        {
            ran.Add("after");
            return Task.CompletedTask;
        });
        await after;
        Assert.AreEqual("after", Assert.ContainsSingle(ran));
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => failing);
    }

    [TestMethod]
    public async Task ASliderMovedWhileAPlayWaitsForTheGainsKeepsTheNewestGains()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        var first = new Gate();
        harness.Core.Queue("volumes", PlaybackHarness.GainsReply, first.Opened);
        harness.Core.Queue("volumes", "\"ok\": true, \"song\": 0.3, \"hits\": 1.0");
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Count("volumes") == 1));
        harness.Ui(() => harness.Playback.SetSongVolume(0.3)); // while the play waits
        first.Release();
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        await harness.Quiet();
        Assert.AreEqual(new Gains(0.3, 1.0), player.GainsSet[^1]);
        Assert.DoesNotContain(new Gains(0.7, 1.0), player.GainsSet);
    }

    [TestMethod]
    public async Task ALateEndedAfterASeekDoesNotMakeTheNextPlayStartAtTheBeginning()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        harness.Ui(() =>
        {
            player.Pauses(PlayerPause.Ended); // the device stopped just before ...
            harness.Playback.Seek(5); // ... the reader's seek, in the same turn
        });
        harness.Flush();
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.AreEqual(5, harness.Read(() => harness.Playback.Position));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual(5, player.Seeks[^1]);
    }

    [TestMethod]
    public async Task AnEndedThatReachedTheSongsEndStillStartsAgainAtTheBeginning()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        player.Position = 11.9; // the device's own position is a little short of the length
        player.Pauses(PlayerPause.Ended);
        harness.Flush();
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual(0, player.Seeks[^1]);
    }

    [TestMethod]
    public async Task APauseTheOldSongCausedDoesNotTouchTheNextOne()
    {
        var player = new FakePlayer();
        var harness = await Started(player);
        harness.Ui(() =>
        {
            harness.Core.Emit(PlaybackHarness.PlayingResult(2, song: "/m/other.flac"));
            player.Pauses(PlayerPause.Ended); // told after the song was changed
        });
        harness.Flush();
        Assert.IsTrue(await harness.Settled(() => harness.Playback.CanPlay));
        harness.Ui(() => harness.Playback.Seek(5));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual("/m/other.flac", player.Loads[^1].Song);
        Assert.AreEqual(5, player.Seeks[^1]);
    }

    [TestMethod]
    public void TheDefaultTickerCallsBackEveryInterval()
    {
        var ticks = new List<string>();
        var ticker = PlaybackModel.Every(TimeSpan.FromMilliseconds(5), work => work());
        using var handle = ticker(() =>
        {
            lock (ticks)
            {
                ticks.Add("tick");
            }
        });
        Assert.IsTrue(SpinWait.SpinUntil(() =>
        {
            lock (ticks)
            {
                return ticks.Count >= 2;
            }
        }, TimeSpan.FromSeconds(10)));
    }
}
