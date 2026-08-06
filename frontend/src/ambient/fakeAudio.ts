/** A minimal hand-rolled `AudioContext` stub for tests.
 *
 * jsdom has no Web Audio at all, and asserting on rendered sound isn't the
 * point — what matters is that the player *creates* its graph once, *resumes*
 * only from a start, and *suspends* (rather than merely muting) on stop. This
 * records exactly that, plus enough node surface for the graph to build.
 */

export class FakeParam {
  value = 0;
  ramps: Array<{ target: number; at: number }> = [];
  cancelled = 0;
  setValueAtTime(v: number, _at: number): FakeParam {
    this.value = v;
    return this;
  }
  exponentialRampToValueAtTime(v: number, at: number): FakeParam {
    this.ramps.push({ target: v, at });
    return this;
  }
  linearRampToValueAtTime(v: number, at: number): FakeParam {
    this.ramps.push({ target: v, at });
    return this;
  }
  cancelScheduledValues(_at: number): FakeParam {
    this.cancelled++;
    return this;
  }
}

class FakeNode {
  connected: unknown[] = [];
  started = 0;
  stopped = 0;
  connect(dest: unknown): unknown {
    this.connected.push(dest);
    return dest;
  }
  disconnect(): void {}
  start(_when?: number): void {
    this.started++;
  }
  stop(_when?: number): void {
    this.stopped++;
  }
}

class FakeOscillator extends FakeNode {
  type = "sine";
  frequency = new FakeParam();
  detune = new FakeParam();
}

class FakeGain extends FakeNode {
  gain = new FakeParam();
}

class FakeFilter extends FakeNode {
  type = "lowpass";
  frequency = new FakeParam();
  Q = new FakeParam();
}

export class FakeBufferSource extends FakeNode {
  buffer: unknown = null;
  loop = false;
}

class FakeConvolver extends FakeNode {
  buffer: unknown = null;
}

class FakeCompressor extends FakeNode {
  threshold = new FakeParam();
  ratio = new FakeParam();
  knee = new FakeParam();
}

class FakeBuffer {
  channels: Float32Array[];
  constructor(public numberOfChannels: number, public length: number, public sampleRate: number) {
    this.channels = Array.from({ length: numberOfChannels }, () => new Float32Array(length));
  }
  copyToChannel(src: Float32Array, ch: number): void {
    this.channels[ch].set(src.subarray(0, this.channels[ch].length));
  }
  getChannelData(ch: number): Float32Array {
    return this.channels[ch];
  }
}

export class FakeAudioContext {
  sampleRate = 8000; // small, so generated buffers stay cheap in a test run
  currentTime = 0;
  state: "suspended" | "running" | "closed" = "suspended";
  destination = new FakeNode();
  resumes = 0;
  suspends = 0;
  oscillators: FakeOscillator[] = [];
  gains: FakeGain[] = [];
  bufferSources: FakeBufferSource[] = [];
  /** Set to make `resume()` reject, standing in for a browser that blocks it. */
  resumeRejects = false;

  async resume(): Promise<void> {
    if (this.resumeRejects) throw new Error("blocked by autoplay policy");
    this.resumes++;
    this.state = "running";
  }
  async suspend(): Promise<void> {
    this.suspends++;
    this.state = "suspended";
  }
  createGain(): FakeGain {
    const g = new FakeGain();
    this.gains.push(g);
    return g;
  }
  createOscillator(): FakeOscillator {
    const o = new FakeOscillator();
    this.oscillators.push(o);
    return o;
  }
  createBiquadFilter(): FakeFilter {
    return new FakeFilter();
  }
  createBufferSource(): FakeBufferSource {
    const s = new FakeBufferSource();
    this.bufferSources.push(s);
    return s;
  }
  createConvolver(): FakeConvolver {
    return new FakeConvolver();
  }
  createDynamicsCompressor(): FakeCompressor {
    return new FakeCompressor();
  }
  createBuffer(channels: number, length: number, rate: number): FakeBuffer {
    return new FakeBuffer(channels, length, rate);
  }
}
