import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import {
  initPreviewCacheDB,
  getPreviewsFromCache,
  savePreviewToCache,
} from '@/lib/previewCache'
import { fuzzyMatch } from '@/lib/utils'
import { useOnBackendConnected } from '@/hooks/useBackendConnection'
import type { PatternMetadata, PreviewData, SortOption, PreExecution, RunMode } from '@/lib/types'
import { preExecutionOptions } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'

export function PlaylistsPage() {
  // Playlists state
  const [playlists, setPlaylists] = useState<string[]>([])
  const [selectedPlaylist, setSelectedPlaylist] = useState<string | null>(() => {
    return localStorage.getItem('playlist-selected')
  })
  const [playlistPatterns, setPlaylistPatterns] = useState<string[]>([])
  const [isLoadingPlaylists, setIsLoadingPlaylists] = useState(true)

  // All patterns for the picker modal
  const [allPatterns, setAllPatterns] = useState<PatternMetadata[]>([])
  const [previews, setPreviews] = useState<Record<string, PreviewData>>({})

  // Pattern picker modal state
  const [isPickerOpen, setIsPickerOpen] = useState(false)
  const [selectedPatternPaths, setSelectedPatternPaths] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [sortBy, setSortBy] = useState<SortOption>('name')
  const [sortAsc, setSortAsc] = useState(true)

  // Create/Rename playlist modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false)
  const [newPlaylistName, setNewPlaylistName] = useState('')
  const [playlistToRename, setPlaylistToRename] = useState<string | null>(null)

  // Playback settings - initialized from localStorage
  const [runMode, setRunMode] = useState<RunMode>(() => {
    const cached = localStorage.getItem('playlist-runMode')
    return (cached === 'single' || cached === 'indefinite') ? cached : 'single'
  })
  const [shuffle, setShuffle] = useState(() => {
    return localStorage.getItem('playlist-shuffle') === 'true'
  })
  const [pauseTime, setPauseTime] = useState(() => {
    const cached = localStorage.getItem('playlist-pauseTime')
    return cached ? Number(cached) : 5
  })
  const [pauseUnit, setPauseUnit] = useState<'sec' | 'min' | 'hr'>(() => {
    const cached = localStorage.getItem('playlist-pauseUnit')
    return (cached === 'sec' || cached === 'min' || cached === 'hr') ? cached : 'min'
  })
  const [clearPattern, setClearPattern] = useState<PreExecution>(() => {
    const cached = localStorage.getItem('playlist-clearPattern')
    return (cached as PreExecution) || 'adaptive'
  })

  // Persist playback settings to localStorage
  useEffect(() => {
    localStorage.setItem('playlist-runMode', runMode)
  }, [runMode])
  useEffect(() => {
    localStorage.setItem('playlist-shuffle', String(shuffle))
  }, [shuffle])
  useEffect(() => {
    localStorage.setItem('playlist-pauseTime', String(pauseTime))
  }, [pauseTime])
  useEffect(() => {
    localStorage.setItem('playlist-pauseUnit', pauseUnit)
  }, [pauseUnit])
  useEffect(() => {
    localStorage.setItem('playlist-clearPattern', clearPattern)
  }, [clearPattern])

  // Persist selected playlist to localStorage
  useEffect(() => {
    if (selectedPlaylist) {
      localStorage.setItem('playlist-selected', selectedPlaylist)
    } else {
      localStorage.removeItem('playlist-selected')
    }
  }, [selectedPlaylist])

  // Validate cached playlist exists and load its patterns after playlists load
  const initialLoadDoneRef = useRef(false)
  useEffect(() => {
    if (isLoadingPlaylists) return

    if (selectedPlaylist) {
      if (playlists.includes(selectedPlaylist)) {
        // Load patterns for cached playlist on initial load only
        if (!initialLoadDoneRef.current) {
          initialLoadDoneRef.current = true
          fetchPlaylistPatterns(selectedPlaylist)
        }
      } else {
        // Cached playlist no longer exists
        setSelectedPlaylist(null)
      }
    }
  }, [isLoadingPlaylists, playlists, selectedPlaylist])

  // Close modals when playback starts
  useEffect(() => {
    const handlePlaybackStarted = () => {
      setIsPickerOpen(false)
      setIsCreateModalOpen(false)
      setIsRenameModalOpen(false)
    }
    window.addEventListener('playback-started', handlePlaybackStarted)
    return () => window.removeEventListener('playback-started', handlePlaybackStarted)
  }, [])
  const [isRunning, setIsRunning] = useState(false)

  // Convert pause time to seconds based on unit
  const getPauseTimeInSeconds = () => {
    switch (pauseUnit) {
      case 'hr':
        return pauseTime * 3600
      case 'min':
        return pauseTime * 60
      default:
        return pauseTime
    }
  }

  // Preview loading
  const pendingPreviewsRef = useRef<Set<string>>(new Set())
  const batchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Initialize and fetch data
  useEffect(() => {
    initPreviewCacheDB().catch(() => {})
    fetchPlaylists()
    fetchAllPatterns()

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
    fetchPlaylists()
    fetchAllPatterns()
  })

  const fetchPlaylists = async () => {
    setIsLoadingPlaylists(true)
    try {
      const data = await apiClient.get<string[]>('/list_all_playlists')
      // Backend returns array directly, not { playlists: [...] }
      setPlaylists(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Error fetching playlists:', error)
      toast.error('Failed to load playlists')
    } finally {
      setIsLoadingPlaylists(false)
    }
  }

  const fetchPlaylistPatterns = async (name: string) => {
    try {
      const data = await apiClient.get<{ files: string[] }>(`/get_playlist?name=${encodeURIComponent(name)}`)
      setPlaylistPatterns(data.files || [])

      // Load previews for playlist patterns
      if (data.files?.length > 0) {
        loadPreviewsForPaths(data.files)
      }
    } catch (error) {
      console.error('Error fetching playlist:', error)
      toast.error('Failed to load playlist')
      setPlaylistPatterns([])
    }
  }

  const fetchAllPatterns = async () => {
    try {
      const data = await apiClient.get<PatternMetadata[]>('/list_theta_rho_files_with_metadata')
      setAllPatterns(data)
    } catch (error) {
      console.error('Error fetching patterns:', error)
    }
  }

  // Preview loading functions (similar to BrowsePage)
  const loadPreviewsForPaths = async (paths: string[]) => {
    const cachedPreviews = await getPreviewsFromCache(paths)

    if (cachedPreviews.size > 0) {
      const cachedData: Record<string, PreviewData> = {}
      cachedPreviews.forEach((previewData, path) => {
        cachedData[path] = previewData
      })
      setPreviews(prev => ({ ...prev, ...cachedData }))
    }

    const uncached = paths.filter(p => !cachedPreviews.has(p))
    if (uncached.length > 0) {
      fetchPreviewsBatch(uncached)
    }
  }

  const fetchPreviewsBatch = async (paths: string[]) => {
    const BATCH_SIZE = 10 // Process 10 patterns at a time to avoid overwhelming the backend

    // Create new AbortController for this batch of requests
    abortControllerRef.current = new AbortController()
    const signal = abortControllerRef.current.signal

    // Process in batches
    for (let i = 0; i < paths.length; i += BATCH_SIZE) {
      // Check if aborted before each batch
      if (signal.aborted) break

      const batch = paths.slice(i, i + BATCH_SIZE)

      try {
        const data = await apiClient.post<Record<string, PreviewData>>('/preview_thr_batch', { file_names: batch }, signal)

        const newPreviews: Record<string, PreviewData> = {}
        for (const [path, previewData] of Object.entries(data)) {
          newPreviews[path] = previewData as PreviewData
          // Only cache valid previews (with image_data and no error)
          if (previewData && !(previewData as PreviewData).error) {
            savePreviewToCache(path, previewData as PreviewData)
          }
        }
        setPreviews(prev => ({ ...prev, ...newPreviews }))
      } catch (error) {
        // Stop processing if aborted, otherwise continue with next batch
        if (error instanceof Error && error.name === 'AbortError') break
        console.error('Error fetching previews batch:', error)
      }

      // Small delay between batches to reduce backend load
      if (i + BATCH_SIZE < paths.length) {
        await new Promise((resolve) => setTimeout(resolve, 100))
      }
    }
  }

  const requestPreview = useCallback((path: string) => {
    if (previews[path] || pendingPreviewsRef.current.has(path)) return

    pendingPreviewsRef.current.add(path)

    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current)
    }

    batchTimeoutRef.current = setTimeout(() => {
      const pathsToFetch = Array.from(pendingPreviewsRef.current)
      pendingPreviewsRef.current.clear()
      if (pathsToFetch.length > 0) {
        loadPreviewsForPaths(pathsToFetch)
      }
    }, 100)
  }, [previews])

  // Playlist CRUD operations
  const handleSelectPlaylist = (name: string) => {
    setSelectedPlaylist(name)
    fetchPlaylistPatterns(name)
  }

  const handleCreatePlaylist = async () => {
    if (!newPlaylistName.trim()) {
      toast.error('Please enter a playlist name')
      return
    }

    const name = newPlaylistName.trim()
    try {
      await apiClient.post('/create_playlist', { playlist_name: name, files: [] })
      toast.success('Playlist created')
      setIsCreateModalOpen(false)
      setNewPlaylistName('')
      await fetchPlaylists()
      handleSelectPlaylist(name)
    } catch (error) {
      console.error('Create playlist error:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to create playlist')
    }
  }

  const handleRenamePlaylist = async () => {
    if (!playlistToRename || !newPlaylistName.trim()) return

    try {
      await apiClient.post('/rename_playlist', { old_name: playlistToRename, new_name: newPlaylistName.trim() })
      toast.success('Playlist renamed')
      setIsRenameModalOpen(false)
      setNewPlaylistName('')
      setPlaylistToRename(null)
      fetchPlaylists()
      if (selectedPlaylist === playlistToRename) {
        setSelectedPlaylist(newPlaylistName.trim())
      }
    } catch (error) {
      toast.error('Failed to rename playlist')
    }
  }

  const handleDeletePlaylist = async (name: string) => {
    if (!confirm(`Delete playlist "${name}"?`)) return

    try {
      await apiClient.delete('/delete_playlist', { playlist_name: name })
      toast.success('Playlist deleted')
      fetchPlaylists()
      if (selectedPlaylist === name) {
        setSelectedPlaylist(null)
        setPlaylistPatterns([])
      }
    } catch (error) {
      toast.error('Failed to delete playlist')
    }
  }

  const handleRemovePattern = async (patternPath: string) => {
    if (!selectedPlaylist) return

    const newPatterns = playlistPatterns.filter(p => p !== patternPath)
    try {
      await apiClient.post('/modify_playlist', { playlist_name: selectedPlaylist, files: newPatterns })
      setPlaylistPatterns(newPatterns)
      toast.success('Pattern removed')
    } catch (error) {
      toast.error('Failed to remove pattern')
    }
  }

  // Pattern picker modal
  const openPatternPicker = () => {
    setSelectedPatternPaths(new Set(playlistPatterns))
    setSearchQuery('')
    setIsPickerOpen(true)

    // Load previews for all patterns
    if (allPatterns.length > 0) {
      const paths = allPatterns.slice(0, 50).map(p => p.path)
      loadPreviewsForPaths(paths)
    }
  }

  const handleSavePatterns = async () => {
    if (!selectedPlaylist) return

    const newPatterns = Array.from(selectedPatternPaths)
    try {
      await apiClient.post('/modify_playlist', { playlist_name: selectedPlaylist, files: newPatterns })
      setPlaylistPatterns(newPatterns)
      setIsPickerOpen(false)
      toast.success('Playlist updated')
      loadPreviewsForPaths(newPatterns)
    } catch (error) {
      toast.error('Failed to update playlist')
    }
  }

  const togglePatternSelection = (path: string) => {
    setSelectedPatternPaths(prev => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  // Run playlist
  const handleRunPlaylist = async () => {
    if (!selectedPlaylist || playlistPatterns.length === 0) return

    setIsRunning(true)
    try {
      await apiClient.post('/run_playlist', {
        playlist_name: selectedPlaylist,
        run_mode: runMode === 'indefinite' ? 'indefinite' : 'single',
        pause_time: getPauseTimeInSeconds(),
        clear_pattern: clearPattern,
        shuffle: shuffle,
      })
      toast.success(`Started playlist: ${selectedPlaylist}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to run playlist')
    } finally {
      setIsRunning(false)
    }
  }

  // Filter and sort patterns for picker
  const categories = useMemo(() => {
    const cats = new Set(allPatterns.map(p => p.category))
    return ['all', ...Array.from(cats).sort()]
  }, [allPatterns])

  const filteredPatterns = useMemo(() => {
    let filtered = allPatterns

    if (searchQuery) {
      filtered = filtered.filter(p => fuzzyMatch(p.name, searchQuery))
    }

    if (selectedCategory !== 'all') {
      filtered = filtered.filter(p => p.category === selectedCategory)
    }

    filtered = [...filtered].sort((a, b) => {
      let cmp = 0
      switch (sortBy) {
        case 'name':
          cmp = a.name.localeCompare(b.name)
          break
        case 'date':
          cmp = a.date_modified - b.date_modified
          break
        case 'category':
          cmp = a.category.localeCompare(b.category)
          break
      }
      return sortAsc ? cmp : -cmp
    })

    return filtered
  }, [allPatterns, searchQuery, selectedCategory, sortBy, sortAsc])

  // Get pattern name from path
  const getPatternName = (path: string) => {
    const pattern = allPatterns.find(p => p.path === path)
    return pattern?.name || path.split('/').pop()?.replace('.thr', '') || path
  }

  // Get preview URL (backend already returns full data URL)
  const getPreviewUrl = (path: string) => {
    const preview = previews[path]
    return preview?.image_data || null
  }

  return (
    <div className="flex flex-col w-full max-w-5xl mx-auto gap-4 sm:gap-6 py-4 sm:py-6 h-[calc(100dvh-10rem)] sm:h-[calc(100dvh-10.5rem)] overflow-hidden">
      {/* Page Header */}
      <div className="space-y-0.5 sm:space-y-1 shrink-0">
        <h1 className="text-xl sm:text-3xl font-bold tracking-tight">Playlists</h1>
        <p className="text-sm sm:text-base text-muted-foreground">
          Create and manage pattern playlists
        </p>
      </div>

      <Separator className="shrink-0" />

      {/* Main Content Area */}
      <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">
        {/* Playlists Sidebar */}
        <aside className="w-full lg:w-64 shrink-0 bg-card border rounded-lg flex flex-col max-h-48 lg:max-h-none">
          <div className="flex items-center justify-between px-3 py-2.5 border-b shrink-0">
            <h2 className="text-lg font-semibold">My Playlists</h2>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => {
                setNewPlaylistName('')
                setIsCreateModalOpen(true)
              }}
            >
              <span className="material-icons-outlined text-xl">add</span>
            </Button>
          </div>

          <nav className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
          {isLoadingPlaylists ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <span className="text-sm">Loading...</span>
            </div>
          ) : playlists.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground gap-2">
              <span className="material-icons-outlined text-3xl">playlist_add</span>
              <span className="text-sm">No playlists yet</span>
            </div>
          ) : (
            playlists.map(name => (
              <div
                key={name}
                className={`group flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer transition-colors ${
                  selectedPlaylist === name
                    ? 'bg-accent text-accent-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                }`}
                onClick={() => handleSelectPlaylist(name)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="material-icons-outlined text-lg">playlist_play</span>
                  <span className="truncate text-sm font-medium">{name}</span>
                </div>
                <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="h-7 w-7"
                    onClick={(e) => {
                      e.stopPropagation()
                      setPlaylistToRename(name)
                      setNewPlaylistName(name)
                      setIsRenameModalOpen(true)
                    }}
                  >
                    <span className="material-icons-outlined text-base">edit</span>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/20"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDeletePlaylist(name)
                    }}
                  >
                    <span className="material-icons-outlined text-base">delete</span>
                  </Button>
                </div>
              </div>
            ))
          )}
        </nav>
      </aside>

        {/* Main Content */}
        <main className="flex-1 bg-card border rounded-lg flex flex-col overflow-hidden min-h-0">
          {/* Header */}
          <header className="flex items-center justify-between px-4 py-3 border-b shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold truncate">
                  {selectedPlaylist || 'Select a Playlist'}
                </h2>
                {selectedPlaylist && playlistPatterns.length > 0 && (
                  <p className="text-sm text-muted-foreground">
                    {playlistPatterns.length} pattern{playlistPatterns.length !== 1 ? 's' : ''}
                  </p>
                )}
              </div>
            </div>
            <Button
              onClick={openPatternPicker}
              disabled={!selectedPlaylist}
              size="sm"
              className="gap-2"
            >
              <span className="material-icons-outlined text-base">add</span>
              <span className="hidden sm:inline">Add Patterns</span>
            </Button>
          </header>

          {/* Patterns List */}
          <div className="flex-1 overflow-y-auto p-4 min-h-0">
            {!selectedPlaylist ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
                <div className="p-4 rounded-full bg-muted">
                  <span className="material-icons-outlined text-5xl">touch_app</span>
                </div>
                <div className="text-center">
                  <p className="font-medium">No playlist selected</p>
                  <p className="text-sm">Select a playlist from the sidebar to view its patterns</p>
                </div>
              </div>
            ) : playlistPatterns.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
                <div className="p-4 rounded-full bg-muted">
                  <span className="material-icons-outlined text-5xl">library_music</span>
                </div>
                <div className="text-center">
                  <p className="font-medium">Empty playlist</p>
                  <p className="text-sm">Add patterns to get started</p>
                </div>
                <Button variant="outline" className="mt-2 gap-2" onClick={openPatternPicker}>
                  <span className="material-icons-outlined text-base">add</span>
                  Add Patterns
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 sm:gap-4">
                {playlistPatterns.map((path, index) => {
                  const previewUrl = getPreviewUrl(path)
                  if (!previewUrl && !previews[path]) {
                    requestPreview(path)
                  }
                  return (
                    <div
                      key={`${path}-${index}`}
                      className="flex flex-col items-center gap-1.5 sm:gap-2 group"
                    >
                      <div className="relative w-full aspect-square">
                        <div className="w-full h-full rounded-full overflow-hidden border bg-muted hover:ring-2 hover:ring-primary hover:ring-offset-2 hover:ring-offset-background transition-all cursor-pointer">
                          {previewUrl ? (
                            <img
                              src={previewUrl}
                              alt={getPatternName(path)}
                              className="w-full h-full object-cover pattern-preview"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <span className="material-icons-outlined text-muted-foreground text-sm sm:text-base">
                                image
                              </span>
                            </div>
                          )}
                        </div>
                        <button
                          className="absolute -top-0.5 -right-0.5 sm:-top-1 sm:-right-1 w-5 h-5 rounded-full bg-destructive hover:bg-destructive/90 text-destructive-foreground flex items-center justify-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity shadow-sm z-10"
                          onClick={() => handleRemovePattern(path)}
                          title="Remove from playlist"
                        >
                          <span className="material-icons" style={{ fontSize: '12px' }}>close</span>
                        </button>
                      </div>
                      <p className="text-[10px] sm:text-xs truncate font-medium w-full text-center">{getPatternName(path)}</p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Playback Settings - Always visible when playlist selected */}
          {selectedPlaylist && (
            <div className="border-t px-3 py-2.5 sm:px-4 sm:py-3 bg-muted/30 shrink-0">
              {/* Mobile: 2-row layout, Desktop: single row */}
              <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 sm:gap-3">
                {/* Top row on mobile: Mode, Shuffle, Pause, Clear */}
                <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                  {/* Run Mode Segmented Control */}
                  <div className="flex rounded-md border bg-muted/50 p-0.5">
                    <button
                      onClick={() => setRunMode('single')}
                      className={`flex items-center gap-1 px-2 py-1 rounded text-xs sm:text-sm font-medium transition-colors ${
                        runMode === 'single'
                          ? 'bg-background text-foreground shadow-sm'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <span className="material-icons-outlined text-sm">play_circle</span>
                      Once
                    </button>
                    <button
                      onClick={() => setRunMode('indefinite')}
                      className={`flex items-center gap-1 px-2 py-1 rounded text-xs sm:text-sm font-medium transition-colors ${
                        runMode === 'indefinite'
                          ? 'bg-background text-foreground shadow-sm'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <span className="material-icons-outlined text-sm">repeat</span>
                      Loop
                    </button>
                  </div>

                  {/* Shuffle Toggle */}
                  <div className="flex items-center gap-1.5 h-8 px-2 rounded-md border bg-muted/50">
                    <span className="material-icons-outlined text-sm text-muted-foreground">shuffle</span>
                    <Switch
                      checked={shuffle}
                      onCheckedChange={setShuffle}
                      className="scale-90"
                    />
                  </div>

                  {/* Pause Time - more compact on mobile */}
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-muted-foreground hidden sm:inline">Pause:</Label>
                    <Input
                      type="number"
                      value={pauseTime}
                      onChange={(e) => setPauseTime(Number(e.target.value))}
                      min={0}
                      className="w-12 sm:w-14 h-8 text-sm"
                    />
                    <Select value={pauseUnit} onValueChange={(v) => setPauseUnit(v as 'sec' | 'min' | 'hr')}>
                      <SelectTrigger className="h-8 w-14 sm:w-16 text-xs sm:text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="sec">sec</SelectItem>
                        <SelectItem value="min">min</SelectItem>
                        <SelectItem value="hr">hr</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Clear Pattern */}
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-muted-foreground hidden sm:inline">Clear:</Label>
                    <Select value={clearPattern} onValueChange={(v) => setClearPattern(v as PreExecution)}>
                      <SelectTrigger className="h-8 w-24 sm:w-28 text-xs sm:text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {preExecutionOptions.map(opt => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Spacer - only on desktop */}
                <div className="hidden sm:flex sm:flex-1" />

                {/* Run Button - full width on mobile */}
                <Button
                  className="gap-2 w-full sm:w-auto"
                  onClick={handleRunPlaylist}
                  disabled={isRunning || playlistPatterns.length === 0}
                >
                  {isRunning ? (
                    <span className="material-icons-outlined animate-spin">sync</span>
                  ) : (
                    <span className="material-icons-outlined">play_arrow</span>
                  )}
                  Run Playlist
                </Button>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Create Playlist Modal */}
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="material-icons-outlined text-primary">playlist_add</span>
              Create New Playlist
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="playlistName">Playlist Name</Label>
              <Input
                id="playlistName"
                value={newPlaylistName}
                onChange={(e) => setNewPlaylistName(e.target.value)}
                placeholder="e.g., Favorites, Morning Patterns..."
                onKeyDown={(e) => e.key === 'Enter' && handleCreatePlaylist()}
                autoFocus
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setIsCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreatePlaylist} className="gap-2">
              <span className="material-icons-outlined text-base">add</span>
              Create Playlist
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename Playlist Modal */}
      <Dialog open={isRenameModalOpen} onOpenChange={setIsRenameModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="material-icons-outlined text-primary">edit</span>
              Rename Playlist
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="renamePlaylist">New Name</Label>
              <Input
                id="renamePlaylist"
                value={newPlaylistName}
                onChange={(e) => setNewPlaylistName(e.target.value)}
                placeholder="Enter new name"
                onKeyDown={(e) => e.key === 'Enter' && handleRenamePlaylist()}
                autoFocus
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setIsRenameModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRenamePlaylist} className="gap-2">
              <span className="material-icons-outlined text-base">save</span>
              Save Name
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Pattern Picker Modal */}
      <Dialog open={isPickerOpen} onOpenChange={setIsPickerOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="material-icons-outlined text-primary">playlist_add</span>
              Add Patterns to {selectedPlaylist}
            </DialogTitle>
          </DialogHeader>

          {/* Search and Filters */}
          <div className="space-y-3 py-2">
            <div className="relative">
              <span className="material-icons-outlined absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-lg">
                search
              </span>
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search patterns..."
                className="pl-10 pr-10 h-10"
              />
              {searchQuery && (
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setSearchQuery('')}
                >
                  <span className="material-icons-outlined text-lg">close</span>
                </button>
              )}
            </div>

            <div className="flex flex-wrap gap-3 items-center p-3 rounded-lg bg-muted/50">
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Sort:</Label>
                <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortOption)}>
                  <SelectTrigger className="h-8 w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="name">Name</SelectItem>
                    <SelectItem value="date">Date</SelectItem>
                    <SelectItem value="category">Category</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setSortAsc(!sortAsc)}
                >
                  <span className="material-icons-outlined text-lg">
                    {sortAsc ? 'arrow_upward' : 'arrow_downward'}
                  </span>
                </Button>
              </div>

              <Separator orientation="vertical" className="h-6" />

              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Folder:</Label>
                <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                  <SelectTrigger className="h-8 w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.map(cat => (
                      <SelectItem key={cat} value={cat}>
                        {cat === 'all' ? 'All Folders' : cat}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1" />

              <div className="flex items-center gap-2 text-sm">
                <span className="material-icons-outlined text-base text-primary">check_circle</span>
                <span className="font-medium">{selectedPatternPaths.size}</span>
                <span className="text-muted-foreground">selected</span>
              </div>
            </div>
          </div>

          {/* Patterns Grid */}
          <div className="flex-1 overflow-y-auto border rounded-lg p-4 min-h-[300px] bg-muted/20">
            {filteredPatterns.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
                <div className="p-4 rounded-full bg-muted">
                  <span className="material-icons-outlined text-5xl">search_off</span>
                </div>
                <span className="text-sm">No patterns found</span>
              </div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-4">
                {filteredPatterns.map(pattern => {
                  const isSelected = selectedPatternPaths.has(pattern.path)
                  const previewUrl = getPreviewUrl(pattern.path)
                  if (!previewUrl && !previews[pattern.path]) {
                    requestPreview(pattern.path)
                  }
                  return (
                    <div
                      key={pattern.path}
                      className="flex flex-col items-center gap-2 cursor-pointer"
                      onClick={() => togglePatternSelection(pattern.path)}
                    >
                      <div
                        className={`relative w-full aspect-square rounded-full overflow-hidden border-2 bg-muted transition-all ${
                          isSelected
                            ? 'border-primary ring-2 ring-primary/20'
                            : 'border-transparent hover:border-muted-foreground/30'
                        }`}
                      >
                        {previewUrl ? (
                          <img
                            src={previewUrl}
                            alt={pattern.name}
                            className="w-full h-full object-cover pattern-preview"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <span className="material-icons-outlined text-muted-foreground">
                              image
                            </span>
                          </div>
                        )}
                        {isSelected && (
                          <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-primary flex items-center justify-center shadow-md">
                            <span className="material-icons text-primary-foreground" style={{ fontSize: '14px' }}>
                              check
                            </span>
                          </div>
                        )}
                      </div>
                      <p className={`text-xs truncate font-medium w-full text-center ${isSelected ? 'text-primary' : ''}`}>
                        {pattern.name}
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setIsPickerOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSavePatterns} className="gap-2">
              <span className="material-icons-outlined text-base">save</span>
              Save Selection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
