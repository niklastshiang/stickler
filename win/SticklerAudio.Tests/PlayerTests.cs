using NAudio.Wave;
using Stickler.Core;

namespace Stickler.Audio.Tests;

/// <summary>A mono source at 1000 Hz whose sample at frame i is i + 1, so a pulled value says
/// which frame it came from.</summary>
internal sealed class RampSamples(long frames) : ISeekableSamples
{
    private long next;

    public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat(1000, 1);

    public long Frames { get; } = frames;

    public bool Disposed { get; private set; }

    public int Read(Span<float> buffer)
    {
        int count = (int)Math.Min(buffer.Length, Frames - next);
        for (int i = 0; i < count; i++)
        {
            buffer[i] = next + i + 1;
        }

        next += count;
        return count;
    }

    public void Seek(long frame) => next = Math.Clamp(frame, 0, Frames);

    public void Dispose() => Disposed = true;
}

internal sealed class FakeOutput(ISampleProvider source) : IOutput
{
    public event Action<Exception?>? Stopped;

    public TimeSpan Latency { get; set; }

    public int Played { get; private set; }

    public int Disposals { get; private set; }

    public Exception? PlayFails { get; set; }

    public void Play()
    {
        Played++;
        if (PlayFails is not null)
        {
            throw PlayFails;
        }
    }

    public void Dispose() => Disposals++;

    /// <summary>What a device does: reads <paramref name="frames"/> from its source.</summary>
    public float[] Pull(int frames)
    {
        float[] buffer = new float[frames];
        int got = source.Read(buffer);
        return buffer[..got];
    }

    /// <summary>Raises <c>Stopped</c> on another thread, as a device does.</summary>
    public void Stop(Exception? why) => Task.Run(() => Stopped?.Invoke(why)).Wait();
}

[TestClass]
public sealed class PlayerTests
{
    private const long SongFrames = 2000; // two seconds
    private string folder = "";
    private string clicksPath = "";
    private readonly List<FakeOutput> outputs = [];
    private readonly List<RampSamples> songs = [];
    private readonly List<RampSamples> clicks = [];
    private readonly List<PlayerPause> pauses = [];
    private TimeSpan latency = TimeSpan.FromMilliseconds(100);
    private Exception? factoryFails;
    private Exception? playFails;
    private Exception? songFails;
    private Exception? clicksFail;

    [TestInitialize]
    public void MakeFolder()
    {
        folder = Path.Combine(Path.GetTempPath(), "stickler-player-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        clicksPath = Path.Combine(folder, "clicks.wav");
        File.WriteAllBytes(clicksPath, []);
    }

    [TestCleanup]
    public void RemoveFolder() => Directory.Delete(folder, recursive: true);

    private Player Make()
    {
        Player player = new(
            _ =>
            {
                if (songFails is not null)
                {
                    throw songFails;
                }

                RampSamples song = new(SongFrames);
                songs.Add(song);
                return song;
            },
            _ =>
            {
                if (clicksFail is not null)
                {
                    throw clicksFail;
                }

                RampSamples hits = new(SongFrames);
                clicks.Add(hits);
                return hits;
            },
            source =>
            {
                if (factoryFails is not null)
                {
                    throw factoryFails;
                }

                FakeOutput output = new(source) { Latency = latency, PlayFails = playFails };
                outputs.Add(output);
                return output;
            },
            why => "cannot: " + why.Message);
        player.Paused += pauses.Add;
        return player;
    }

    private Player Loaded()
    {
        Player player = Make();
        player.Load("song.wav", null);
        return player;
    }

    [TestMethod]
    public void LoadOpensTheSongAndTheClicksOnlyWhenTheFileExists()
    {
        using Player player = Make();

        player.Load("song.wav", clicksPath);
        Assert.AreEqual(1, songs.Count);
        Assert.AreEqual(1, clicks.Count);

        player.Load("song.wav", Path.Combine(folder, "missing.wav"));
        Assert.AreEqual(2, songs.Count);
        Assert.AreEqual(1, clicks.Count);

        player.Load("song.wav", null);
        Assert.AreEqual(3, songs.Count);
        Assert.AreEqual(1, clicks.Count);
        Assert.AreEqual(0, outputs.Count, "no output before Play");
    }

    [TestMethod]
    public void ASecondLoadReleasesTheFirstFiles()
    {
        using Player player = Make();
        player.Load("a.wav", clicksPath);

        player.Load("b.wav", clicksPath);

        Assert.IsTrue(songs[0].Disposed);
        Assert.IsTrue(clicks[0].Disposed);
        Assert.IsFalse(songs[1].Disposed);
    }

    [TestMethod]
    public void AnUnreadableSongBecomesUnreadableWithTheCoresWords()
    {
        using Player player = Make();
        songFails = new InvalidOperationException("no codec");

        PlayerUnreadableException thrown = Assert.ThrowsExactly<PlayerUnreadableException>(
            () => player.Load("song.mp3", null));

        Assert.AreEqual("cannot: no codec", thrown.Message);
    }

    [TestMethod]
    public void ClicksThatCannotBeOpenedLeaveTheSongPlayingAlone()
    {
        using Player player = Make();
        clicksFail = new IOException("clicks broken");

        player.Load("song.wav", clicksPath);
        player.Play();

        Assert.IsFalse(songs[0].Disposed);
        Assert.AreEqual(1, outputs.Count);
        Assert.AreEqual(0, clicks.Count);
        Assert.AreEqual(1f, outputs[0].Pull(1)[0]); // the song, no clicks added
    }

    [TestMethod]
    public void ClicksTheMixRefusesAreClosedAndTheSongPlaysAlone()
    {
        SixChannelSamples refused = new();
        Player player = new(
            _ =>
            {
                RampSamples song = new(SongFrames);
                songs.Add(song);
                return song;
            },
            _ => refused,
            source =>
            {
                FakeOutput output = new(source);
                outputs.Add(output);
                return output;
            },
            why => "cannot: " + why.Message);

        player.Load("song.wav", clicksPath);
        player.Play();

        Assert.IsTrue(refused.Disposed);
        Assert.IsFalse(songs[0].Disposed);
        Assert.AreEqual(1f, outputs[0].Pull(1)[0]);
        player.Dispose();
        Assert.IsTrue(songs[0].Disposed);
    }

    [TestMethod]
    public void ASongTheMixCannotUseFailsAndLeavesNoFileOpen()
    {
        BrokenFormatSamples broken = new();
        Player failing = new(_ => broken, _ => new RampSamples(SongFrames), source => new FakeOutput(source), why => "cannot: " + why.Message);

        PlayerFailedException thrown = Assert.ThrowsExactly<PlayerFailedException>(
            () => failing.Load("song.wav", clicksPath));

        Assert.AreEqual("cannot: format broken", thrown.Message);
        Assert.IsTrue(broken.Disposed);
        Assert.AreEqual(0, failing.Position);
    }

    [TestMethod]
    public void PlayMakesExactlyOneOutputAndASecondPlayDoesNothing()
    {
        using Player player = Loaded();

        player.Play();
        player.Play();

        Assert.AreEqual(1, outputs.Count);
        Assert.AreEqual(1, outputs[0].Played);
    }

    [TestMethod]
    public void PlayWithoutASongDoesNothing()
    {
        using Player player = Make();

        player.Play();

        Assert.AreEqual(0, outputs.Count);
        Assert.AreEqual(0, player.Position);
    }

    [TestMethod]
    public void AThrowingFactoryLeavesNothingBehindAndALaterPlayTriesAgain()
    {
        using Player player = Loaded();
        factoryFails = new InvalidOperationException("no device");

        PlayerFailedException thrown = Assert.ThrowsExactly<PlayerFailedException>(player.Play);
        Assert.AreEqual("cannot: no device", thrown.Message);
        Assert.AreEqual(0, outputs.Count);

        factoryFails = null;
        player.Play();
        Assert.AreEqual(1, outputs.Count);
        Assert.AreEqual(1, outputs[0].Played);
    }

    [TestMethod]
    public void AThrowingPlayDisposesTheOutputAndALaterPlayTriesAgain()
    {
        using Player player = Loaded();
        playFails = new InvalidOperationException("device busy");

        PlayerFailedException thrown = Assert.ThrowsExactly<PlayerFailedException>(player.Play);
        Assert.AreEqual("cannot: device busy", thrown.Message);
        Assert.AreEqual(1, outputs[0].Disposals);

        playFails = null;
        player.Play();
        Assert.AreEqual(2, outputs.Count);
        Assert.AreEqual(1, outputs[1].Played);
        Assert.AreEqual(0, outputs[1].Disposals);
    }

    [TestMethod]
    public void WhilePlayingThePositionIsWhatTheDevicePulledLessTheLatency()
    {
        using Player player = Loaded();
        player.Play();

        Assert.AreEqual(0, player.Position, 1e-9, "nothing pulled yet: never before the start");
        _ = outputs[0].Pull(50);
        Assert.AreEqual(0, player.Position, 1e-9, "less than the latency pulled");
        _ = outputs[0].Pull(450);
        Assert.AreEqual(0.4, player.Position, 1e-9);
    }

    [TestMethod]
    public void ThePositionNeverGoesBeforeWhereThisRunBegan()
    {
        using Player player = Loaded();
        player.Seek(1);
        player.Play();

        _ = outputs[0].Pull(50);

        Assert.AreEqual(1, player.Position, 1e-9);
    }

    [TestMethod]
    public void PauseDisposesTheOutputKeepsThePositionAndPlayGoesOnFromThere()
    {
        using Player player = Loaded();
        player.Play();
        _ = outputs[0].Pull(500);

        player.Pause();

        Assert.AreEqual(1, outputs[0].Disposals);
        Assert.AreEqual(0.4, player.Position, 1e-9);
        player.Play();
        Assert.AreEqual(2, outputs.Count);
        Assert.AreEqual(401f, outputs[1].Pull(1)[0], "the frames read ahead are read again");
    }

    [TestMethod]
    public void PauseWithoutAnOutputIsHarmless()
    {
        using Player player = Loaded();

        player.Pause();

        Assert.AreEqual(0, player.Position);
        Assert.AreEqual(0, outputs.Count);
    }

    [TestMethod]
    public void SeekWhilePausedMovesThePositionAndMakesNoOutput()
    {
        using Player player = Loaded();

        player.Seek(1.5);

        Assert.AreEqual(1.5, player.Position, 1e-9);
        Assert.AreEqual(0, outputs.Count);
        player.Play();
        Assert.AreEqual(1501f, outputs[0].Pull(1)[0]);
    }

    [TestMethod]
    public void SeekWhilePlayingPlaysThroughANewOutputFromTheTarget()
    {
        using Player player = Loaded();
        player.Play();
        _ = outputs[0].Pull(500);

        player.Seek(1);

        Assert.AreEqual(1, outputs[0].Disposals);
        Assert.AreEqual(2, outputs.Count);
        Assert.AreEqual(1, outputs[1].Played);
        Assert.AreEqual(1001f, outputs[1].Pull(1)[0]);
        Assert.AreEqual(1, player.Position, 1e-9);
    }

    [TestMethod]
    public void SeekWithoutASongDoesNothing()
    {
        using Player player = Make();

        player.Seek(1);

        Assert.AreEqual(0, player.Position);
        Assert.AreEqual(0, outputs.Count);
    }

    [TestMethod]
    public void GainsSetBeforeLoadApplyToTheSongLoadedLater()
    {
        using Player player = Make();
        player.SetGains(new Gains(0.5, 1));
        player.Load("song.wav", null);
        player.Play();

        Assert.AreEqual(0.5f, outputs[0].Pull(1)[0]);
    }

    [TestMethod]
    public void GainsSetWhilePlayingReachTheMix()
    {
        using Player player = Loaded();
        player.Play();
        Assert.AreEqual(1f, outputs[0].Pull(1)[0]);

        player.SetGains(new Gains(0, 1));

        Assert.AreEqual(0f, outputs[0].Pull(1)[0]);
    }

    [TestMethod]
    public void TheSourceRunningOutEndsThePlayAndTheNextWindowCallDisposesTheOutput()
    {
        using Player player = Loaded();
        player.Play();
        Assert.AreEqual(2000, outputs[0].Pull(5000).Length);
        Assert.AreEqual(0, outputs[0].Pull(10).Length);

        outputs[0].Stop(null);

        CollectionAssert.AreEqual(new[] { PlayerPause.Ended }, pauses);
        Assert.AreEqual(0, outputs[0].Disposals, "never inside the callback");
        Assert.AreEqual(2.0, player.Position, 1e-9);

        player.Seek(0);
        Assert.AreEqual(1, outputs[0].Disposals);
        Assert.AreEqual(1, outputs.Count, "a stopped device is not played again by Seek");
        Assert.AreEqual(0, player.Position);

        player.Play();
        Assert.AreEqual(2, outputs.Count);
        Assert.AreEqual(1f, outputs[1].Pull(1)[0], "from the start again");
        Assert.AreEqual(1, pauses.Count);
    }

    [TestMethod]
    public void AStoppedOutputIsDisposedByPlayPauseAndRelease()
    {
        foreach (Action<Player> call in new Action<Player>[] { p => p.Play(), p => p.Pause(), p => p.Release() })
        {
            outputs.Clear();
            using Player player = Loaded();
            player.Play();
            outputs[0].Stop(null);

            call(player);

            Assert.AreEqual(1, outputs[0].Disposals);
        }
    }

    [TestMethod]
    public void AnInterruptionPausesAndThePositionStaysWhereItWas()
    {
        using Player player = Loaded();
        player.Play();
        _ = outputs[0].Pull(500);

        outputs[0].Stop(new IOException("unplugged"));

        CollectionAssert.AreEqual(new[] { PlayerPause.Interrupted }, pauses);
        Assert.AreEqual(0.4, player.Position, 1e-9);
        Assert.AreEqual(0, outputs[0].Disposals);
    }

    [TestMethod]
    public void AfterAnInterruptionPlayOpensANewOutputAndContinuesWhereItWasHeard()
    {
        using Player player = Loaded();
        player.Play();
        _ = outputs[0].Pull(500);
        outputs[0].Stop(new IOException("unplugged"));

        player.Play();

        Assert.AreEqual(1, outputs[0].Disposals);
        Assert.AreEqual(2, outputs.Count);
        Assert.AreEqual(401f, outputs[1].Pull(1)[0]);
        Assert.AreEqual(0.4, player.Position, 1e-9);
    }

    [TestMethod]
    public void AStopFromAnOutputThePlayerClosedItselfIsIgnored()
    {
        using Player player = Loaded();
        player.Play();
        player.Pause();

        outputs[0].Stop(null);
        outputs[0].Stop(new IOException("late"));

        Assert.AreEqual(0, pauses.Count);
        player.Play();
        outputs[1].Stop(null);
        Assert.AreEqual(1, pauses.Count);
    }

    [TestMethod]
    public void AStopFromTheOldOutputAfterASeekIsIgnored()
    {
        using Player player = Loaded();
        player.Play();
        player.Seek(1);

        outputs[0].Stop(null);

        Assert.AreEqual(0, pauses.Count);
        Assert.AreEqual(1, player.Position, 1e-9);
    }

    [TestMethod]
    public void ReleaseAndDisposeLetGoOfTheOutputAndTheFiles()
    {
        Player player = Loaded();
        player.Play();

        player.Release();

        Assert.AreEqual(1, outputs[0].Disposals);
        Assert.IsTrue(songs[0].Disposed);

        player = Loaded();
        player.Play();
        player.Dispose();
        Assert.AreEqual(1, outputs[1].Disposals);
        Assert.IsTrue(songs[1].Disposed);
    }

    [TestMethod]
    public void MethodsAfterReleaseAreHarmless()
    {
        Player player = Loaded();
        player.Release();

        player.Play();
        player.Pause();
        player.Seek(1);
        player.SetGains(new Gains(1, 1));
        player.Release();

        Assert.AreEqual(0, player.Position);
        Assert.AreEqual(0, outputs.Count);
    }

    private sealed class SixChannelSamples : ISeekableSamples
    {
        public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat(1000, 6);

        public long Frames => 10;

        public int Read(Span<float> buffer) => 0;

        public void Seek(long frame)
        {
        }

        public bool Disposed { get; private set; }

        public void Dispose() => Disposed = true;
    }

    private sealed class BrokenFormatSamples : ISeekableSamples
    {
        public WaveFormat WaveFormat => throw new InvalidOperationException("format broken");

        public long Frames => 10;

        public bool Disposed { get; private set; }

        public int Read(Span<float> buffer) => 0;

        public void Seek(long frame)
        {
        }

        public void Dispose() => Disposed = true;
    }
}
