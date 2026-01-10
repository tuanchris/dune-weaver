// IndexedDB cache for preview images - matches original implementation
const PREVIEW_CACHE_DB_NAME = 'dune_weaver_previews'
const PREVIEW_CACHE_DB_VERSION = 1
const PREVIEW_CACHE_STORE_NAME = 'previews'
const MAX_CACHE_SIZE_MB = 200
const MAX_CACHE_SIZE_BYTES = MAX_CACHE_SIZE_MB * 1024 * 1024

interface PreviewData {
  image_data: string
  first_coordinate: { x: number; y: number } | null
  last_coordinate: { x: number; y: number } | null
  error?: string
}

interface CacheEntry {
  pattern: string
  data: PreviewData
  size: number
  lastAccessed: number
  created: number
}

let previewCacheDB: IDBDatabase | null = null

// In-memory cache for faster access during session
const memoryCache = new Map<string, PreviewData>()
const MAX_MEMORY_CACHE_SIZE = 100

// Initialize IndexedDB
export async function initPreviewCacheDB(): Promise<IDBDatabase> {
  if (previewCacheDB) return previewCacheDB

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(PREVIEW_CACHE_DB_NAME, PREVIEW_CACHE_DB_VERSION)

    request.onerror = () => {
      console.error('Failed to open preview cache database')
      reject(request.error)
    }

    request.onsuccess = () => {
      previewCacheDB = request.result
      console.debug('Preview cache database opened successfully')
      resolve(previewCacheDB)
    }

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result

      // Create object store for preview cache
      const store = db.createObjectStore(PREVIEW_CACHE_STORE_NAME, { keyPath: 'pattern' })
      store.createIndex('lastAccessed', 'lastAccessed', { unique: false })
      store.createIndex('size', 'size', { unique: false })

      console.debug('Preview cache database schema created')
    }
  })
}

// Get preview from cache (memory first, then IndexedDB)
export async function getPreviewFromCache(pattern: string): Promise<PreviewData | null> {
  // Check memory cache first
  if (memoryCache.has(pattern)) {
    return memoryCache.get(pattern)!
  }

  // Check IndexedDB
  try {
    if (!previewCacheDB) await initPreviewCacheDB()

    const transaction = previewCacheDB!.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite')
    const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME)

    return new Promise((resolve, reject) => {
      const request = store.get(pattern)

      request.onsuccess = () => {
        const result = request.result as CacheEntry | undefined
        if (result) {
          // Update last accessed time
          result.lastAccessed = Date.now()
          store.put(result)

          // Add to memory cache
          addToMemoryCache(pattern, result.data)

          resolve(result.data)
        } else {
          resolve(null)
        }
      }

      request.onerror = () => reject(request.error)
    })
  } catch (error) {
    console.warn(`Error getting preview from cache: ${error}`)
    return null
  }
}

// Add to memory cache with size limit
function addToMemoryCache(pattern: string, data: PreviewData) {
  if (memoryCache.size >= MAX_MEMORY_CACHE_SIZE) {
    // Remove oldest entry (first key)
    const oldestKey = memoryCache.keys().next().value
    if (oldestKey) {
      memoryCache.delete(oldestKey)
    }
  }
  memoryCache.set(pattern, data)
}

// Save preview to IndexedDB cache with size management
export async function savePreviewToCache(pattern: string, previewData: PreviewData): Promise<void> {
  try {
    if (!previewData || !previewData.image_data) {
      console.warn(`Invalid preview data for ${pattern}, skipping cache save`)
      return
    }

    if (!previewCacheDB) await initPreviewCacheDB()

    // Add to memory cache
    addToMemoryCache(pattern, previewData)

    // Calculate size from base64 data
    const size = Math.ceil((previewData.image_data.length * 3) / 4)

    // Check if we need to free up space
    await managePreviewCacheSize(size)

    const cacheEntry: CacheEntry = {
      pattern: pattern,
      data: previewData,
      size: size,
      lastAccessed: Date.now(),
      created: Date.now(),
    }

    const transaction = previewCacheDB!.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite')
    const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME)

    return new Promise((resolve, reject) => {
      const request = store.put(cacheEntry)

      request.onsuccess = () => {
        console.debug(`Preview cached for ${pattern} (${(size / 1024).toFixed(1)}KB)`)
        resolve()
      }

      request.onerror = () => reject(request.error)
    })
  } catch (error) {
    console.warn(`Error saving preview to cache: ${error}`)
  }
}

// Get current cache size
async function getPreviewCacheSize(): Promise<number> {
  try {
    if (!previewCacheDB) return 0

    const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readonly')
    const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME)

    return new Promise((resolve, reject) => {
      const request = store.getAll()

      request.onsuccess = () => {
        const totalSize = request.result.reduce(
          (sum: number, entry: CacheEntry) => sum + (entry.size || 0),
          0
        )
        resolve(totalSize)
      }

      request.onerror = () => reject(request.error)
    })
  } catch (error) {
    console.warn(`Error getting cache size: ${error}`)
    return 0
  }
}

// Manage cache size by removing least recently used items (LRU eviction)
async function managePreviewCacheSize(newItemSize: number): Promise<void> {
  try {
    const currentSize = await getPreviewCacheSize()

    if (currentSize + newItemSize <= MAX_CACHE_SIZE_BYTES) {
      return // No cleanup needed
    }

    console.debug(
      `Cache size would exceed limit (${((currentSize + newItemSize) / 1024 / 1024).toFixed(1)}MB), cleaning up...`
    )

    const transaction = previewCacheDB!.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite')
    const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME)
    const index = store.index('lastAccessed')

    // Get all entries sorted by last accessed (oldest first)
    const entries = await new Promise<CacheEntry[]>((resolve, reject) => {
      const request = index.getAll()
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })

    // Sort by last accessed time (oldest first)
    entries.sort((a, b) => a.lastAccessed - b.lastAccessed)

    let freedSpace = 0
    const targetSpace = newItemSize + MAX_CACHE_SIZE_BYTES * 0.1 // Free 10% extra buffer

    for (const entry of entries) {
      if (freedSpace >= targetSpace) break

      await new Promise<void>((resolve, reject) => {
        const deleteRequest = store.delete(entry.pattern)
        deleteRequest.onsuccess = () => {
          freedSpace += entry.size
          // Also remove from memory cache
          memoryCache.delete(entry.pattern)
          console.debug(
            `Evicted cached preview for ${entry.pattern} (${(entry.size / 1024).toFixed(1)}KB)`
          )
          resolve()
        }
        deleteRequest.onerror = () => reject(deleteRequest.error)
      })
    }

    console.debug(`Freed ${(freedSpace / 1024 / 1024).toFixed(1)}MB from preview cache`)
  } catch (error) {
    console.warn(`Error managing cache size: ${error}`)
  }
}

// Clear a specific pattern from cache
export async function clearPatternFromCache(pattern: string): Promise<void> {
  try {
    // Remove from memory cache
    memoryCache.delete(pattern)

    if (!previewCacheDB) await initPreviewCacheDB()

    const transaction = previewCacheDB!.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite')
    const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME)

    await new Promise<void>((resolve, reject) => {
      const deleteRequest = store.delete(pattern)
      deleteRequest.onsuccess = () => {
        console.debug(`Cleared ${pattern} from cache`)
        resolve()
      }
      deleteRequest.onerror = () => reject(deleteRequest.error)
    })
  } catch (error) {
    console.warn(`Error clearing pattern from cache: ${error}`)
  }
}

// Get multiple previews from cache (batch operation)
export async function getPreviewsFromCache(
  patterns: string[]
): Promise<Map<string, PreviewData>> {
  const results = new Map<string, PreviewData>()
  const uncachedPatterns: string[] = []

  // Check memory cache first
  for (const pattern of patterns) {
    if (memoryCache.has(pattern)) {
      results.set(pattern, memoryCache.get(pattern)!)
    } else {
      uncachedPatterns.push(pattern)
    }
  }

  // Check IndexedDB for remaining patterns
  if (uncachedPatterns.length > 0 && previewCacheDB) {
    try {
      const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite')
      const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME)

      await Promise.all(
        uncachedPatterns.map(
          (pattern) =>
            new Promise<void>((resolve) => {
              const request = store.get(pattern)
              request.onsuccess = () => {
                const result = request.result as CacheEntry | undefined
                if (result) {
                  // Update last accessed time
                  result.lastAccessed = Date.now()
                  store.put(result)

                  // Add to results and memory cache
                  results.set(pattern, result.data)
                  addToMemoryCache(pattern, result.data)
                }
                resolve()
              }
              request.onerror = () => resolve()
            })
        )
      )
    } catch (error) {
      console.warn(`Error batch getting from cache: ${error}`)
    }
  }

  return results
}

// Shared function to cache all previews - used by both BrowsePage and Layout modal
export interface CacheAllProgress {
  completed: number
  total: number
  done: boolean
}

export async function cacheAllPreviews(
  onProgress: (progress: CacheAllProgress) => void
): Promise<{ success: boolean; cached: number }> {
  const BATCH_SIZE = 10

  try {
    await initPreviewCacheDB()

    // Fetch all patterns
    const response = await fetch('/list_theta_rho_files_with_metadata')
    const patterns: { path: string }[] = await response.json()
    const allPaths = patterns.map((p) => p.path)

    // Check which patterns are already cached
    const cachedPreviews = await getPreviewsFromCache(allPaths)
    const uncachedPatterns = allPaths.filter((path) => !cachedPreviews.has(path))

    if (uncachedPatterns.length === 0) {
      onProgress({ completed: patterns.length, total: patterns.length, done: true })
      return { success: true, cached: 0 }
    }

    onProgress({ completed: 0, total: uncachedPatterns.length, done: false })

    const totalBatches = Math.ceil(uncachedPatterns.length / BATCH_SIZE)

    for (let i = 0; i < totalBatches; i++) {
      const batchStart = i * BATCH_SIZE
      const batchEnd = Math.min(batchStart + BATCH_SIZE, uncachedPatterns.length)
      const batchPatterns = uncachedPatterns.slice(batchStart, batchEnd)

      try {
        const batchResponse = await fetch('/preview_thr_batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_names: batchPatterns }),
        })

        if (batchResponse.ok) {
          const results = await batchResponse.json()

          for (const [path, data] of Object.entries(results)) {
            if (data && !(data as { error?: string }).error) {
              await savePreviewToCache(path, data as PreviewData)
            }
          }
        }
      } catch {
        // Continue even if batch fails
      }

      onProgress({ completed: batchEnd, total: uncachedPatterns.length, done: false })

      // Small delay between batches
      if (i + 1 < totalBatches) {
        await new Promise((resolve) => setTimeout(resolve, 100))
      }
    }

    onProgress({ completed: uncachedPatterns.length, total: uncachedPatterns.length, done: true })
    return { success: true, cached: uncachedPatterns.length }
  } catch (error) {
    console.error('Error caching previews:', error)
    return { success: false, cached: 0 }
  }
}
