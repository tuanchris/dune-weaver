import { useEffect, useRef } from 'react'

// Client-side port of the firmware LED engine (dune-weaver-firmware
// FluidNC/src/Leds.cpp) so the ring preview animates exactly like the table.
// Effect ids, palettes and the 8-bit math mirror the firmware; the phase is a
// uint16 in 8.8 fixed point advanced by speed*8 every FRAME_MS.

const NUM_LEDS = 60
const FRAME_MS = 33

// Firmware effect ids (Leds.h EFFECT_*)
const FX = {
  OFF: 0, STATIC: 1, RAINBOW: 2, BREATHE: 3, COLORLOOP: 4, THEATER: 5,
  SCAN: 6, RUNNING: 7, SINE: 8, GRADIENT: 9, SINELON: 10, TWINKLE: 11,
  SPARKLE: 12, FIRE: 13, CANDLE: 14, METEOR: 15, BOUNCING: 16, WIPE: 17,
  DUALSCAN: 18, JUGGLE: 19, MULTICOMET: 20, GLITTER: 21, DISSOLVE: 22,
  RIPPLE: 23, DRIP: 24, LIGHTNING: 25, FIREWORKS: 26, PLASMA: 27,
  HEARTBEAT: 28, STROBE: 29, POLICE: 30, CHASE: 31, RAILWAY: 32,
  PACIFICA: 33, AURORA: 34, PRIDE: 35, COLORWAVES: 36, BPM: 37, BALL: 38,
} as const

// 16-entry packed-RGB palettes (Leds.cpp); ids 1..7, id 0 = wheel()
const PALETTES: number[][] = [
  [0x191970, 0x00008B, 0x191970, 0x000080, 0x00008B, 0x0000CD, 0x2E8B57, 0x008080,
   0x5F9EA0, 0x0000FF, 0x008B8B, 0x6495ED, 0x7FFFD4, 0x2E8B57, 0x00FFFF, 0x87CEFA], // ocean
  [0x000000, 0x800000, 0x000000, 0x800000, 0x8B0000, 0x800000, 0x8B0000, 0x8B0000,
   0x8B0000, 0x8B0000, 0xFF0000, 0xFFA500, 0xFFFFFF, 0xFFA500, 0xFF0000, 0x8B0000], // lava
  [0x006400, 0x006400, 0x556B2F, 0x006400, 0x008000, 0x228B22, 0x6B8E23, 0x008000,
   0x2E8B57, 0x66CDAA, 0x32CD32, 0x9ACD32, 0x90EE90, 0x7CFC00, 0x66CDAA, 0x228B22], // forest
  [0x5500AB, 0x84007C, 0xB5004B, 0xE5001B, 0xE81700, 0xB84700, 0xAB7700, 0xABAB00,
   0xAB5500, 0xDD2200, 0xF2000E, 0xC2003E, 0x8F0071, 0x5F00A1, 0x2F00D0, 0x0700E9], // party
  [0x0000FF, 0x00008B, 0x00008B, 0x00008B, 0x00008B, 0x00008B, 0x00008B, 0x00008B,
   0x0000FF, 0x00008B, 0x87CEEB, 0x87CEEB, 0xADD8E6, 0xFFFFFF, 0xADD8E6, 0x87CEEB], // cloud
  [0x000000, 0x330000, 0x660000, 0x990000, 0xCC0000, 0xFF0000, 0xFF3300, 0xFF6600,
   0xFF9900, 0xFFCC00, 0xFFFF00, 0xFFFF33, 0xFFFF66, 0xFFFF99, 0xFFFFCC, 0xFFFFFF], // heat
  [0x00008B, 0x4B0082, 0x800080, 0xC71585, 0xFF1493, 0xFF4500, 0xFF8C00, 0xFFD700,
   0xFFA500, 0xFF4500, 0xC71585, 0x800080, 0x4B0082, 0x191970, 0x00008B, 0x000033], // sunset
]

const PAL_OCEAN = PALETTES[0]
const PAL_AURORA = [
  0x001A0A, 0x003311, 0x004D1A, 0x006622, 0x00994D, 0x00CC66, 0x00FF7F, 0x2E8B57,
  0x008080, 0x4B0082, 0x800080, 0x9400D3, 0x4B0082, 0x008080, 0x00994D, 0x003311,
]

export interface BallPreviewParams {
  size: number
  direction: 'cw' | 'ccw'
  align: number
  fgbright: number
  bgbright: number
  bgEffectId: number
}

interface EngineParams {
  effectId: number
  paletteId: number
  color1: [number, number, number]
  color2: [number, number, number]
  brightness255: number
  speed: number
  ball: BallPreviewParams
}

function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.replace('#', ''), 16) || 0
  return [(v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff]
}

// WS2812s emit linear light but canvas colors are sRGB: without gamma
// correction a half-brightness LED renders as a muddy, tinted mid-tone.
const GAMMA = new Uint8Array(256)
for (let i = 0; i < 256; i++) {
  GAMMA[i] = Math.round(255 * Math.pow(i / 255, 1 / 2.2))
}

class LedEngine {
  fb = new Uint8Array(NUM_LEDS * 3)
  heat = new Uint8Array(NUM_LEDS)
  rng = (Math.floor(performance.now()) * 2654435761) >>> 0 || 1
  phase = 0 // uint16, 8.8 fixed point
  candle = 200
  aux = 0
  ballPos = [0, 0, 0]
  ballVel = [4.4, 3.9, 3.4]
  lastEffect = -1
  lastBgEffect = -1
  ballTrack = -1
  simBallFrac = 0 // simulated sand-ball angle (the browser has no kinematics)
  p!: EngineParams

  random8(): number {
    let x = this.rng
    x = (x ^ (x << 13)) >>> 0
    x = (x ^ (x >>> 17)) >>> 0
    x = (x ^ (x << 5)) >>> 0
    this.rng = x
    return x & 0xff
  }
  random8lim(lim: number): number {
    return (this.random8() * lim) >> 8
  }
  sin8(theta: number): number {
    return (Math.sin(((theta & 0xff) * 2 * Math.PI) / 256) * 127.5 + 127.5) | 0
  }
  scale8(v: number, s: number): number {
    return (v * (s + 1)) >> 8
  }
  qadd8(a: number, b: number): number {
    return Math.min(255, a + b)
  }
  qsub8(a: number, b: number): number {
    return Math.max(0, a - b)
  }
  lerp8(a: number, b: number, t: number): number {
    return a + (((b - a) * t) >> 8)
  }

  setFb(i: number, r: number, g: number, b: number): void {
    if (i < 0 || i >= NUM_LEDS) return
    this.fb[i * 3] = r
    this.fb[i * 3 + 1] = g
    this.fb[i * 3 + 2] = b
  }
  addFb(i: number, r: number, g: number, b: number): void {
    if (i < 0 || i >= NUM_LEDS) return
    this.fb[i * 3] = this.qadd8(this.fb[i * 3], r)
    this.fb[i * 3 + 1] = this.qadd8(this.fb[i * 3 + 1], g)
    this.fb[i * 3 + 2] = this.qadd8(this.fb[i * 3 + 2], b)
  }
  fadeBy(amount: number): void {
    const keep = 256 - amount
    for (let i = 0; i < NUM_LEDS * 3; i++) this.fb[i] = (this.fb[i] * keep) >> 8
  }

  wheel(pos: number): [number, number, number] {
    pos = (255 - pos) & 0xff
    if (pos < 85) return [255 - pos * 3, 0, pos * 3]
    if (pos < 170) {
      pos -= 85
      return [0, pos * 3, 255 - pos * 3]
    }
    pos -= 170
    return [pos * 3, 255 - pos * 3, 0]
  }
  heatColor(heat: number): [number, number, number] {
    const t192 = this.scale8(heat, 191)
    const ramp = (t192 & 0x3f) << 2
    if (t192 & 0x80) return [255, 255, ramp]
    if (t192 & 0x40) return [255, ramp, 0]
    return [ramp, 0, 0]
  }
  sampleTable(pal: number[], index: number): [number, number, number] {
    const e = index >> 4
    const f = (index & 0x0f) << 4
    const c0 = pal[e]
    const c1 = pal[(e + 1) & 15]
    return [
      this.lerp8((c0 >> 16) & 0xff, (c1 >> 16) & 0xff, f),
      this.lerp8((c0 >> 8) & 0xff, (c1 >> 8) & 0xff, f),
      this.lerp8(c0 & 0xff, c1 & 0xff, f),
    ]
  }
  palColor(index: number): [number, number, number] {
    const p = this.p.paletteId
    if (p <= 0 || p > PALETTES.length) return this.wheel(index & 0xff)
    return this.sampleTable(PALETTES[p - 1], index & 0xff)
  }

  tick(): void {
    this.phase = (this.phase + this.p.speed * 8) & 0xffff
    this.simBallFrac = (this.simBallFrac + FRAME_MS / 15000) % 1
    this.renderEffect(this.p.effectId, this.p.speed, false)
  }

  renderEffect(effect: number, speed: number, nested: boolean): void {
    if (nested ? effect !== this.lastBgEffect : effect !== this.lastEffect) {
      if (nested) this.lastBgEffect = effect
      else this.lastEffect = effect
      this.fb.fill(0)
      this.heat.fill(0)
      this.candle = 200
      this.aux = 0
      for (let k = 0; k < 3; k++) {
        this.ballPos[k] = 0
        this.ballVel[k] = 4.4 - 0.5 * k
      }
      if (!nested) this.ballTrack = -1
    }

    const hi = (this.phase >> 8) & 0xff
    const N = NUM_LEDS
    let rgb: [number, number, number]

    switch (effect) {
      case FX.STATIC: {
        const [r, g, b] = this.p.color1
        for (let i = 0; i < N; i++) this.setFb(i, r, g, b)
        break
      }
      case FX.RAINBOW:
        for (let i = 0; i < N; i++) {
          rgb = this.palColor((hi + ((i * 256) / N)) & 0xff)
          this.setFb(i, rgb[0], rgb[1], rgb[2])
        }
        break
      case FX.BREATHE: {
        const [r, g, b] = this.p.color1
        const lvl = 16 + ((this.sin8(hi) * 239) >> 8)
        for (let i = 0; i < N; i++) this.setFb(i, (r * lvl) >> 8, (g * lvl) >> 8, (b * lvl) >> 8)
        break
      }
      case FX.COLORLOOP: {
        rgb = this.palColor(hi)
        for (let i = 0; i < N; i++) this.setFb(i, rgb[0], rgb[1], rgb[2])
        break
      }
      case FX.THEATER: {
        const [r, g, b] = this.p.color1
        const off = (this.phase >> 9) % 3
        for (let i = 0; i < N; i++) {
          if (i % 3 === off) this.setFb(i, r, g, b)
          else this.setFb(i, 0, 0, 0)
        }
        break
      }
      case FX.SCAN: {
        const [r, g, b] = this.p.color1
        this.fadeBy(90)
        this.setFb(this.scale8(this.sin8(hi), N - 1), r, g, b)
        break
      }
      case FX.RUNNING: {
        const [r, g, b] = this.p.color1
        for (let i = 0; i < N; i++) {
          const s = this.sin8((i * ((256 / N) | 0) - hi) & 0xff)
          this.setFb(i, (r * s) >> 8, (g * s) >> 8, (b * s) >> 8)
        }
        break
      }
      case FX.SINE: {
        const [r, g, b] = this.p.color1
        for (let i = 0; i < N; i++) {
          const s = this.sin8((i * ((512 / N) | 0) + hi) & 0xff)
          this.setFb(i, (r * s) >> 8, (g * s) >> 8, (b * s) >> 8)
        }
        break
      }
      case FX.GRADIENT: {
        const [r1, g1, b1] = this.p.color1
        const [r2, g2, b2] = this.p.color2
        for (let i = 0; i < N; i++) {
          const t = (((i * 256) / N) + hi) & 0xff
          const tri = t < 128 ? t * 2 : (255 - t) * 2
          this.setFb(i, this.lerp8(r1, r2, tri), this.lerp8(g1, g2, tri), this.lerp8(b1, b2, tri))
        }
        break
      }
      case FX.SINELON: {
        this.fadeBy(40)
        const pos = this.scale8(this.sin8(hi), N - 1)
        rgb = this.palColor((this.phase >> 7) & 0xff)
        this.addFb(pos, rgb[0], rgb[1], rgb[2])
        break
      }
      case FX.TWINKLE:
        this.fadeBy(28)
        if (this.random8() < speed) {
          rgb = this.palColor(this.random8())
          this.setFb(this.random8lim(N), rgb[0], rgb[1], rgb[2])
        }
        break
      case FX.SPARKLE: {
        const [r, g, b] = this.p.color1
        for (let i = 0; i < N; i++) this.setFb(i, (r * 40) >> 8, (g * 40) >> 8, (b * 40) >> 8)
        this.setFb(this.random8lim(N), 255, 255, 255)
        break
      }
      case FX.FIRE: {
        for (let i = 0; i < N; i++) {
          this.heat[i] = this.qsub8(this.heat[i], this.random8lim(((55 * 10) / N + 2) | 0))
        }
        for (let k = N - 1; k >= 2; k--) {
          this.heat[k] = ((this.heat[k - 1] + this.heat[k - 2] + this.heat[k - 2]) / 3) | 0
        }
        if (this.random8() < 120) {
          const y = this.random8lim(7)
          this.heat[y] = this.qadd8(this.heat[y], this.random8lim(95) + 160)
        }
        for (let i = 0; i < N; i++) {
          rgb = this.heatColor(this.heat[i])
          this.setFb(i, rgb[0], rgb[1], rgb[2])
        }
        break
      }
      case FX.CANDLE: {
        const [r, g, b] = this.p.color1
        const target = 100 + this.random8lim(155)
        this.candle = (this.candle * 7 + target) >> 3
        for (let i = 0; i < N; i++) {
          this.setFb(i, (r * this.candle) >> 8, (g * this.candle) >> 8, (b * this.candle) >> 8)
        }
        break
      }
      case FX.METEOR: {
        const [r, g, b] = this.p.color1
        this.fadeBy(40 + this.random8lim(40))
        this.setFb((this.phase >> 8) % N, r, g, b)
        break
      }
      case FX.BOUNCING: {
        const [r, g, b] = this.p.color1
        this.fadeBy(120)
        const dt = (FRAME_MS / 1000) * (speed / 50)
        for (let k = 0; k < 3; k++) {
          this.ballVel[k] -= 9.8 * dt
          this.ballPos[k] += this.ballVel[k] * dt
          if (this.ballPos[k] < 0) {
            this.ballPos[k] = 0
            this.ballVel[k] = -this.ballVel[k] * 0.9
            if (this.ballVel[k] < 0.6) this.ballVel[k] = 4.4 - 0.5 * k
          }
          this.addFb((this.ballPos[k] * (N - 1)) | 0, r, g, b)
        }
        break
      }
      case FX.WIPE: {
        const [r, g, b] = this.p.color1
        const [r2, g2, b2] = this.p.color2
        const span = (this.phase >> 7) % (2 * N)
        for (let i = 0; i < N; i++) {
          if (span < N) {
            if (i <= span) this.setFb(i, r, g, b)
            else this.setFb(i, r2, g2, b2)
          } else {
            if (i <= span - N) this.setFb(i, r2, g2, b2)
            else this.setFb(i, r, g, b)
          }
        }
        break
      }
      case FX.DUALSCAN: {
        const [r, g, b] = this.p.color1
        const [r2, g2, b2] = this.p.color2
        this.fadeBy(80)
        const pos = this.scale8(this.sin8(hi), N - 1)
        this.addFb(pos, r, g, b)
        this.addFb(N - 1 - pos, r2, g2, b2)
        break
      }
      case FX.JUGGLE:
        this.fadeBy(40)
        for (let k = 0; k < 3; k++) {
          const pos = this.scale8(this.sin8(((this.phase >> 8) * (k + 2)) & 0xff), N - 1)
          rgb = this.palColor((k * 85 + hi) & 0xff)
          this.addFb(pos, rgb[0], rgb[1], rgb[2])
        }
        break
      case FX.MULTICOMET:
        this.fadeBy(48)
        for (let k = 0; k < 3; k++) {
          const pos = ((((this.phase >> 8) * (k + 1)) >> 1) + k * ((N / 3) | 0)) % N
          rgb = this.palColor((k * 85) & 0xff)
          this.addFb(pos, rgb[0], rgb[1], rgb[2])
        }
        break
      case FX.GLITTER:
        for (let i = 0; i < N; i++) {
          rgb = this.palColor((hi + ((i * 256) / N)) & 0xff)
          this.setFb(i, (rgb[0] * 180) >> 8, (rgb[1] * 180) >> 8, (rgb[2] * 180) >> 8)
        }
        if (this.random8() < 60) this.setFb(this.random8lim(N), 255, 255, 255)
        break
      case FX.DISSOLVE: {
        const [r, g, b] = this.p.color1
        const [r2, g2, b2] = this.p.color2
        const converts = ((N / 12) | 0) + 1
        for (let n = 0; n < converts; n++) this.heat[this.random8lim(N)] = this.aux
        let remaining = 0
        for (let i = 0; i < N; i++) {
          if (this.heat[i] !== this.aux) remaining++
          if (this.heat[i]) this.setFb(i, r2, g2, b2)
          else this.setFb(i, r, g, b)
        }
        if (remaining === 0) this.aux ^= 1
        break
      }
      case FX.RIPPLE: {
        this.fadeBy(40)
        const step = 0.5 * (speed / 50)
        for (let k = 0; k < 3; k++) {
          if (this.ballVel[k] <= 0 || this.ballVel[k] > N / 2) {
            this.ballPos[k] = this.random8lim(N)
            this.ballVel[k] = 0.01
          }
          const center = this.ballPos[k] | 0
          const radius = this.ballVel[k] | 0
          const fade = 255 - this.scale8(((this.ballVel[k] * 512) / N) & 0xff, 255)
          rgb = this.palColor((center * 5) & 0xff)
          this.addFb((center + radius) % N, (rgb[0] * fade) >> 8, (rgb[1] * fade) >> 8, (rgb[2] * fade) >> 8)
          this.addFb((center - radius + N) % N, (rgb[0] * fade) >> 8, (rgb[1] * fade) >> 8, (rgb[2] * fade) >> 8)
          this.ballVel[k] += step
        }
        break
      }
      case FX.DRIP: {
        const [r, g, b] = this.p.color1
        this.fadeBy(60)
        const accel = 0.02 * (speed / 50)
        for (let k = 0; k < 3; k++) {
          this.ballVel[k] += accel
          this.ballPos[k] -= this.ballVel[k]
          if (this.ballPos[k] <= 0) {
            this.setFb(0, 255, 255, 255)
            this.setFb(1, (r * 128) >> 8, (g * 128) >> 8, (b * 128) >> 8)
            this.ballPos[k] = N - 1 - this.random8lim(N >> 1)
            this.ballVel[k] = 0
          }
          this.addFb(this.ballPos[k] | 0, r, g, b)
        }
        break
      }
      case FX.LIGHTNING:
        this.fadeBy(120)
        if (this.random8() < 12) {
          const start = this.random8lim(N)
          const len = 2 + this.random8lim((N / 3) | 0)
          for (let j = 0; j < len; j++) this.setFb((start + j) % N, 255, 255, 255)
        }
        break
      case FX.FIREWORKS:
        this.fadeBy(48)
        if (this.random8() < 50) {
          const center = this.random8lim(N)
          rgb = this.palColor(this.random8())
          this.addFb(center, rgb[0], rgb[1], rgb[2])
          this.addFb((center + 1) % N, rgb[0] >> 1, rgb[1] >> 1, rgb[2] >> 1)
          this.addFb((center - 1 + N) % N, rgb[0] >> 1, rgb[1] >> 1, rgb[2] >> 1)
        }
        break
      case FX.PLASMA:
        for (let i = 0; i < N; i++) {
          const x = ((i * 256) / N) & 0xff
          const v1 = this.sin8((x * 2 + hi) & 0xff)
          const v2 = this.sin8((x * 3 - hi * 2) & 0xff)
          rgb = this.palColor((v1 + v2) >> 1)
          this.setFb(i, rgb[0], rgb[1], rgb[2])
        }
        break
      case FX.HEARTBEAT: {
        const [r, g, b] = this.p.color1
        const t = hi
        let lvl: number
        if (t < 32) lvl = this.sin8((t * 4) & 0xff)
        else if (t < 96) lvl = 24
        else if (t < 128) lvl = this.sin8(((t - 96) * 4) & 0xff)
        else lvl = 24
        if (lvl < 24) lvl = 24
        for (let i = 0; i < N; i++) this.setFb(i, (r * lvl) >> 8, (g * lvl) >> 8, (b * lvl) >> 8)
        break
      }
      case FX.STROBE: {
        const [r, g, b] = this.p.color1
        const on = hi < 32
        for (let i = 0; i < N; i++) {
          if (on) this.setFb(i, r, g, b)
          else this.setFb(i, 0, 0, 0)
        }
        break
      }
      case FX.POLICE: {
        const phaseA = (this.phase >> 9) & 1
        const half = N >> 1
        for (let i = 0; i < N; i++) {
          const left = i < half
          if (left === Boolean(phaseA)) this.setFb(i, left ? 255 : 0, 0, left ? 0 : 255)
          else this.setFb(i, 0, 0, 0)
        }
        break
      }
      case FX.CHASE: {
        const [r, g, b] = this.p.color1
        const [r2, g2, b2] = this.p.color2
        for (let i = 0; i < N; i++) this.setFb(i, (r2 * 40) >> 8, (g2 * 40) >> 8, (b2 * 40) >> 8)
        const pos = (this.phase >> 8) % N
        for (let j = 0; j < 3; j++) this.setFb((pos + j) % N, r, g, b)
        break
      }
      case FX.RAILWAY: {
        const [r, g, b] = this.p.color1
        const [r2, g2, b2] = this.p.color2
        for (let i = 0; i < N; i++) {
          const s = this.sin8((i * ((256 / N) | 0) - hi) & 0xff)
          const sc = 100 + ((s * 155) >> 8)
          if (i & 1) this.setFb(i, (r * sc) >> 8, (g * sc) >> 8, (b * sc) >> 8)
          else this.setFb(i, (r2 * sc) >> 8, (g2 * sc) >> 8, (b2 * sc) >> 8)
        }
        break
      }
      case FX.PACIFICA:
        for (let i = 0; i < N; i++) {
          const a = this.sin8((i * 4 + (this.phase >> 8)) & 0xff)
          const c = this.sin8((i * 5 - (this.phase >> 7)) & 0xff)
          const d = this.sin8((i * 3 + (this.phase >> 9)) & 0xff)
          rgb = this.sampleTable(PAL_OCEAN, ((a + c + d) / 3) | 0)
          this.setFb(i, rgb[0], rgb[1], rgb[2])
          const cap = this.sin8((i * 9 - (this.phase >> 5)) & 0xff)
          if (cap > 236) {
            const w = (cap - 236) * 8
            this.addFb(i, w, w, w)
          }
        }
        break
      case FX.AURORA:
        for (let i = 0; i < N; i++) {
          const a = this.sin8((i * 3 + (this.phase >> 8)) & 0xff)
          const c = this.sin8((i * 2 - (this.phase >> 9)) & 0xff)
          rgb = this.sampleTable(PAL_AURORA, (a + c) >> 1)
          const w = this.sin8((i * 5 + (this.phase >> 7)) & 0xff)
          const bri = 40 + ((w * 215) >> 8)
          this.setFb(i, (rgb[0] * bri) >> 8, (rgb[1] * bri) >> 8, (rgb[2] * bri) >> 8)
        }
        break
      case FX.PRIDE:
        for (let i = 0; i < N; i++) {
          rgb = this.wheel(((this.phase >> 8) + i * 2) & 0xff)
          const bw = this.sin8((i * 7 + (this.phase >> 6)) & 0xff)
          const bri = 60 + ((bw * 195) >> 8)
          this.setFb(i, (rgb[0] * bri) >> 8, (rgb[1] * bri) >> 8, (rgb[2] * bri) >> 8)
        }
        break
      case FX.COLORWAVES:
        for (let i = 0; i < N; i++) {
          rgb = this.palColor(((this.phase >> 8) + i * 3) & 0xff)
          const bw = this.sin8((i * 7 + (this.phase >> 6)) & 0xff)
          const bri = 60 + ((bw * 195) >> 8)
          this.setFb(i, (rgb[0] * bri) >> 8, (rgb[1] * bri) >> 8, (rgb[2] * bri) >> 8)
        }
        break
      case FX.BPM: {
        const beat = this.sin8((this.phase >> 6) & 0xff)
        for (let i = 0; i < N; i++) {
          rgb = this.palColor(((this.phase >> 8) + i * 3) & 0xff)
          let bri = this.qsub8(beat, (i * 2) & 0xff)
          if (bri < 40) bri = 40
          this.setFb(i, (rgb[0] * bri) >> 8, (rgb[1] * bri) >> 8, (rgb[2] * bri) >> 8)
        }
        break
      }
      case FX.BALL: {
        const ball = this.p.ball
        let bg = ball.bgEffectId
        if (bg === FX.BALL) bg = FX.STATIC
        if (bg === FX.OFF) {
          this.fb.fill(0)
        } else if (bg === FX.STATIC) {
          const [br, bgc, bb] = this.p.color2
          for (let i = 0; i < N; i++) this.setFb(i, br, bgc, bb)
        } else {
          this.renderEffect(bg, speed, true)
        }
        if (ball.bgbright < 255) {
          for (let i = 0; i < N * 3; i++) this.fb[i] = this.scale8(this.fb[i], ball.bgbright)
        }

        // The firmware reads the real sand-ball angle; the preview orbits a
        // simulated one, with the same shortest-path smoothing glide.
        let pf = this.simBallFrac * (ball.direction === 'ccw' ? -1 : 1) + ball.align / 360
        pf -= Math.floor(pf)
        if (this.ballTrack < 0) this.ballTrack = pf
        const alpha = Math.max(speed / 255, 0.03)
        let delta = pf - this.ballTrack
        delta -= Math.round(delta)
        this.ballTrack += delta * alpha
        this.ballTrack -= Math.floor(this.ballTrack)

        const posf = this.ballTrack * N
        const size = Math.max(1, ball.size)
        let [r, g, b] = this.p.color1
        r = this.scale8(r, ball.fgbright)
        g = this.scale8(g, ball.fgbright)
        b = this.scale8(b, ball.fgbright)
        for (let i = 0; i < N; i++) {
          let d = Math.abs(i - posf)
          d = Math.min(d, N - d)
          let t = 1 - d / size
          if (t <= 0) continue
          t = t * t * (3 - 2 * t)
          const cr = this.fb[i * 3]
          const cg = this.fb[i * 3 + 1]
          const cb = this.fb[i * 3 + 2]
          this.setFb(i, (cr + (r - cr) * t) | 0, (cg + (g - cg) * t) | 0, (cb + (b - cb) * t) | 0)
        }
        break
      }
      default: // EFFECT_OFF
        this.fb.fill(0)
        break
    }
  }
}

export interface LedRingPreviewProps {
  effectId: number
  paletteId: number
  color1: string
  color2: string
  brightness: number // UI percent 0..100
  speed: number // firmware range 1..255
  powerOn: boolean
  ball: BallPreviewParams
  className?: string
}

export function LedRingPreview({
  effectId,
  paletteId,
  color1,
  color2,
  brightness,
  speed,
  powerOn,
  ball,
  className,
}: LedRingPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const engineRef = useRef<LedEngine | null>(null)
  const paramsRef = useRef<EngineParams & { powerOn: boolean }>(null as never)

  paramsRef.current = {
    effectId,
    paletteId,
    color1: hexToRgb(color1),
    color2: hexToRgb(color2),
    brightness255: Math.round((Math.max(0, Math.min(100, brightness)) * 255) / 100),
    speed: Math.max(1, Math.min(255, speed)),
    ball,
    powerOn,
  }

  const reduceMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  // With reduced motion there is no animation loop, so the static frame must
  // re-render whenever any visual input changes.
  const staticKey = reduceMotion
    ? JSON.stringify([effectId, paletteId, color1, color2, brightness, speed, ball])
    : ''

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    if (!engineRef.current) engineRef.current = new LedEngine()
    const engine = engineRef.current

    const cssSize = canvas.clientWidth || 144
    const dpr = window.devicePixelRatio || 1
    canvas.width = cssSize * dpr
    canvas.height = cssSize * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const thickness = cssSize * 0.075
    const radius = cssSize / 2 - thickness / 2 - cssSize * 0.06 // margin for glow
    const cx = cssSize / 2
    const cy = cssSize / 2
    const segAngle = (2 * Math.PI) / NUM_LEDS
    // slight overlap hides the anti-aliased seams between adjacent arcs,
    // so the ring reads as one continuous band (no per-pixel dividers)
    const eps = 0.6 / radius

    const drawFrame = () => {
      const p = paramsRef.current
      ctx.clearRect(0, 0, cssSize, cssSize)
      ctx.lineWidth = thickness
      ctx.lineCap = 'butt'
      for (let i = 0; i < NUM_LEDS; i++) {
        let r = 0
        let g = 0
        let b = 0
        if (p.powerOn) {
          // same master-brightness scaling as the firmware's commit(),
          // then linear -> sRGB so on-screen hues match the physical LEDs
          const s = p.brightness255 + 1
          r = GAMMA[(engine.fb[i * 3] * s) >> 8]
          g = GAMMA[(engine.fb[i * 3 + 1] * s) >> 8]
          b = GAMMA[(engine.fb[i * 3 + 2] * s) >> 8]
        }
        // LED 0 at 12 o'clock, increasing clockwise (matches ball align=0)
        const a0 = -Math.PI / 2 + i * segAngle - eps
        const a1 = a0 + segAngle + 2 * eps
        const lit = r + g + b > 6
        ctx.beginPath()
        ctx.arc(cx, cy, radius, a0, a1)
        if (lit) {
          ctx.shadowColor = `rgb(${r},${g},${b})`
          ctx.shadowBlur = cssSize * 0.05
          ctx.strokeStyle = `rgb(${r},${g},${b})`
        } else {
          ctx.shadowBlur = 0
          // unlit stretch: faint neutral so the ring shape reads in both themes
          ctx.strokeStyle = p.powerOn ? `rgba(127,127,127,0.12)` : `rgba(127,127,127,0.22)`
        }
        ctx.stroke()
      }
      ctx.shadowBlur = 0
    }

    if (reduceMotion) {
      // static preview: run enough frames for stateful effects to develop
      engine.p = paramsRef.current
      for (let k = 0; k < 45; k++) engine.tick()
      drawFrame()
      return
    }

    let raf = 0
    let last = 0
    const loop = (ts: number) => {
      raf = requestAnimationFrame(loop)
      if (ts - last < FRAME_MS) return
      last = ts
      if (paramsRef.current.powerOn) {
        engine.p = paramsRef.current
        engine.tick()
      }
      drawFrame()
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
    // Animated mode rebinds only on power changes; per-frame params flow
    // through paramsRef without restarting the loop.
  }, [powerOn, reduceMotion, staticKey])

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />
}
