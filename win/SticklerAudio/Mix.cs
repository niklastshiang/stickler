using NAudio.Wave;
using NAudio.Wave.SampleProviders;

namespace Stickler.Audio;

/// <summary>The song and the clicks mixed in one pull (SPEC.md, module <c>win-playback</c>): both
/// are read for the same frames under one lock, so they cannot drift apart, as the Mac's
/// <c>AVAudioEngine</c> keeps them on one clock. The output has the song's rate and channels.
/// <c>Read</c> runs on the audio thread, everything else on the window's.</summary>
public sealed class Mix : ISampleProvider, IDisposable
{
    private readonly object gate = new();
    private readonly ISeekableSamples song;
    private readonly ISeekableSamples? clicks;
    private readonly int rate;
    private readonly int channels;
    private readonly int resamplerDelay; // output frames the resampler adds, found by trying it
    private ISampleProvider? clicksChain; // clicks in the song's rate and channels; rebuilt on every seek
    private float[] scratch = [];
    private long frame; // the next frame to play, in the song's frames
    private bool exhausted; // the song's source came up short
    private bool ended; // Ended was raised for this run
    private bool disposed;
    private float songGain = 1;
    private float hitsGain = 1;

    /// <summary><paramref name="clicks"/> may be missing: the song plays alone. The mix owns both sources.</summary>
    public Mix(ISeekableSamples song, ISeekableSamples? clicks)
    {
        this.song = song;
        this.clicks = clicks;
        rate = song.WaveFormat.SampleRate;
        channels = song.WaveFormat.Channels;
        WaveFormat = WaveFormat.CreateIeeeFloatWaveFormat(rate, channels);
        if (clicks is not null)
        {
            resamplerDelay = ResamplerDelay(clicks.WaveFormat.SampleRate, rate);
            clicksChain = Convert(clicks); // an unsupported layout is refused here, not on the audio thread
        }
    }

    /// <summary>Raised once per run to the song's end, after the last <c>Read</c> that returned 0
    /// (on the audio thread, outside the lock); a seek starts a new run.</summary>
    public event Action? Ended;

    public WaveFormat WaveFormat { get; }

    /// <summary>The song's length in seconds.</summary>
    public double Length => (double)song.Frames / rate;

    /// <summary>Where the next sample comes from, in seconds: the seek target plus what was read.</summary>
    public double Position
    {
        get
        {
            lock (gate)
            {
                return (double)Math.Min(frame, song.Frames) / rate;
            }
        }
    }

    /// <summary>Fills <paramref name="buffer"/> with whole frames (a rest shorter than a frame is left
    /// alone); 0 at the song's end, and from then on. A buffer shorter than a frame also gives 0 but
    /// does not end the run.</summary>
    public int Read(Span<float> buffer)
    {
        int count;
        bool raise = false;
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            int wanted = buffer.Length / channels;
            if (wanted == 0)
            {
                return 0;
            }

            wanted = (int)Math.Min(wanted, song.Frames - frame);
            int got = wanted > 0 && !exhausted ? Fill(song, buffer, wanted) : 0;
            exhausted |= got < wanted;
            count = got * channels;
            if (got == 0 && !ended)
            {
                ended = raise = true;
            }
            else if (got > 0)
            {
                Scale(buffer[..count], songGain);
                AddClicks(buffer[..count], got);
                frame += got;
            }
        }

        if (raise)
        {
            Ended?.Invoke();
        }

        return count;
    }

    /// <summary>Moves both sources to <paramref name="seconds"/> (clamped into the song) for the next <c>Read</c>.</summary>
    public void Seek(double seconds)
    {
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            frame = (long)Math.Clamp(Math.Round(seconds * rate), 0, song.Frames);
            exhausted = ended = false;
            song.Seek(frame);
            if (clicks is not null)
            {
                // Same instant at the clicks' own rate; a fresh chain forgets the resampler's history.
                clicks.Seek((long)Math.Round(frame * (double)clicks.WaveFormat.SampleRate / rate));
                clicksChain = Convert(clicks);
            }
        }
    }

    /// <summary>Volumes 0..1 from the next <c>Read</c>; 0 is silence, not a quiet signal.</summary>
    public void SetGains(float song, float hits)
    {
        lock (gate)
        {
            songGain = Normalise(song);
            hitsGain = Normalise(hits);
        }
    }

    public void Dispose()
    {
        lock (gate)
        {
            disposed = true;
            song.Dispose();
            clicks?.Dispose();
        }
    }

    // NaN counts as 0 (the comparison fails).
    private static float Normalise(float gain) => gain > 0 ? Math.Min(gain, 1) : 0;

    private static void Scale(Span<float> samples, float gain)
    {
        if (gain != 1)
        {
            foreach (ref float sample in samples)
            {
                sample *= gain;
            }
        }
    }

    // Sources may return less than asked without being at their end; only 0 says that.
    private int Fill(ISampleProvider source, Span<float> buffer, int frames)
    {
        int total = frames * channels;
        int have = 0;
        while (have < total)
        {
            int read = source.Read(buffer[have..total]);
            if (read == 0)
            {
                break;
            }

            have += read;
        }

        return have / channels;
    }

    private void AddClicks(Span<float> mixed, int frames)
    {
        if (clicksChain is null)
        {
            return;
        }

        // Read even at gain 0: a skipped chain would fall behind the song.

        if (scratch.Length < mixed.Length)
        {
            scratch = new float[mixed.Length];
        }

        Span<float> hits = scratch.AsSpan(0, mixed.Length);
        int read = Fill(clicksChain, hits, frames) * channels;
        hits[read..].Clear(); // clicks shorter than the song: silence
        for (int i = 0; i < mixed.Length; i++)
        {
            mixed[i] += hits[i] * hitsGain;
        }
    }

    // The clicks' channels first (cheaper at the lower rate), then the song's rate.
    private ISampleProvider Convert(ISampleProvider source)
    {
        ISampleProvider chain = (source.WaveFormat.Channels, channels) switch
        {
            (1, 2) => new MonoToStereoSampleProvider(source),
            (2, 1) => new StereoToMonoSampleProvider(source),
            var (from, to) when from == to => source,
            var (from, to) => throw new NotSupportedException($"Clicks with {from} channels cannot be mixed into {to}."),
        };
        if (chain.WaveFormat.SampleRate == rate)
        {
            return chain;
        }

        // The resampler's filter delays what it gives (about 3 frames at 2x); reading that much
        // and dropping it puts the clicks back on the song's time.
        ISampleProvider resampled = new WdlResamplingSampleProvider(chain, rate);
        Fill(resampled, new float[resamplerDelay * channels], resamplerDelay);
        return resampled;
    }

    // Where a lone impulse comes out of the resampler, compared with where it belongs.
    private static int ResamplerDelay(int from, int to)
    {
        if (from == to)
        {
            return 0;
        }

        const int at = 256;
        float[] impulse = new float[2 * at];
        impulse[at] = 1;
        WdlResamplingSampleProvider resampler = new(new ArraySamples(from, impulse), to);
        float[] output = new float[(int)((long)impulse.Length * to / from)];
        int read = 0;
        int count;
        while ((count = resampler.Read(output.AsSpan(read))) > 0)
        {
            read += count;
        }

        int peak = 0;
        for (int i = 0; i < read; i++)
        {
            peak = Math.Abs(output[i]) > Math.Abs(output[peak]) ? i : peak;
        }

        return Math.Max(0, peak - (int)Math.Round((double)at * to / from));
    }

    private sealed class ArraySamples(int rate, float[] data) : ISampleProvider
    {
        private int next;

        public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat(rate, 1);

        public int Read(Span<float> buffer)
        {
            int count = Math.Min(buffer.Length, data.Length - next);
            data.AsSpan(next, count).CopyTo(buffer);
            next += count;
            return count;
        }
    }
}
