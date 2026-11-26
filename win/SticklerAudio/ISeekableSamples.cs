using NAudio.Wave;

namespace Stickler.Audio;

/// <summary>A source of float samples that can jump to a frame. The app wraps Media Foundation's
/// reader behind it; <see cref="WaveStreamSamples"/> does it for NAudio's own file readers, so
/// the mixer is tested without Windows. A frame is one sample per channel.</summary>
public interface ISeekableSamples : ISampleProvider, IDisposable
{
    /// <summary>The length in frames.</summary>
    long Frames { get; }

    /// <summary>Makes the next <c>Read</c> start at <paramref name="frame"/> (clamped into 0..<see cref="Frames"/>).</summary>
    void Seek(long frame);
}
