import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Normalize a string for fuzzy search matching.
 * Treats spaces, underscores, and hyphens as equivalent.
 * Example: "clear from out" matches "clear_from_out"
 */
export function normalizeForSearch(str: string): string {
  return str.toLowerCase().replace(/[\s_-]+/g, ' ')
}

/**
 * Check if a search query matches a target string (fuzzy match).
 * Spaces, underscores, and hyphens are treated as equivalent.
 */
export function fuzzyMatch(target: string, query: string): boolean {
  return normalizeForSearch(target).includes(normalizeForSearch(query))
}
