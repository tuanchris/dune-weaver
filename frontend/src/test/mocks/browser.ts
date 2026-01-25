import { vi } from 'vitest'

// Mock IntersectionObserver
export class MockIntersectionObserver {
  callback: IntersectionObserverCallback
  elements: Set<Element> = new Set()

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
  }

  observe(element: Element) {
    this.elements.add(element)
    // Immediately trigger as visible for testing
    this.callback(
      [{ target: element, isIntersecting: true, intersectionRatio: 1 } as IntersectionObserverEntry],
      this
    )
  }

  unobserve(element: Element) {
    this.elements.delete(element)
  }

  disconnect() {
    this.elements.clear()
  }
}

// Mock matchMedia
export function createMockMatchMedia(matches: boolean = false) {
  return vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

// Mock ResizeObserver
export class MockResizeObserver {
  callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }

  observe() {}
  unobserve() {}
  disconnect() {}
}

// Setup all browser mocks
export function setupBrowserMocks() {
  vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
  vi.stubGlobal('ResizeObserver', MockResizeObserver)
  vi.stubGlobal('matchMedia', createMockMatchMedia())

  // Mock canvas context
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
    fillRect: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    arc: vi.fn(),
    drawImage: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    scale: vi.fn(),
    translate: vi.fn(),
    rotate: vi.fn(),
    setTransform: vi.fn(),
    getImageData: vi.fn().mockReturnValue({ data: new Uint8ClampedArray(4) }),
    putImageData: vi.fn(),
    createLinearGradient: vi.fn().mockReturnValue({ addColorStop: vi.fn() }),
    createRadialGradient: vi.fn().mockReturnValue({ addColorStop: vi.fn() }),
    measureText: vi.fn().mockReturnValue({ width: 0 }),
    fillText: vi.fn(),
    strokeText: vi.fn(),
  })

  // Mock localStorage
  const localStorageMock = {
    store: {} as Record<string, string>,
    getItem: vi.fn((key: string) => localStorageMock.store[key] || null),
    setItem: vi.fn((key: string, value: string) => { localStorageMock.store[key] = value }),
    removeItem: vi.fn((key: string) => { delete localStorageMock.store[key] }),
    clear: vi.fn(() => { localStorageMock.store = {} }),
    get length() { return Object.keys(localStorageMock.store).length },
    key: vi.fn((i: number) => Object.keys(localStorageMock.store)[i] || null),
  }
  vi.stubGlobal('localStorage', localStorageMock)

  return { localStorage: localStorageMock }
}

export function cleanupBrowserMocks() {
  vi.unstubAllGlobals()
}
