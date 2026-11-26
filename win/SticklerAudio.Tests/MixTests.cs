using NAudio.Wave;

namespace Stickler.Audio.Tests;

[TestClass]
public sealed class MixTests
{
    private const float Song = 0.25f;
    private string folder = "";

    [TestInitialize]
    public void MakeFolder()
    {
        folder = Path.Combine(Path.GetTempPath(), "stickler-audio-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
    }

    [TestCleanup]
    public void RemoveFolder() => Directory.Delete(folder, recursive: true);

    [TestMethod]
    public void AnImpulseOfTheClicksAppearsAtItsExactFrame()
    {
        using Mix mix = MakeMix(rate: 1000, channels: 2, frames: 1000, impulses: [300, 700]);

        float[] all = ReadAll(mix);

        Assert.AreEqual(2000, all.Length);
        Assert.AreEqual(2, mix.WaveFormat.Channels);
        Assert.AreEqual(WaveFormatEncoding.IeeeFloat, mix.WaveFormat.Encoding);
        AssertImpulsesAt(all, 2, [300, 700]);
        Assert.AreEqual(Song + 1, all[600]);
        Assert.AreEqual(Song + 1, all[601]);
    }

    [TestMethod]
    public void BothSourcesLandOnTheTargetFrameAfterASeek()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300, 700]);

        mix.Seek(0.5);
        AssertImpulsesAt(ReadAll(mix), 2, [200]);

        mix.Seek(0.3);
        AssertImpulsesAt(ReadAll(mix), 2, [0, 400]);
    }

    [TestMethod]
    public void ASeekBackwardsAfterReadingOnLandsOnTheTargetToo()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300, 700]);
        _ = mix.Read(new float[1600]);

        mix.Seek(0.2);

        Assert.AreEqual(0.2, mix.Position, 1e-9);
        AssertImpulsesAt(ReadAll(mix), 2, [100, 500]);
    }

    [TestMethod]
    public void AGainOfZeroLeavesExactlyTheOtherSource()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300]);

        mix.SetGains(0, 1);
        float[] hitsOnly = ReadAll(mix);
        mix.Seek(0);
        mix.SetGains(1, 0);
        float[] songOnly = ReadAll(mix);

        Assert.AreEqual(1f, hitsOnly[600]);
        Assert.AreEqual(1, hitsOnly.Count(x => x != 0) / 2);
        Assert.IsTrue(songOnly.All(x => x == Song));
    }

    [TestMethod]
    public void ClicksMuteStaysInSyncWhenTheyComeBack()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300, 700]);
        mix.SetGains(1, 0);
        _ = mix.Read(new float[1000]); // 500 frames, hits silent

        mix.SetGains(1, 1);

        AssertImpulsesAt(ReadAll(mix), 2, [200]);
    }

    [TestMethod]
    public void GainChangesApplyToTheNextRead()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [100, 300], songLevel: 1f);
        float[] first = new float[400];
        float[] second = new float[400];

        _ = mix.Read(first); // frames 0..199: the impulse at 100 at full gain
        mix.SetGains(0.5f, 0.25f);
        _ = mix.Read(second); // frames 200..399: the impulse at 300 (offset 100)

        Assert.AreEqual(2f, first[200]);
        Assert.AreEqual(1f, first[0]);
        Assert.AreEqual(0.5f + 0.25f, second[200]);
        Assert.AreEqual(0.5f, second[0]);
    }

    [TestMethod]
    public void GainsAreKeptInsideZeroAndOne()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [0], songLevel: 1f);

        mix.SetGains(7, float.NaN);
        float[] loud = new float[2];
        _ = mix.Read(loud);
        mix.Seek(0);
        mix.SetGains(-3, 3);
        float[] other = new float[2];
        _ = mix.Read(other);

        Assert.AreEqual(1f, loud[0]);
        Assert.AreEqual(1f, other[0]);
    }

    [TestMethod]
    public void ClicksAtAnotherRateAndChannelCountLineUpWithinOneFrame()
    {
        // Clicks: mono at 4000 Hz, an impulse at 1000 = 0.25 s; the song is stereo at 8000 Hz.
        using Mix mix = MakeMix(8000, 2, 8000, songFile: 0, clicksRate: 4000, clicksChannels: 1, clicksFrames: 4000, impulses: [1000]);

        float[] all = ReadAll(mix);

        AssertPeakNear(all, 2, 0, 2000);
        AssertPeakNear(all, 2, 1, 2000); // mono clicks reach both channels
    }

    [TestMethod]
    public void ClicksAtAHigherRateAndStereoAreMixedDownToAMonoSong()
    {
        using Mix mix = MakeMix(4000, 1, 4000, songFile: 0, clicksRate: 8000, clicksChannels: 2, clicksFrames: 8000, impulses: [2000]);

        AssertPeakNear(ReadAll(mix), 1, 0, 1000);
    }

    [TestMethod]
    public void ResampledClicksStillLineUpAfterASeekInEitherDirection()
    {
        using Mix mix = MakeMix(8000, 2, 8000, songFile: 0, clicksRate: 4000, clicksChannels: 1, clicksFrames: 4000, impulses: [1000, 3000]);
        _ = mix.Read(new float[2 * 7000]);

        mix.Seek(0.125); // song frame 1000
        float[] from = ReadAll(mix);
        mix.Seek(0.5); // song frame 4000
        float[] later = ReadAll(mix);

        AssertPeakNear(from, 2, 0, 1000);
        AssertPeakNear(later, 2, 0, 2000);
    }

    [TestMethod]
    public void ClicksShorterThanTheSongArePaddedWithSilence()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300], clicksFrames: 500);

        float[] all = ReadAll(mix);

        Assert.AreEqual(2000, all.Length);
        AssertImpulsesAt(all, 2, [300]);
    }

    [TestMethod]
    public void ClicksLongerThanTheSongAreCutAtTheSongsEnd()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300, 1500], clicksFrames: 2000);

        float[] all = ReadAll(mix);

        Assert.AreEqual(2000, all.Length);
        AssertImpulsesAt(all, 2, [300]);
        Assert.AreEqual(0, mix.Read(new float[10]));
    }

    [TestMethod]
    public void WithoutClicksTheSongPlaysAlone()
    {
        string songPath = WriteWav("song.wav", 1000, 2, Constant(1000, 2));
        using Mix mix = new(WaveStreamSamples.Open(songPath), null);

        mix.SetGains(1, 1);
        float[] all = ReadAll(mix);
        mix.Seek(0.5);

        Assert.IsTrue(all.All(x => x == Song));
        Assert.AreEqual(2000, all.Length);
        Assert.AreEqual(0.5, mix.Position, 1e-9);
    }

    [TestMethod]
    public void ABufferThatIsNotWholeFramesGetsWholeFramesOnly()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [1]);
        float[] odd = [-9, -9, -9, -9, -9];

        int count = mix.Read(odd);

        Assert.AreEqual(4, count);
        Assert.AreEqual(Song, odd[0]);
        Assert.AreEqual(Song + 1, odd[2]);
        Assert.AreEqual(Song + 1, odd[3]);
        Assert.AreEqual(-9f, odd[4]); // the half frame is left alone
        Assert.AreEqual(0.002, mix.Position, 1e-9);
    }

    [TestMethod]
    public void ABufferShorterThanAFrameReadsNothingAndEndsNothing()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [2]);
        int ended = 0;
        mix.Ended += () => ended++;

        Assert.AreEqual(0, mix.Read(new float[1]));
        Assert.AreEqual(0, mix.Read(Span<float>.Empty));

        Assert.AreEqual(0, ended);
        Assert.AreEqual(0.0, mix.Position);
        Assert.AreEqual(2000, ReadAll(mix).Length);
    }

    [TestMethod]
    public void TheEndReturnsZeroAndRaisesEndedOncePerRun()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300]);
        int ended = 0;
        mix.Ended += () => ended++;
        float[] buffer = new float[600];

        Assert.AreEqual(600, mix.Read(buffer));
        Assert.AreEqual(600, mix.Read(buffer));
        Assert.AreEqual(600, mix.Read(buffer));
        Assert.AreEqual(200, mix.Read(buffer));
        Assert.AreEqual(0, ended);
        Assert.AreEqual(0, mix.Read(buffer));
        Assert.AreEqual(0, mix.Read(buffer));
        Assert.AreEqual(1, ended);

        mix.Seek(0.9);
        Assert.AreEqual(200, mix.Read(buffer));
        Assert.AreEqual(0, mix.Read(buffer));
        Assert.AreEqual(0, mix.Read(buffer));
        Assert.AreEqual(2, ended);
    }

    [TestMethod]
    public void AHandlerOfEndedMayRestartTheSong()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [300]);
        int ended = 0;
        mix.Ended += () =>
        {
            ended++;
            mix.Seek(0);
        };
        float[] buffer = new float[2000];

        Assert.AreEqual(2000, mix.Read(buffer));
        Assert.AreEqual(0, mix.Read(buffer));
        Assert.AreEqual(2000, mix.Read(buffer));

        Assert.AreEqual(1, ended);
    }

    [TestMethod]
    public void PositionAndLengthAreInSecondsAndPositionNeverPassesTheLength()
    {
        using Mix mix = MakeMix(1000, 2, 1500, [300]);
        Assert.AreEqual(1.5, mix.Length, 1e-9);
        Assert.AreEqual(0.0, mix.Position);

        _ = mix.Read(new float[800]);
        Assert.AreEqual(0.4, mix.Position, 1e-9);
        mix.Seek(0.25);
        _ = mix.Read(new float[200]);
        Assert.AreEqual(0.35, mix.Position, 1e-9);
        _ = ReadAll(mix);

        Assert.AreEqual(1.5, mix.Position, 1e-9);
    }

    [TestMethod]
    public void ASeekBeyondTheEndOrBeforeZeroIsClamped()
    {
        using Mix mix = MakeMix(1000, 2, 1000, [0]);
        int ended = 0;
        mix.Ended += () => ended++;

        mix.Seek(99);
        Assert.AreEqual(1.0, mix.Position, 1e-9);
        Assert.AreEqual(0, mix.Read(new float[10]));
        Assert.AreEqual(1, ended);

        mix.Seek(-4);
        Assert.AreEqual(0.0, mix.Position);
        float[] start = new float[2];
        Assert.AreEqual(2, mix.Read(start));
        Assert.AreEqual(Song + 1, start[0]);
    }

    [TestMethod]
    public void AnEarlyEndOfTheSongsSourceEndsTheRun()
    {
        var song = new FakeSamples(1000, 1, Enumerable.Repeat(0.5f, 600).ToArray()) { ClaimedFrames = 1000 };
        using Mix mix = new(song, null);
        int ended = 0;
        mix.Ended += () => ended++;

        Assert.AreEqual(600, mix.Read(new float[1000]));
        Assert.AreEqual(0, mix.Read(new float[1000]));

        Assert.AreEqual(1, ended);
    }

    [TestMethod]
    public void SourcesThatGiveLessThanAskedAreReadUntilTheBufferIsFull()
    {
        float[] ramp = Enumerable.Range(0, 100).Select(i => i / 100f).ToArray();
        float[] hits = Enumerable.Range(0, 100).Select(i => i / 1000f).ToArray();
        using Mix mix = new(new FakeSamples(1000, 1, ramp) { PerRead = 7 }, new FakeSamples(1000, 1, hits) { PerRead = 3 });

        float[] all = ReadAll(mix);

        Assert.AreEqual(100, all.Length);
        for (int i = 0; i < 100; i++)
        {
            Assert.AreEqual((i / 100f) + (i / 1000f), all[i], 1e-6);
        }
    }

    [TestMethod]
    public void ClicksWithAChannelCountThatCannotBeMixedAreRefused()
    {
        var song = new FakeSamples(1000, 2, new float[20]);
        var clicks = new FakeSamples(1000, 3, new float[30]);

        Assert.ThrowsExactly<NotSupportedException>(() => new Mix(song, clicks));
    }

    [TestMethod]
    public void DisposeClosesBothFilesAndStopsTheMix()
    {
        string songPath = WriteWav("song.wav", 1000, 2, Constant(1000, 2));
        string clicksPath = WriteWav("clicks.wav", 1000, 2, Impulses(1000, 2, [5]));
        Mix mix = new(WaveStreamSamples.Open(songPath), WaveStreamSamples.Open(clicksPath));
        Assert.ThrowsExactly<IOException>(() => new FileStream(songPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None).Dispose());

        mix.Dispose();

        using (new FileStream(songPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        using (new FileStream(clicksPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
        }

        File.Delete(songPath);
        File.Delete(clicksPath);
        Assert.ThrowsExactly<ObjectDisposedException>(() => mix.Read(new float[4]));
        Assert.ThrowsExactly<ObjectDisposedException>(() => mix.Seek(0));
    }

    [TestMethod]
    public void SeekAndSetGainsFromAnotherThreadNeverBreakARunningRead()
    {
        using Mix mix = MakeMix(8000, 2, 8000, [100, 4000], clicksRate: 4000, clicksChannels: 1, clicksFrames: 4000);
        using CancellationTokenSource stop = new(TimeSpan.FromMilliseconds(200));
        Exception? failure = null;
        int reads = 0;

        Task reader = Task.Run(() =>
        {
            try
            {
                float[] buffer = new float[511];
                while (!stop.IsCancellationRequested)
                {
                    int count = mix.Read(buffer);
                    reads++;
                    Assert.IsTrue(buffer.Take(count).All(x => float.IsFinite(x) && Math.Abs(x) <= 3));
                    if (count == 0)
                    {
                        mix.Seek(0);
                    }
                }
            }
            catch (Exception e)
            {
                failure = e;
            }
        });
        Random random = new(1);
        while (!stop.IsCancellationRequested)
        {
            mix.Seek(random.NextDouble() * 1.2);
            mix.SetGains((float)random.NextDouble(), (float)random.NextDouble());
            _ = mix.Position;
        }

        reader.Wait();

        Assert.IsNull(failure, failure?.ToString());
        Assert.IsTrue(reads > 10);
    }

    [TestMethod]
    public void AnAiffFileOpensToo()
    {
        string path = Path.Combine(folder, "song.AIF");
        using (AiffFileWriter writer = new(path, new WaveFormat(1000, 16, 1)))
        {
            writer.WriteSamples(Enumerable.Repeat((short)8192, 500).ToArray(), 0, 500);
        }

        using WaveStreamSamples samples = WaveStreamSamples.Open(path);
        samples.Seek(100);
        float[] buffer = new float[4];

        Assert.AreEqual(500, samples.Frames);
        Assert.AreEqual(4, samples.Read(buffer));
        Assert.AreEqual(Song, buffer[0], 1e-4);
        samples.Seek(10_000);
        Assert.AreEqual(0, samples.Read(buffer));
    }

    // A song of constant Song (or songLevel) and clicks that are single impulses of 1.0, as files.
    private Mix MakeMix(
        int rate,
        int channels,
        int frames,
        int[] impulses,
        int? clicksRate = null,
        int? clicksChannels = null,
        int? clicksFrames = null,
        float songLevel = Song,
        float? songFile = null)
    {
        float level = songFile ?? songLevel;
        string songPath = WriteWav("song.wav", rate, channels, Constant(frames, channels, level));
        string clicksPath = WriteWav("clicks.wav", clicksRate ?? rate, clicksChannels ?? channels, Impulses(clicksFrames ?? frames, clicksChannels ?? channels, impulses));
        return new Mix(WaveStreamSamples.Open(songPath), WaveStreamSamples.Open(clicksPath));
    }

    private string WriteWav(string name, int rate, int channels, float[] samples)
    {
        string path = Path.Combine(folder, name);
        using WaveFileWriter writer = new(path, WaveFormat.CreateIeeeFloatWaveFormat(rate, channels));
        writer.WriteSamples(samples, 0, samples.Length);
        return path;
    }

    private static float[] Constant(int frames, int channels, float level = Song) =>
        Enumerable.Repeat(level, frames * channels).ToArray();

    private static float[] Impulses(int frames, int channels, int[] at)
    {
        float[] samples = new float[frames * channels];
        foreach (int frame in at.Where(f => f < frames))
        {
            for (int c = 0; c < channels; c++)
            {
                samples[(frame * channels) + c] = 1f;
            }
        }

        return samples;
    }

    private static float[] ReadAll(Mix mix)
    {
        List<float> all = [];
        float[] buffer = new float[256 * mix.WaveFormat.Channels];
        int count;
        while ((count = mix.Read(buffer)) > 0)
        {
            all.AddRange(buffer.Take(count));
        }

        return [.. all];
    }

    // The frames where the first channel is above the song's level, which must be exactly `at`.
    private static void AssertImpulsesAt(float[] samples, int channels, int[] at)
    {
        int[] found = [.. Enumerable.Range(0, samples.Length / channels).Where(f => samples[f * channels] != Song && samples[f * channels] != Song + 1)];
        Assert.AreEqual(0, found.Length, "samples other than the song's or an impulse's");
        int[] impulses = [.. Enumerable.Range(0, samples.Length / channels).Where(f => samples[f * channels] > Song + 0.5f)];
        CollectionAssert.AreEqual(at, impulses);
    }

    private static void AssertPeakNear(float[] samples, int channels, int channel, int frame)
    {
        int peak = Enumerable.Range(0, samples.Length / channels)
            .MaxBy(f => Math.Abs(samples[(f * channels) + channel]));
        Assert.IsTrue(Math.Abs(peak - frame) <= 1, $"the clicks' peak is at {peak}, expected {frame}");
    }

    // Plays `data` once; ClaimedFrames and PerRead bend what it tells and gives.
    private sealed class FakeSamples(int rate, int channels, float[] data) : ISeekableSamples
    {
        private int next;

        public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat(rate, channels);

        public long? ClaimedFrames { get; init; }

        public int PerRead { get; init; } = int.MaxValue;

        public long Frames => ClaimedFrames ?? data.Length / channels;

        public int Read(Span<float> buffer)
        {
            int count = Math.Min(Math.Min(buffer.Length, PerRead), data.Length - next);
            data.AsSpan(next, count).CopyTo(buffer);
            next += count;
            return count;
        }

        public void Seek(long frame) => next = (int)(frame * channels);

        public void Dispose()
        {
        }
    }
}
