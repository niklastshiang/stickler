using NAudio.Wave;

namespace Stickler.Audio;

/// <summary><see cref="ISeekableSamples"/> over a NAudio <see cref="WaveStream"/> (WAV, AIFF); owns it.</summary>
public sealed class WaveStreamSamples : ISeekableSamples
{
    private static readonly string[] AiffExtensions = [".aif", ".aiff", ".aifc"];

    private readonly WaveStream stream;
    private readonly ISampleProvider samples;

    public WaveStreamSamples(WaveStream stream)
    {
        this.stream = stream;
        samples = stream.ToSampleProvider();
        Frames = stream.Length / stream.WaveFormat.BlockAlign;
    }

    public WaveFormat WaveFormat => samples.WaveFormat;

    public long Frames { get; }

    /// <summary>Opens a WAV or AIFF file (by its extension).</summary>
    public static WaveStreamSamples Open(string path) =>
        new(AiffExtensions.Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase)
            ? new AiffFileReader(path)
            : new WaveFileReader(path));

    public int Read(Span<float> buffer) => samples.Read(buffer);

    // The readers round Position down to a whole block, so a frame times BlockAlign is exact.
    public void Seek(long frame) =>
        stream.Position = Math.Clamp(frame, 0, Frames) * stream.WaveFormat.BlockAlign;

    public void Dispose() => stream.Dispose();
}
