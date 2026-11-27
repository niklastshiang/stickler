using System.Runtime.InteropServices;
using NAudio.Wave;

namespace Stickler.Audio;

/// <summary>A song decoded once, from its start to its end, into a temporary file of float
/// samples that goes away when this is disposed. A seek is then a file position and exact.
/// The app reads compressed songs (MP3, AAC) this way: Media Foundation's own seek landed one
/// MP3 granule (12 ms) off in some jumps, which is heard against the clicks (SPEC.md, module
/// <c>win-playback</c>, found on 2026-11-27).</summary>
public sealed class DecodedSamples : ISeekableSamples
{
    private readonly FileStream file;
    private readonly int frameBytes;

    private DecodedSamples(FileStream file, WaveFormat format)
    {
        this.file = file;
        WaveFormat = format;
        frameBytes = format.Channels * sizeof(float);
        Frames = file.Length / frameBytes;
    }

    public WaveFormat WaveFormat { get; }

    public long Frames { get; }

    /// <summary>Reads <paramref name="source"/> to its end into a new file in
    /// <paramref name="folder"/>; whatever the source or the disk throws is passed on and leaves
    /// no file.</summary>
    public static DecodedSamples Copy(ISampleProvider source, string folder)
    {
        WaveFormat format = WaveFormat.CreateIeeeFloatWaveFormat(source.WaveFormat.SampleRate, source.WaveFormat.Channels);
        FileStream file = new(
            Path.Combine(folder, "stickler-" + Guid.NewGuid().ToString("N") + ".f32"),
            FileMode.CreateNew,
            FileAccess.ReadWrite,
            FileShare.None,
            bufferSize: 1 << 16,
            FileOptions.DeleteOnClose);
        try
        {
            float[] buffer = new float[format.SampleRate * format.Channels];
            int count;
            while ((count = source.Read(buffer)) > 0)
            {
                file.Write(MemoryMarshal.AsBytes(buffer.AsSpan(0, count)));
            }

            file.Position = 0;
            return new DecodedSamples(file, format);
        }
        catch
        {
            file.Dispose();
            throw;
        }
    }

    public int Read(Span<float> buffer)
    {
        Span<byte> bytes = MemoryMarshal.AsBytes(buffer[..(buffer.Length - (buffer.Length % WaveFormat.Channels))]);
        return file.ReadAtLeast(bytes, bytes.Length, throwOnEndOfStream: false) / sizeof(float);
    }

    public void Seek(long frame) => file.Position = Math.Clamp(frame, 0, Frames) * frameBytes;

    public void Dispose() => file.Dispose();
}
