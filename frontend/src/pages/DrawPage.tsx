import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiClient } from '@/lib/apiClient'
import { useLanguageStore } from '@/stores/useLanguageStore'

type Point = { theta: number; rho: number }

export default function DrawPage() {
  const { t } = useLanguageStore()
  const navigate = useNavigate()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [points, setPoints] = useState<Point[]>([])
  const [undoStack, setUndoStack] = useState<Point[][]>([])
  const [redoStack, setRedoStack] = useState<Point[][]>([])
  const [isDrawing, setIsDrawing] = useState(false)
  const [patternName, setPatternName] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  const CANVAS_SIZE = 600
  const PADDING = 20
  const RADIUS = (CANVAS_SIZE - PADDING * 2) / 2
  const CENTER = CANVAS_SIZE / 2

  // Initialize canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    drawCanvas()
  }, [points])

  const drawCanvas = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const isDark = document.documentElement.classList.contains('dark')
    const bgColor = isDark ? '#1a1a1a' : '#f5f5f5'
    const circleColor = isDark ? '#333333' : '#e5e5e5'
    const lineColor = isDark ? '#3b82f6' : '#2563eb'

    // Clear
    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE)

    // Draw outer circle
    ctx.beginPath()
    ctx.arc(CENTER, CENTER, RADIUS, 0, Math.PI * 2)
    ctx.fillStyle = bgColor
    ctx.fill()
    ctx.strokeStyle = circleColor
    ctx.lineWidth = 2
    ctx.stroke()

    // Draw points
    if (points.length > 0) {
      ctx.beginPath()
      ctx.strokeStyle = lineColor
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'

      const firstPos = polarToCanvas(points[0].theta, points[0].rho)
      ctx.moveTo(firstPos.x, firstPos.y)

      for (let i = 1; i < points.length; i++) {
        const pos = polarToCanvas(points[i].theta, points[i].rho)
        ctx.lineTo(pos.x, pos.y)
      }
      ctx.stroke()

      // Draw last point marker
      const lastPos = polarToCanvas(points[points.length - 1].theta, points[points.length - 1].rho)
      ctx.beginPath()
      ctx.arc(lastPos.x, lastPos.y, 5, 0, Math.PI * 2)
      ctx.fillStyle = lineColor
      ctx.fill()
    }
  }

  const polarToCanvas = (theta: number, rho: number) => {
    const r = rho * RADIUS
    const x = CENTER + r * Math.cos(theta)
    const y = CENTER + r * Math.sin(theta)
    return { x, y }
  }

  const canvasToPolar = (x: number, y: number) => {
    const dx = x - CENTER
    const dy = y - CENTER
    let theta = Math.atan2(dy, dx)
    let rho = Math.sqrt(dx * dx + dy * dy) / RADIUS

    // Normalize rho to 1.0
    if (rho > 1) rho = 1

    return { theta, rho }
  }

  const handleMouseDown = (e: React.MouseEvent | React.TouchEvent) => {
    setIsDrawing(true)
    setUndoStack([...undoStack, [...points]])
    setRedoStack([])
    addPoint(e)
  }

  const handleMouseMove = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isDrawing) return
    addPoint(e)
  }

  const handleMouseUp = () => {
    setIsDrawing(false)
  }

  const addPoint = (e: React.MouseEvent | React.TouchEvent) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    
    let clientX, clientY
    if ('touches' in e) {
      clientX = e.touches[0].clientX
      clientY = e.touches[0].clientY
    } else {
      clientX = e.clientX
      clientY = e.clientY
    }

    const x = (clientX - rect.left) * (CANVAS_SIZE / rect.width)
    const y = (clientY - rect.top) * (CANVAS_SIZE / rect.height)

    const { theta, rho } = canvasToPolar(x, y)
    
    // Simple optimization: only add if distance is meaningful
    if (points.length > 0) {
      const last = points[points.length - 1]
      const dTheta = Math.abs(theta - last.theta)
      const dRho = Math.abs(rho - last.rho)
      if (dTheta < 0.01 && dRho < 0.01) return
    }

    setPoints([...points, { theta, rho }])
  }

  const handleUndo = () => {
    if (undoStack.length === 0) return
    const prev = undoStack[undoStack.length - 1]
    setRedoStack([...redoStack, [...points]])
    setPoints(prev)
    setUndoStack(undoStack.slice(0, -1))
  }

  const handleRedo = () => {
    if (redoStack.length === 0) return
    const next = redoStack[redoStack.length - 1]
    setUndoStack([...undoStack, [...points]])
    setPoints(next)
    setRedoStack(redoStack.slice(0, -1))
  }

  const handleClear = () => {
    setUndoStack([...undoStack, [...points]])
    setPoints([])
    setRedoStack([])
  }

  const generateTHR = () => {
    return points.map(p => `${p.theta.toFixed(4)} ${p.rho.toFixed(4)}`).join('\n')
  }

  const handleExport = () => {
    if (points.length === 0) {
      toast.error('No points to export')
      return
    }
    const content = generateTHR()
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${patternName || 'custom_pattern'}.thr`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleSave = async () => {
    if (points.length === 0) {
      toast.error('No points to save')
      return
    }
    if (!patternName.trim()) {
      toast.error('Please enter a pattern name')
      return
    }

    setIsSaving(true)
    try {
      const content = generateTHR()
      const fileName = patternName.trim().endsWith('.thr') ? patternName.trim() : `${patternName.trim()}.thr`
      const file = new File([content], fileName, { type: 'text/plain' })
      
      await apiClient.uploadFile('/upload_theta_rho', file)
      toast.success(t('draw.save_success') || 'Pattern saved successfully')
      navigate('/')
    } catch (error) {
      console.error('Save error:', error)
      toast.error('Failed to save pattern')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      <div className="w-full max-w-xl flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-center">{t('draw.title')}</h1>
        
        <div className="flex flex-col gap-2">
          <Label htmlFor="patternName">{t('draw.name_placeholder')}</Label>
          <Input 
            id="patternName"
            value={patternName}
            onChange={(e) => setPatternName(e.target.value)}
            placeholder="my_awesome_pattern"
          />
        </div>

        <div className="relative aspect-square w-full bg-card rounded-xl border border-border shadow-sm overflow-hidden touch-none">
          <canvas
            ref={canvasRef}
            width={CANVAS_SIZE}
            height={CANVAS_SIZE}
            className="w-full h-full cursor-crosshair"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onTouchStart={handleMouseDown}
            onTouchMove={handleMouseMove}
            onTouchEnd={handleMouseUp}
          />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Button variant="outline" onClick={handleUndo} disabled={undoStack.length === 0}>
            <span className="material-icons-outlined mr-2">undo</span>
            {t('draw.undo')}
          </Button>
          <Button variant="outline" onClick={handleRedo} disabled={redoStack.length === 0}>
            <span className="material-icons-outlined mr-2">redo</span>
            {t('draw.redo')}
          </Button>
          <Button variant="outline" onClick={handleClear} disabled={points.length === 0}>
            <span className="material-icons-outlined mr-2">delete</span>
            {t('draw.clear')}
          </Button>
          <Button variant="outline" onClick={handleExport} disabled={points.length === 0}>
            <span className="material-icons-outlined mr-2">download</span>
            {t('draw.export')}
          </Button>
        </div>

        <Button className="w-full h-12 text-lg" onClick={handleSave} disabled={isSaving || points.length === 0}>
          {isSaving ? (
            <span className="material-icons-outlined animate-spin mr-2">sync</span>
          ) : (
            <span className="material-icons-outlined mr-2">save</span>
          )}
          {t('draw.save')}
        </Button>
      </div>
    </div>
  )
}
