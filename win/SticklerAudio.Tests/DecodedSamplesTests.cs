using NAudio.Wave;

namespace Stickler.Audio.Tests;

[TestClass]
public sealed class DecodedSamplesTests
{
    private string folder = "";

    [TestInitialize]
    public void MakeFolder()
    {
        folder = Path.Combine(Path.GetTempPath(), "stickler-decoded-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
    }

    [TestCleanup]
    public void RemoveFolder() => Directory.Delete(folder, recursive: true);

    [TestMethod]
    public void TheCopyHoldsEverySampleInOrder()
    {
        using DecodedSamples copy = DecodedSamples.Copy(new Counting(rate: 1000, channels: 2, frames: 5000, chunk: 7), folder);

        Assert.AreEqual(5000, copy.Frames);
        Assert.AreEqual(2, copy.WaveFormat.Channels);
        Assert.AreEqual(1000, copy.WaveFormat.SampleRate);
        Assert.AreEqual(WaveFormatEncoding.IeeeFloat, copy.WaveFormat.Encoding);
        float[] all = new float[10001];
        Assert.AreEqual(10000, copy.Read(all));
        for (int i = 0; i < 10000; i++)
        {
            Assert.AreEqual(i, all[i]);
        }

        Assert.AreEqual(0, copy.Read(all));
    }

    [TestMethod]
    public void ASeekLandsOnTheExactFrameForwardsAndBackwards()
    {
        using DecodedSamples copy = DecodedSamples.Copy(new Counting(1000, 2, 5000, chunk: 1024), folder);
        float[] two = new float[2];

        copy.Seek(4321);
        Assert.AreEqual(2, copy.Read(two));
        Assert.AreEqual(8642f, two[0]);

        copy.Seek(17);
        Assert.AreEqual(2, copy.Read(two));
        Assert.AreEqual(34f, two[0]);
        Assert.AreEqual(35f, two[1]);
    }

    [TestMethod]
    public void ASeekIsClampedIntoTheSong()
    {
        using DecodedSamples copy = DecodedSamples.Copy(new Counting(1000, 1, 100, chunk: 64), folder);
        float[] one = new float[1];

        copy.Seek(-5);
        Assert.AreEqual(1, copy.Read(one));
        Assert.AreEqual(0f, one[0]);

        copy.Seek(1000);
        Assert.AreEqual(0, copy.Read(one));
    }

    [TestMethod]
    public void AReadEndsOnAWholeFrame()
    {
        using DecodedSamples copy = DecodedSamples.Copy(new Counting(1000, 2, 10, chunk: 64), folder);

        Assert.AreEqual(6, copy.Read(new float[7]));
    }

    [TestMethod]
    public void TheFileIsGoneAfterDispose()
    {
        DecodedSamples copy = DecodedSamples.Copy(new Counting(1000, 2, 100, chunk: 64), folder);
        Assert.AreEqual(1, Directory.GetFiles(folder).Length);

        copy.Dispose();

        Assert.AreEqual(0, Directory.GetFiles(folder).Length);
    }

    [TestMethod]
    public void ASourceThatFailsLeavesNoFile()
    {
        Assert.ThrowsExactly<InvalidDataException>(() => DecodedSamples.Copy(new Counting(1000, 2, 100, chunk: 64, failAt: 50), folder));

        Assert.AreEqual(0, Directory.GetFiles(folder).Length);
    }

    /// <summary>Sample i has the value i; hands out at most <c>chunk</c> samples per read.</summary>
    private sealed class Counting(int rate, int channels, int frames, int chunk, int failAt = -1) : ISampleProvider
    {
        private int next;

        public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat(rate, channels);

        public int Read(Span<float> buffer)
        {
            if (failAt >= 0 && next >= failAt)
            {
                throw new InvalidDataException("broken");
            }

            int count = Math.Min(Math.Min(buffer.Length, chunk), (frames * channels) - next);
            for (int i = 0; i < count; i++)
            {
                buffer[i] = next++;
            }

            return count;
        }
    }
}
