import { useEffect, useState } from 'react'
import { HexColorPicker } from 'react-colorful'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface ColorPickerProps {
  value: string
  onChange: (color: string) => void
  className?: string
  presets?: string[]
}

const defaultPresets = [
  '#ff0000', // Red
  '#ff8000', // Orange
  '#ffff00', // Yellow
  '#00ff00', // Green
  '#00ffff', // Cyan
  '#0000ff', // Blue
  '#ff00ff', // Magenta
  '#ffffff', // White
  '#2a9d8f', // Teal
  '#e9c46a', // Sand
  '#dc143c', // Crimson
  '#000000', // Black
]

const HEX_RE = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/

function normalizeHex(input: string): string | null {
  const match = HEX_RE.exec(input.trim())
  if (!match) return null
  let hex = match[1].toLowerCase()
  if (hex.length === 3) {
    hex = hex
      .split('')
      .map((c) => c + c)
      .join('')
  }
  return `#${hex}`
}

export function ColorPicker({
  value,
  onChange,
  className,
  presets = defaultPresets,
}: ColorPickerProps) {
  const [open, setOpen] = useState(false)
  const [hexInput, setHexInput] = useState(value)

  // Keep the text field in sync with external/picker changes
  useEffect(() => {
    setHexInput(value)
  }, [value])

  const commitHexInput = (input: string) => {
    const hex = normalizeHex(input)
    if (hex) {
      onChange(hex)
      setHexInput(hex)
    } else {
      setHexInput(value)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="secondary"
          className={cn(
            'w-12 h-12 rounded-full p-1 border-2',
            className
          )}
          style={{ backgroundColor: value }}
        >
          <span className="sr-only">Pick a color</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-3 space-y-3" align="start">
        <HexColorPicker color={value} onChange={onChange} />
        <Input
          value={hexInput}
          onChange={(e) => setHexInput(e.target.value)}
          onBlur={(e) => commitHexInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              commitHexInput(e.currentTarget.value)
            }
          }}
          spellCheck={false}
          autoComplete="off"
          aria-label="Hex color"
          className="h-8 font-mono text-sm"
        />
        <div className="grid grid-cols-6 gap-1.5">
          {presets.map((preset) => (
            <button
              key={preset}
              type="button"
              aria-label={`Select color ${preset}`}
              className={cn(
                'h-6 w-6 rounded border border-border cursor-pointer transition-transform hover:scale-110',
                value.toLowerCase() === preset.toLowerCase() &&
                  'ring-2 ring-ring ring-offset-1'
              )}
              style={{ backgroundColor: preset }}
              onClick={() => onChange(preset)}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
