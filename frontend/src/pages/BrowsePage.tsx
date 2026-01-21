import { useState, useEffect, useMemo, useRef, useCallback, createContext, useContext } from 'react'
import { toast } from 'sonner'
import {
  initPreviewCacheDB,
  getPreviewsFromCache,
  savePreviewToCache,
  cacheAllPreviews,
} from '@/lib/previewCache'
import { fuzzyMatch } from '@/lib/utils'
import { apiClient } from '@/lib/apiClient'
import { useOnBackendConnected } from '@/hooks/useBackendConnection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

// Types
interface PatternMetadata {
  path: string
  name: string
  category: string
  date_modified: number
  coordinates_count: number
}

interface PreviewData {
  image_data: string
  first_coordinate: { x: number; y: number } | null
  last_coordinate: { x: number; y: number } | null
  error?: string
}

// Coordinates come as [theta, rho] tuples from the backend
type Coordinate = [number, number]

type SortOption = 'name' | 'date' | 'size' | 'favorites'
type PreExecution = 'none' | 'adaptive' | 'clear_from_in' | 'clear_from_out' | 'clear_sideway'

const preExecutionOptions: { value: PreExecution; label: string }[] = [
  { value: 'adaptive', label: 'Adaptive' },
  { value: 'clear_from_in', label: 'Clear From Center' },
  { value: 'clear_from_out', label: 'Clear From Perimeter' },
  { value: 'clear_sideway', label: 'Clear Sideway' },
  { value: 'none', label: 'None' },
]

// Context for lazy loading previews
interface PreviewContextType {
  requestPreview: (path: string) => void
  previews: Record<string, PreviewData>
}

const PreviewContext = createContext<PreviewContextType | null>(null)

export function BrowsePage() {
  // Data state
  const [patterns, setPatterns] = useState<PatternMetadata[]>([])
  const [previews, setPreviews] = useState<Record<string, PreviewData>>({})
  const [isLoading, setIsLoading] = useState(true)

  // Filter/sort state
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [sortBy, setSortBy] = useState<SortOption>('name')
  const [sortAsc, setSortAsc] = useState(true)

  // Selection and panel state
  const [selectedPattern, setSelectedPattern] = useState<PatternMetadata | null>(null)
  const [isPanelOpen, setIsPanelOpen] = useState(false)
  const [preExecution, setPreExecution] = useState<PreExecution>(() => {
    const cached = localStorage.getItem('preExecution')
    return (cached as PreExecution) || 'adaptive'
  })
  const [isRunning, setIsRunning] = useState(false)

  // Animated preview modal state
  const [isAnimatedPreviewOpen, setIsAnimatedPreviewOpen] = useState(false)
  const [coordinates, setCoordinates] = useState<Coordinate[]>([])
  const [isLoadingCoordinates, setIsLoadingCoordinates] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [progress, setProgress] = useState(0)

  // Pattern execution history state
  const [patternHistory, setPatternHistory] = useState<{
    actual_time_formatted: string | null
    speed: number | null
  } | null>(null)

  // All pattern histories for badges
  const [allPatternHistories, setAllPatternHistories] = useState<Record<string, {
    actual_time_formatted: string | null
    timestamp: string | null
  }>>({})

  // Canvas and animation refs
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | null>(null)
  const currentIndexRef = useRef(0)

  // Lazy loading queue for previews
  const pendingPreviewsRef = useRef<Set<string>>(new Set())
  const batchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Cache all previews state
  const [isCaching, setIsCaching] = useState(false)
  const [cacheProgress, setCacheProgress] = useState(0)
  const [allCached, setAllCached] = useState(false)

  // Favorites state
  const [favorites, setFavorites] = useState<Set<string>>(new Set())

  // Upload state
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)

  // Swipe to dismiss sheet on mobile
  const sheetTouchStartRef = useRef<{ x: number; y: number } | null>(null)
  const handleSheetTouchStart = (e: React.TouchEvent) => {
    sheetTouchStartRef.current = {
      x: e.touches[0].clientX,
      y: e.touches[0].clientY,
    }
  }
  const handleSheetTouchEnd = (e: React.TouchEvent) => {
    if (!sheetTouchStartRef.current) return
    const deltaX = e.changedTouches[0].clientX - sheetTouchStartRef.current.x
    const deltaY = e.changedTouches[0].clientY - sheetTouchStartRef.current.y

    // Swipe right (positive X) or swipe down (positive Y) to dismiss
    // Require at least 80px movement and more horizontal/vertical than the other direction
    if (deltaX > 80 && deltaX > Math.abs(deltaY)) {
      setIsPanelOpen(false)
    } else if (deltaY > 80 && deltaY > Math.abs(deltaX)) {
      setIsPanelOpen(false)
    }
    sheetTouchStartRef.current = null
  }

  // Close panel when playback starts
  useEffect(() => {
    const handlePlaybackStarted = () => {
      setIsPanelOpen(false)
    }
    window.addEventListener('playback-started', handlePlaybackStarted)
    return () => window.removeEventListener('playback-started', handlePlaybackStarted)
  }, [])

  // Persist pre-execution selection to localStorage
  useEffect(() => {
    localStorage.setItem('preExecution', preExecution)
  }, [preExecution])

  // Initialize IndexedDB cache and fetch patterns on mount
  useEffect(() => {
    initPreviewCacheDB().then(() => {
      fetchPatterns()
    }).catch(() => {
      // Continue even if IndexedDB fails - just won't have persistent cache
      fetchPatterns()
    })
    loadFavorites()

    // Cleanup on unmount: abort in-flight requests and clear pending queue
    return () => {
      if (batchTimeoutRef.current) {
        clearTimeout(batchTimeoutRef.current)
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      pendingPreviewsRef.current.clear()
    }
  }, [])

  // Refetch when backend reconnects
  useOnBackendConnected(() => {
    fetchPatterns()
    loadFavorites()
  })

  // Load favorites from "Favorites" playlist
  const loadFavorites = async () => {
    try {
      const playlist = await apiClient.get<{ files?: string[] }>('/get_playlist?name=Favorites')
      setFavorites(new Set(playlist.files || []))
    } catch {
      // Favorites playlist doesn't exist yet - that's OK
    }
  }

  // Toggle favorite status for a pattern
  const toggleFavorite = async (path: string, e: React.MouseEvent) => {
    e.stopPropagation() // Don't trigger card click

    const isFavorite = favorites.has(path)
    const newFavorites = new Set(favorites)

    try {
      if (isFavorite) {
        // Remove from favorites
        newFavorites.delete(path)
        await apiClient.post('/modify_playlist', { playlist_name: 'Favorites', files: Array.from(newFavorites) })
        setFavorites(newFavorites)
        toast.success('Removed from favorites')
      } else {
        // Add to favorites - first check if playlist exists
        newFavorites.add(path)
        try {
          await apiClient.get('/get_playlist?name=Favorites')
          // Playlist exists, add to it
          await apiClient.post('/add_to_playlist', { playlist_name: 'Favorites', pattern: path })
        } catch {
          // Create playlist with this pattern
          await apiClient.post('/create_playlist', { playlist_name: 'Favorites', files: [path] })
        }
        setFavorites(newFavorites)
        toast.success('Added to favorites')
      }
    } catch {
      toast.error('Failed to update favorites')
    }
  }

  const fetchPatterns = async () => {
    setIsLoading(true)
    try {
      // Fetch patterns and history in parallel
      const [data, historyData] = await Promise.all([
        apiClient.get<PatternMetadata[]>('/list_theta_rho_files_with_metadata'),
        apiClient.get<Record<string, { actual_time_formatted: string | null; timestamp: string | null }>>('/api/pattern_history_all')
      ])
      setPatterns(data)
      setAllPatternHistories(historyData)

      if (data.length > 0) {
        // Sort patterns by name (default sort) before preloading
        const sortedPatterns = [...data].sort((a: PatternMetadata, b: PatternMetadata) =>
          a.name.localeCompare(b.name)
        )
        const allPaths = data.map((p: PatternMetadata) => p.path)

        // Preload first 30 patterns in sorted order (fills most viewports)
        const initialBatch = sortedPatterns.slice(0, 30).map((p: PatternMetadata) => p.path)
        const cachedPreviews = await getPreviewsFromCache(initialBatch)

        // Immediately display cached previews
        if (cachedPreviews.size > 0) {
          const cachedData: Record<string, PreviewData> = {}
          cachedPreviews.forEach((previewData, path) => {
            cachedData[path] = previewData
          })
          setPreviews(cachedData)
        }

        // Fetch any uncached patterns in the initial batch
        const uncachedInitial = initialBatch.filter((p: string) => !cachedPreviews.has(p))
        if (uncachedInitial.length > 0) {
          fetchPreviewsBatch(uncachedInitial)
        }

        // Check if ALL patterns are cached (for Cache All button)
        const allCachedPreviews = await getPreviewsFromCache(allPaths)
        setAllCached(allCachedPreviews.size === allPaths.length)
      }
    } catch (error) {
      console.error('Error fetching patterns:', error)
      toast.error('Failed to load patterns')
    } finally {
      setIsLoading(false)
    }
  }

  const fetchPreviewsBatch = async (filePaths: string[]) => {
    const BATCH_SIZE = 10 // Process 10 patterns at a time to avoid overwhelming the backend

    // Create new AbortController for this batch of requests
    abortControllerRef.current = new AbortController()
    const signal = abortControllerRef.current.signal

    try {
      // First check IndexedDB cache for all patterns
      const cachedPreviews = await getPreviewsFromCache(filePaths)

      // Update state with cached previews immediately
      if (cachedPreviews.size > 0) {
        const cachedData: Record<string, PreviewData> = {}
        cachedPreviews.forEach((data, path) => {
          cachedData[path] = data
        })
        setPreviews((prev) => ({ ...prev, ...cachedData }))
      }

      // Find patterns not in cache
      const uncachedPaths = filePaths.filter((path) => !cachedPreviews.has(path))

      // Fetch uncached patterns in batches to avoid overwhelming the backend
      if (uncachedPaths.length > 0) {
        for (let i = 0; i < uncachedPaths.length; i += BATCH_SIZE) {
          // Check if aborted before each batch
          if (signal.aborted) break

          const batch = uncachedPaths.slice(i, i + BATCH_SIZE)

          try {
            const data = await apiClient.post<Record<string, PreviewData>>('/preview_thr_batch', { file_names: batch }, signal)

            // Save fetched previews to IndexedDB cache
            for (const [path, previewData] of Object.entries(data)) {
              if (previewData && !(previewData as PreviewData).error) {
                savePreviewToCache(path, previewData as PreviewData)
              }
            }

            setPreviews((prev) => ({ ...prev, ...data }))
          } catch (err) {
            // Stop processing if aborted, otherwise continue with next batch
            if (err instanceof Error && err.name === 'AbortError') break
          }

          // Small delay between batches to reduce backend load
          if (i + BATCH_SIZE < uncachedPaths.length) {
            await new Promise((resolve) => setTimeout(resolve, 100))
          }
        }
      }
    } catch (error) {
      // Silently ignore abort errors
      if (error instanceof Error && error.name === 'AbortError') return
      console.error('Error fetching previews:', error)
    }
  }

  const fetchCoordinates = async (filePath: string) => {
    setIsLoadingCoordinates(true)
    try {
      const data = await apiClient.post<{ coordinates?: Coordinate[] }>('/get_theta_rho_coordinates', { file_name: filePath })
      setCoordinates(data.coordinates || [])
    } catch (error) {
      console.error('Error fetching coordinates:', error)
      toast.error('Failed to load pattern coordinates')
    } finally {
      setIsLoadingCoordinates(false)
    }
  }

  // Get unique categories
  const categories = useMemo(() => {
    const cats = new Set(patterns.map((p) => p.category))
    return ['all', ...Array.from(cats).sort()]
  }, [patterns])

  // Filter and sort patterns
  const filteredPatterns = useMemo(() => {
    let result = patterns

    if (selectedCategory !== 'all') {
      result = result.filter((p) => p.category === selectedCategory)
    }

    if (searchQuery) {
      result = result.filter(
        (p) =>
          fuzzyMatch(p.name, searchQuery) ||
          fuzzyMatch(p.category, searchQuery)
      )
    }

    result = [...result].sort((a, b) => {
      let comparison = 0
      switch (sortBy) {
        case 'name':
          comparison = a.name.localeCompare(b.name)
          break
        case 'date':
          comparison = a.date_modified - b.date_modified
          break
        case 'size':
          comparison = a.coordinates_count - b.coordinates_count
          break
        case 'favorites': {
          const aFav = favorites.has(a.path) ? 1 : 0
          const bFav = favorites.has(b.path) ? 1 : 0
          comparison = bFav - aFav // Favorites first
          if (comparison === 0) {
            comparison = a.name.localeCompare(b.name) // Then by name
          }
          break
        }
        default:
          return 0
      }
      return sortAsc ? comparison : -comparison
    })

    return result
  }, [patterns, selectedCategory, searchQuery, sortBy, sortAsc, favorites])

  // Batched preview loading - collects requests and fetches in batches
  const requestPreview = useCallback((path: string) => {
    // Skip if already loaded or pending
    if (previews[path] || pendingPreviewsRef.current.has(path)) return

    pendingPreviewsRef.current.add(path)

    // Clear existing timeout and set a new one to batch requests
    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current)
    }

    batchTimeoutRef.current = setTimeout(() => {
      const pathsToFetch = Array.from(pendingPreviewsRef.current)
      if (pathsToFetch.length > 0) {
        pendingPreviewsRef.current.clear()
        fetchPreviewsBatch(pathsToFetch)
      }
    }, 50) // Batch requests within 50ms window
  }, [previews])

  // Canvas drawing functions
  const polarToCartesian = useCallback((theta: number, rho: number, size: number) => {
    const centerX = size / 2
    const centerY = size / 2
    const radius = (size / 2) * 0.9 * rho
    const x = centerX + radius * Math.cos(theta)
    const y = centerY + radius * Math.sin(theta)
    return { x, y }
  }, [])

  // Offscreen canvas for the pattern path (performance optimization)
  const offscreenCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const lastDrawnIndexRef = useRef<number>(-1)
  const lastThemeRef = useRef<boolean | null>(null)

  // Get theme colors
  const getThemeColors = useCallback(() => {
    const isDark = document.documentElement.classList.contains('dark')
    return {
      isDark,
      bgOuter: isDark ? '#1a1a1a' : '#f5f5f5',
      bgInner: isDark ? '#262626' : '#ffffff',
      borderColor: isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(128, 128, 128, 0.3)',
      lineColor: isDark ? '#e5e5e5' : '#333333',
      markerBorder: isDark ? '#333333' : '#ffffff',
    }
  }, [])

  // Initialize or reset offscreen canvas
  const initOffscreenCanvas = useCallback((size: number, coords: Coordinate[]) => {
    const colors = getThemeColors()

    // Create offscreen canvas if needed
    if (!offscreenCanvasRef.current) {
      offscreenCanvasRef.current = document.createElement('canvas')
    }

    const offscreen = offscreenCanvasRef.current
    offscreen.width = size
    offscreen.height = size

    const ctx = offscreen.getContext('2d')
    if (!ctx) return

    // Draw background
    ctx.fillStyle = colors.bgOuter
    ctx.fillRect(0, 0, size, size)

    // Draw background circle
    ctx.beginPath()
    ctx.arc(size / 2, size / 2, (size / 2) * 0.95, 0, Math.PI * 2)
    ctx.fillStyle = colors.bgInner
    ctx.fill()
    ctx.strokeStyle = colors.borderColor
    ctx.lineWidth = 1
    ctx.stroke()

    // Setup line style for incremental drawing
    ctx.strokeStyle = colors.lineColor
    ctx.lineWidth = 1
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    // Draw initial point if we have coordinates
    if (coords.length > 0) {
      const firstPoint = polarToCartesian(coords[0][0], coords[0][1], size)
      ctx.beginPath()
      ctx.moveTo(firstPoint.x, firstPoint.y)
      ctx.stroke()
    }

    lastDrawnIndexRef.current = 0
    lastThemeRef.current = colors.isDark
  }, [getThemeColors, polarToCartesian])

  // Draw pattern incrementally for performance
  const drawPattern = useCallback((ctx: CanvasRenderingContext2D, coords: Coordinate[], upToIndex: number, forceRedraw = false) => {
    const canvas = ctx.canvas
    const size = canvas.width
    const colors = getThemeColors()

    // Check if we need to reinitialize (theme change or reset)
    const needsReinit = forceRedraw ||
      !offscreenCanvasRef.current ||
      lastThemeRef.current !== colors.isDark ||
      upToIndex < lastDrawnIndexRef.current

    if (needsReinit) {
      initOffscreenCanvas(size, coords)
    }

    const offscreen = offscreenCanvasRef.current
    if (!offscreen) return

    const offCtx = offscreen.getContext('2d')
    if (!offCtx) return

    // Draw new segments incrementally on offscreen canvas
    if (coords.length > 0 && upToIndex > lastDrawnIndexRef.current) {
      offCtx.strokeStyle = colors.lineColor
      offCtx.lineWidth = 1
      offCtx.lineCap = 'round'
      offCtx.lineJoin = 'round'

      offCtx.beginPath()
      const startPoint = polarToCartesian(
        coords[lastDrawnIndexRef.current][0],
        coords[lastDrawnIndexRef.current][1],
        size
      )
      offCtx.moveTo(startPoint.x, startPoint.y)

      for (let i = lastDrawnIndexRef.current + 1; i <= upToIndex && i < coords.length; i++) {
        const point = polarToCartesian(coords[i][0], coords[i][1], size)
        offCtx.lineTo(point.x, point.y)
      }
      offCtx.stroke()

      lastDrawnIndexRef.current = upToIndex
    }

    // Copy offscreen canvas to main canvas
    ctx.drawImage(offscreen, 0, 0)

    // Draw current position marker on main canvas
    if (upToIndex < coords.length && coords.length > 0) {
      const currentPoint = polarToCartesian(coords[upToIndex][0], coords[upToIndex][1], size)
      ctx.beginPath()
      ctx.arc(currentPoint.x, currentPoint.y, 5, 0, Math.PI * 2)
      ctx.fillStyle = '#0b80ee'
      ctx.fill()
      ctx.strokeStyle = colors.markerBorder
      ctx.lineWidth = 1
      ctx.stroke()
    }
  }, [getThemeColors, initOffscreenCanvas, polarToCartesian])

  // Animation loop
  useEffect(() => {
    if (!isPlaying || coordinates.length === 0 || !canvasRef.current) return

    const ctx = canvasRef.current.getContext('2d')
    if (!ctx) return

    let lastTime = performance.now()
    const coordsPerSecond = 100 * speed

    const animate = (currentTime: number) => {
      const deltaTime = (currentTime - lastTime) / 1000
      lastTime = currentTime

      const coordsToAdvance = Math.floor(deltaTime * coordsPerSecond)
      currentIndexRef.current = Math.min(
        currentIndexRef.current + Math.max(1, coordsToAdvance),
        coordinates.length - 1
      )

      drawPattern(ctx, coordinates, currentIndexRef.current)
      setProgress((currentIndexRef.current / (coordinates.length - 1)) * 100)

      if (currentIndexRef.current < coordinates.length - 1) {
        animationRef.current = requestAnimationFrame(animate)
      } else {
        setIsPlaying(false)
      }
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isPlaying, coordinates, speed, drawPattern])

  // Draw initial state when coordinates load
  useEffect(() => {
    if (coordinates.length > 0 && canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        currentIndexRef.current = 0
        setProgress(0)
        drawPattern(ctx, coordinates, 0, true) // Force redraw on new pattern
      }
    }
  }, [coordinates, drawPattern])

  const handlePatternClick = async (pattern: PatternMetadata) => {
    setSelectedPattern(pattern)
    setIsPanelOpen(true)
    setPreExecution('adaptive')
    setPatternHistory(null) // Reset while loading

    // Fetch pattern execution history
    try {
      const history = await apiClient.get<{
        actual_time_formatted: string | null
        speed: number | null
      }>(`/api/pattern_history/${encodeURIComponent(pattern.path)}`)
      setPatternHistory(history)
    } catch {
      // Silently ignore - history is optional
    }
  }

  const handleOpenAnimatedPreview = async () => {
    if (!selectedPattern) return
    setIsPanelOpen(false) // Close sheet before opening preview
    setIsAnimatedPreviewOpen(true)
    setIsPlaying(false)
    setProgress(0)
    currentIndexRef.current = 0
    await fetchCoordinates(selectedPattern.path)
    // Auto-play after coordinates load
    setIsPlaying(true)
  }

  const handleCloseAnimatedPreview = () => {
    setIsAnimatedPreviewOpen(false)
    setIsPlaying(false)
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current)
    }
    setCoordinates([])
  }

  const handlePlayPause = () => {
    if (isPlaying) {
      setIsPlaying(false)
    } else {
      if (currentIndexRef.current >= coordinates.length - 1) {
        currentIndexRef.current = 0
        setProgress(0)
      }
      setIsPlaying(true)
    }
  }

  const handleReset = () => {
    setIsPlaying(false)
    currentIndexRef.current = 0
    setProgress(0)
    if (canvasRef.current && coordinates.length > 0) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        drawPattern(ctx, coordinates, 0, true) // Force redraw on reset
      }
    }
  }

  const handleProgressChange = (value: number[]) => {
    const newProgress = value[0]
    setProgress(newProgress)
    currentIndexRef.current = Math.floor((newProgress / 100) * (coordinates.length - 1))

    if (canvasRef.current && coordinates.length > 0) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        drawPattern(ctx, coordinates, currentIndexRef.current)
      }
    }
  }

  const handleRunPattern = async () => {
    if (!selectedPattern) return

    setIsRunning(true)
    try {
      await apiClient.post('/run_theta_rho', {
        file_name: selectedPattern.path,
        pre_execution: preExecution,
      })
      toast.success(`Running ${selectedPattern.name}`)
      // Close the preview panel and trigger Now Playing bar to open
      setIsPanelOpen(false)
      window.dispatchEvent(new CustomEvent('playback-started'))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to run pattern'
      if (message.includes('409') || message.includes('already running')) {
        toast.error('Another pattern is already running')
      } else {
        toast.error(message)
      }
    } finally {
      setIsRunning(false)
    }
  }

  const handleDeletePattern = async () => {
    if (!selectedPattern) return

    if (!selectedPattern.path.startsWith('custom_patterns/')) {
      toast.error('Only custom patterns can be deleted')
      return
    }

    if (!confirm(`Delete "${selectedPattern.name}"? This cannot be undone.`)) {
      return
    }

    try {
      await apiClient.post('/delete_theta_rho_file', { file_name: selectedPattern.path })
      toast.success(`Deleted ${selectedPattern.name}`)
      setIsPanelOpen(false)
      setSelectedPattern(null)
      fetchPatterns()
    } catch {
      toast.error('Failed to delete pattern')
    }
  }

  const handleAddToQueue = async (position: 'next' | 'end') => {
    if (!selectedPattern) return

    try {
      await apiClient.post('/add_to_queue', {
        pattern: selectedPattern.path,
        position,
      })
      toast.success(position === 'next' ? 'Playing next' : 'Added to queue')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to add to queue'
      if (message.includes('400') || message.includes('No playlist')) {
        toast.error('No playlist is currently running')
      } else {
        toast.error(message)
      }
    }
  }

  const getPreviewUrl = (path: string) => {
    const preview = previews[path]
    return preview?.image_data || null
  }

  const formatCoordinate = (coord: { x: number; y: number } | null) => {
    if (!coord) return '(-, -)'
    return `(${coord.x.toFixed(1)}, ${coord.y.toFixed(1)})`
  }

  const canDelete = selectedPattern?.path.startsWith('custom_patterns/')

  // Cache all previews handler
  const handleCacheAllPreviews = async () => {
    if (isCaching) return

    setIsCaching(true)
    setCacheProgress(0)

    const result = await cacheAllPreviews((progress) => {
      const percentage = progress.total > 0
        ? Math.round((progress.completed / progress.total) * 100)
        : 0
      setCacheProgress(percentage)
    })

    if (result.success) {
      setAllCached(true)
      if (result.cached === 0) {
        toast.success('All patterns are already cached!')
      } else {
        toast.success('All pattern previews have been cached!')
      }
    } else {
      toast.error('Failed to cache previews')
    }

    setIsCaching(false)
    setCacheProgress(0)
  }

  // Handle pattern file upload
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file extension
    if (!file.name.endsWith('.thr')) {
      toast.error('Please select a .thr file')
      return
    }

    setIsUploading(true)
    try {
      await apiClient.uploadFile('/upload_theta_rho', file)
      toast.success(`Pattern "${file.name}" uploaded successfully`)

      // Refresh patterns list using the same function as initial load
      await fetchPatterns()
    } catch (error) {
      console.error('Upload error:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to upload pattern')
    } finally {
      setIsUploading(false)
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <span className="material-icons-outlined animate-spin text-4xl text-muted-foreground">
          sync
        </span>
      </div>
    )
  }

  return (
    <div className="flex flex-col w-full max-w-5xl mx-auto gap-3 sm:gap-6 py-3 sm:py-6 px-0 sm:px-4">
      {/* Hidden file input for pattern upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".thr"
        onChange={handleFileUpload}
        className="hidden"
      />

      {/* Page Header */}
      <div className="flex items-start justify-between gap-4 pl-1">
        <div className="space-y-0.5">
          <h1 className="text-xl font-semibold tracking-tight">Browse Patterns</h1>
          <p className="text-xs text-muted-foreground">
            {patterns.length} patterns available
          </p>
        </div>
        <Button
          variant="ghost"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="gap-2 shrink-0 h-9 w-9 sm:h-11 sm:w-auto rounded-full px-0 sm:px-4 justify-center bg-card border border-border shadow-sm hover:bg-accent"
        >
          {isUploading ? (
            <span className="material-icons-outlined animate-spin text-lg">sync</span>
          ) : (
            <span className="material-icons-outlined text-lg">add</span>
          )}
          <span className="hidden sm:inline">Add Pattern</span>
        </Button>
      </div>

      {/* Filter Bar */}
      <div
        className="sticky z-30 py-3 -mx-0 sm:-mx-4 px-0 sm:px-4 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60"
        style={{ top: 'calc(4.5rem + env(safe-area-inset-top, 0px))' }}
      >
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Search - Pill shaped, white background */}
          <div className="relative flex-1 min-w-0">
            <span className="material-icons-outlined absolute left-3 sm:left-4 top-1/2 -translate-y-1/2 text-muted-foreground text-lg sm:text-xl">
              search
            </span>
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search..."
              className="pl-9 sm:pl-11 pr-10 h-9 sm:h-11 rounded-full bg-card border-border shadow-sm text-xs sm:text-sm focus:ring-2 focus:ring-ring"
            />
            {searchQuery && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
              >
                <span className="material-icons-outlined text-lg">close</span>
              </Button>
            )}
          </div>

          {/* Category - Icon on mobile, text on desktop */}
          <Select value={selectedCategory} onValueChange={setSelectedCategory}>
            <SelectTrigger className="h-9 w-9 sm:h-11 sm:w-auto rounded-full bg-card border-border shadow-sm text-xs sm:text-sm shrink-0 [&>svg]:hidden sm:[&>svg]:block px-0 sm:px-3 justify-center sm:justify-between [&>span:last-of-type]:hidden sm:[&>span:last-of-type]:inline gap-2">
              <span className="material-icons-outlined text-lg shrink-0 sm:hidden">folder</span>
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              {categories.map((cat) => (
                <SelectItem key={cat} value={cat}>
                  {cat === 'all' ? 'All' : cat === 'root' ? 'Default' : cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Sort - Icon on mobile, text on desktop */}
          <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortOption)}>
            <SelectTrigger className="h-9 w-9 sm:h-11 sm:w-auto rounded-full bg-card border-border shadow-sm text-xs sm:text-sm shrink-0 [&>svg]:hidden sm:[&>svg]:block px-0 sm:px-3 justify-center sm:justify-between [&>span:last-of-type]:hidden sm:[&>span:last-of-type]:inline gap-2">
              <span className="material-icons-outlined text-lg shrink-0 sm:hidden">sort</span>
              <SelectValue placeholder="Sort" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="favorites">Favorites</SelectItem>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="date">Modified</SelectItem>
              <SelectItem value="size">Size</SelectItem>
            </SelectContent>
          </Select>

          {/* Sort direction - Pill shaped, white background */}
          <Button
            variant="outline"
            size="icon"
            onClick={() => setSortAsc(!sortAsc)}
            className="shrink-0 h-9 w-9 sm:h-11 sm:w-11 rounded-full bg-card shadow-sm"
            title={sortAsc ? 'Ascending' : 'Descending'}
          >
            <span className="material-icons-outlined text-lg sm:text-xl">
              {sortAsc ? 'arrow_upward' : 'arrow_downward'}
            </span>
          </Button>

          {/* Cache button - Pill shaped, white background */}
          {!allCached && (
            <Button
              variant="outline"
              onClick={handleCacheAllPreviews}
              className={`shrink-0 rounded-full bg-card shadow-sm gap-2 ${
                isCaching
                  ? 'h-9 sm:h-11 w-auto px-3 sm:px-4'
                  : 'h-9 w-9 sm:h-11 sm:w-auto px-0 sm:px-4 justify-center sm:justify-start'
              }`}
              title="Cache All Previews"
            >
              {isCaching ? (
                <>
                  <span className="material-icons-outlined animate-spin text-lg">sync</span>
                  <span className="text-sm">{cacheProgress}%</span>
                </>
              ) : (
                <>
                  <span className="material-icons-outlined text-lg">cached</span>
                  <span className="hidden sm:inline text-sm">Cache</span>
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {(searchQuery || selectedCategory !== 'all') && (
        <p className="text-sm text-muted-foreground">
          Showing {filteredPatterns.length} of {patterns.length} patterns
        </p>
      )}

      {/* Pattern Grid */}
      {filteredPatterns.length === 0 ? (
        <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4 text-center">
          <div className="p-4 rounded-full bg-muted">
            <span className="material-icons-outlined text-5xl text-muted-foreground">
              search_off
            </span>
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-semibold">No patterns found</h2>
            <p className="text-muted-foreground">Try adjusting your search or filters</p>
          </div>
          {(searchQuery || selectedCategory !== 'all') && (
            <Button
              variant="secondary"
              onClick={() => {
                setSearchQuery('')
                setSelectedCategory('all')
              }}
            >
              Clear Filters
            </Button>
          )}
        </div>
      ) : (
        <PreviewContext.Provider value={{ requestPreview, previews }}>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2 sm:gap-4">
            {filteredPatterns.map((pattern) => (
              <PatternCard
                key={pattern.path}
                pattern={pattern}
                isSelected={selectedPattern?.path === pattern.path}
                isFavorite={favorites.has(pattern.path)}
                playTime={allPatternHistories[pattern.path.split('/').pop() || '']?.actual_time_formatted || null}
                onToggleFavorite={toggleFavorite}
                onClick={() => handlePatternClick(pattern)}
              />
            ))}
          </div>
        </PreviewContext.Provider>
      )}

      <div className="h-48" />

      {/* Pattern Details Sheet */}
      <Sheet open={isPanelOpen} onOpenChange={setIsPanelOpen}>
        <SheetContent
          className="flex flex-col p-0 overflow-hidden pt-safe"
          onTouchStart={handleSheetTouchStart}
          onTouchEnd={handleSheetTouchEnd}
        >
          <SheetHeader className="px-6 py-4 shrink-0">
            <SheetTitle className="flex items-center gap-2 pr-8">
              {selectedPattern && (
                <span
                  role="button"
                  tabIndex={0}
                  className={`shrink-0 transition-colors cursor-pointer flex items-center ${
                    favorites.has(selectedPattern.path) ? 'text-red-500 hover:text-red-600' : 'text-muted-foreground hover:text-red-500'
                  }`}
                  onClick={(e) => toggleFavorite(selectedPattern.path, e)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      toggleFavorite(selectedPattern.path, e as unknown as React.MouseEvent)
                    }
                  }}
                  title={favorites.has(selectedPattern.path) ? 'Remove from favorites' : 'Add to favorites'}
                >
                  <span className="material-icons" style={{ fontSize: '20px' }}>
                    {favorites.has(selectedPattern.path) ? 'favorite' : 'favorite_border'}
                  </span>
                </span>
              )}
              <span className="truncate">{selectedPattern?.name || 'Pattern Details'}</span>
            </SheetTitle>
          </SheetHeader>

          {selectedPattern && (
            <div className="p-6 overflow-y-auto flex-1">
              {/* Clickable Round Preview Image */}
              <div className="mb-6">
                <div
                  className="aspect-square w-full max-w-[280px] mx-auto overflow-hidden rounded-full border bg-muted relative group cursor-pointer"
                  onClick={handleOpenAnimatedPreview}
                >
                  {getPreviewUrl(selectedPattern.path) ? (
                    <img
                      src={getPreviewUrl(selectedPattern.path)!}
                      alt={selectedPattern.name}
                      className="w-full h-full object-cover pattern-preview"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <span className="material-icons-outlined text-4xl text-muted-foreground">
                        image
                      </span>
                    </div>
                  )}
                  {/* Play badge - always visible */}
                  <div className="absolute bottom-2 right-2 bg-background/90 backdrop-blur-sm rounded-full w-10 h-10 flex items-center justify-center shadow-md border group-hover:scale-110 transition-transform">
                    <span className="material-icons text-xl">play_arrow</span>
                  </div>
                  {/* Hover overlay */}
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-black/20 rounded-full" />
                </div>
                <p className="text-xs text-muted-foreground text-center mt-2">Tap to preview animation</p>
              </div>

              {/* Coordinates */}
              <div className="mb-4 flex justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className="material-icons-outlined text-muted-foreground text-base">flag</span>
                  <span className="text-muted-foreground">First:</span>
                  <span className="font-semibold">
                    {formatCoordinate(previews[selectedPattern.path]?.first_coordinate)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="material-icons-outlined text-muted-foreground text-base">check</span>
                  <span className="text-muted-foreground">Last:</span>
                  <span className="font-semibold">
                    {formatCoordinate(previews[selectedPattern.path]?.last_coordinate)}
                  </span>
                </div>
              </div>

              {/* Last Played Info */}
              {patternHistory?.actual_time_formatted && (
                <div className="mb-4 flex justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className="material-icons-outlined text-muted-foreground text-base">schedule</span>
                    <span className="text-muted-foreground">Last run:</span>
                    <span className="font-semibold">{patternHistory.actual_time_formatted}</span>
                  </div>
                  {patternHistory.speed !== null && (
                    <div className="flex items-center gap-2">
                      <span className="material-icons-outlined text-muted-foreground text-base">speed</span>
                      <span className="text-muted-foreground">Speed:</span>
                      <span className="font-semibold">{patternHistory.speed}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Pre-Execution Options */}
              <div className="mb-6">
                <Label className="text-sm font-semibold mb-3 block">Pre-Execution Action</Label>
                <div className="grid grid-cols-2 gap-2">
                  {preExecutionOptions.map((option) => (
                    <label
                      key={option.value}
                      className={`relative flex cursor-pointer items-center justify-center rounded-lg border p-2.5 text-center text-sm font-medium transition-all hover:border-primary ${
                        preExecution === option.value
                          ? 'border-primary bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2 ring-offset-background'
                          : 'border-border text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {option.label}
                      <input
                        type="radio"
                        name="preExecutionAction"
                        value={option.value}
                        checked={preExecution === option.value}
                        onChange={() => setPreExecution(option.value)}
                        className="sr-only"
                      />
                    </label>
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="space-y-3">
                {/* Play + Delete row */}
                <div className="flex gap-2">
                  <Button
                    onClick={handleRunPattern}
                    disabled={isRunning}
                    className="flex-1 gap-2"
                    size="lg"
                  >
                    {isRunning ? (
                      <span className="material-icons-outlined animate-spin text-lg">sync</span>
                    ) : (
                      <span className="material-icons text-lg">play_arrow</span>
                    )}
                    Play
                  </Button>

                  {canDelete && (
                    <Button
                      variant="outline"
                      onClick={handleDeletePattern}
                      className="text-destructive hover:bg-destructive/10 hover:border-destructive px-3"
                      size="lg"
                    >
                      <span className="material-icons text-lg">delete</span>
                    </Button>
                  )}
                </div>

                {/* Queue buttons */}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1 gap-1.5"
                    onClick={() => handleAddToQueue('next')}
                  >
                    <span className="material-icons-outlined text-base">playlist_play</span>
                    Play Next
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1 gap-1.5"
                    onClick={() => handleAddToQueue('end')}
                  >
                    <span className="material-icons-outlined text-base">playlist_add</span>
                    Add to Queue
                  </Button>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Animated Preview Modal */}
      {isAnimatedPreviewOpen && (
        <div
          className="fixed inset-0 bg-black/80 z-[60] flex items-center justify-center p-4"
          onClick={handleCloseAnimatedPreview}
        >
          <div
            className="bg-background rounded-lg shadow-xl max-w-4xl w-full max-h-[95vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b shrink-0">
              <h3 className="text-xl font-semibold">
                {selectedPattern?.name || 'Animated Preview'}
              </h3>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleCloseAnimatedPreview}
                className="rounded-full"
              >
                <span className="material-icons text-2xl">close</span>
              </Button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto flex-1 flex justify-center items-center">
              {isLoadingCoordinates ? (
                <div className="w-full max-w-[400px] aspect-square flex items-center justify-center rounded-full bg-muted">
                  <span className="material-icons-outlined animate-spin text-4xl text-muted-foreground">
                    sync
                  </span>
                </div>
              ) : (
                <div className="relative w-full max-w-[400px] aspect-square">
                  <canvas
                    ref={canvasRef}
                    width={400}
                    height={400}
                    className="rounded-full w-full h-full"
                  />
                  {/* Play/Pause overlay */}
                  <div
                    className="absolute inset-0 flex items-center justify-center cursor-pointer rounded-full opacity-0 hover:opacity-100 transition-opacity bg-black/10"
                    onClick={handlePlayPause}
                  >
                    <div className="bg-background rounded-full w-16 h-16 flex items-center justify-center shadow-lg">
                      <span className="material-icons text-3xl">
                        {isPlaying ? 'pause' : 'play_arrow'}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="p-6 space-y-4 shrink-0 border-t">
              {/* Speed Control */}
              <div>
                <div className="flex justify-between mb-2">
                  <Label className="text-sm font-medium">Speed</Label>
                  <span className="text-sm text-muted-foreground">{speed}x</span>
                </div>
                <Slider
                  value={[speed]}
                  onValueChange={(v) => setSpeed(v[0])}
                  min={0.1}
                  max={5}
                  step={0.1}
                  className="py-2"
                />
              </div>

              {/* Progress Control */}
              <div>
                <div className="flex justify-between mb-2">
                  <Label className="text-sm font-medium">Progress</Label>
                  <span className="text-sm text-muted-foreground">{progress.toFixed(0)}%</span>
                </div>
                <Slider
                  value={[progress]}
                  onValueChange={handleProgressChange}
                  min={0}
                  max={100}
                  step={0.1}
                  className="py-2"
                />
              </div>

              {/* Control Buttons */}
              <div className="flex items-center justify-center gap-4">
                <Button onClick={handlePlayPause} className="gap-2">
                  <span className="material-icons">
                    {isPlaying ? 'pause' : 'play_arrow'}
                  </span>
                  {isPlaying ? 'Pause' : 'Play'}
                </Button>
                <Button variant="secondary" onClick={handleReset} className="gap-2">
                  <span className="material-icons">replay</span>
                  Reset
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Pattern Card Component
interface PatternCardProps {
  pattern: PatternMetadata
  isSelected: boolean
  isFavorite: boolean
  playTime: string | null
  onToggleFavorite: (path: string, e: React.MouseEvent) => void
  onClick: () => void
}

function PatternCard({ pattern, isSelected, isFavorite, playTime, onToggleFavorite, onClick }: PatternCardProps) {
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const cardRef = useRef<HTMLButtonElement>(null)
  const context = useContext(PreviewContext)

  // Request preview when card becomes visible
  useEffect(() => {
    if (!context || !cardRef.current) return

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            context.requestPreview(pattern.path)
            observer.disconnect() // Only need to load once
          }
        })
      },
      { rootMargin: '100px' } // Start loading slightly before visible
    )

    observer.observe(cardRef.current)

    return () => observer.disconnect()
  }, [pattern.path, context])

  const previewUrl = context?.previews[pattern.path]?.image_data || null

  return (
    <button
      ref={cardRef}
      onClick={onClick}
      className={`group flex flex-col items-center gap-2 p-2.5 rounded-xl bg-card border border-border transition-all duration-200 ease-out hover:-translate-y-1 hover:shadow-md active:scale-95 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
        isSelected ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : ''
      }`}
    >
      <div className="relative w-full aspect-square">
        <div className="w-full h-full rounded-full overflow-hidden border border-border bg-muted">
          {previewUrl && !imageError ? (
            <>
              {!imageLoaded && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="material-icons-outlined animate-spin text-xl text-muted-foreground">
                    sync
                  </span>
                </div>
              )}
              <img
                src={previewUrl}
                alt={pattern.name}
                className={`w-full h-full object-cover pattern-preview transition-opacity ${
                  imageLoaded ? 'opacity-100' : 'opacity-0'
                }`}
                loading="lazy"
                onLoad={() => setImageLoaded(true)}
                onError={() => setImageError(true)}
              />
            </>
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <span className="material-icons-outlined text-2xl text-muted-foreground">
                {imageError ? 'broken_image' : 'image'}
              </span>
            </div>
          )}
        </div>

        {/* Play time badge */}
        {playTime && (
          <div className="absolute -top-1 -right-1 bg-card/90 backdrop-blur-sm text-[10px] font-medium px-1.5 py-0.5 rounded-full border border-border shadow-sm">
            {(() => {
              // Parse time and convert to minutes only
              // Try MM:SS or HH:MM:SS format first (e.g., "15:48" or "1:15:48")
              const colonMatch = playTime.match(/^(?:(\d+):)?(\d+):(\d+)$/)
              if (colonMatch) {
                const hours = colonMatch[1] ? parseInt(colonMatch[1]) : 0
                const minutes = parseInt(colonMatch[2])
                const seconds = parseInt(colonMatch[3])
                const totalMins = hours * 60 + minutes + (seconds >= 30 ? 1 : 0)
                return totalMins > 0 ? `${totalMins}m` : '<1m'
              }

              // Try text-based formats
              const match = playTime.match(/(\d+)h\s*(\d+)m|(\d+)\s*min|(\d+)m\s*(\d+)s|(\d+)\s*sec/)
              if (match) {
                if (match[1] && match[2]) {
                  // "Xh Ym" format
                  return `${parseInt(match[1]) * 60 + parseInt(match[2])}m`
                } else if (match[3]) {
                  // "X min" format
                  return `${match[3]}m`
                } else if (match[4] && match[5]) {
                  // "Xm Ys" format - round to minutes
                  const mins = parseInt(match[4])
                  return mins > 0 ? `${mins}m` : '<1m'
                } else if (match[6]) {
                  // seconds only
                  return '<1m'
                }
              }
              // Fallback: show original
              return playTime
            })()}
          </div>
        )}
      </div>

      {/* Name and favorite row */}
      <div className="flex items-center justify-between w-full gap-1 px-0.5">
        <span className="text-xs font-bold text-foreground truncate" title={pattern.name}>
          {pattern.name}
        </span>
        <span
          role="button"
          tabIndex={0}
          className={`shrink-0 transition-colors cursor-pointer ${
            isFavorite ? 'text-red-500 hover:text-red-600' : 'text-muted-foreground hover:text-red-500'
          }`}
          onClick={(e) => {
            e.stopPropagation()
            onToggleFavorite(pattern.path, e)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              e.stopPropagation()
              onToggleFavorite(pattern.path, e as unknown as React.MouseEvent)
            }
          }}
          title={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
        >
          <span className="material-icons" style={{ fontSize: '16px' }}>
            {isFavorite ? 'favorite' : 'favorite_border'}
          </span>
        </span>
      </div>
    </button>
  )
}
