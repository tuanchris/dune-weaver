# Tailwind CSS Setup

This project now uses **production-ready Tailwind CSS** instead of the CDN version.

## 🚀 Quick Start

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Build CSS for production:**
   ```bash
   npm run build-css
   ```

3. **For development (watch mode):**
   ```bash
   npm run dev
   ```

## 📁 File Structure

- `tailwind.config.js` - Tailwind configuration
- `static/css/tailwind-input.css` - Source CSS with custom styles
- `static/css/tailwind.css` - Generated CSS (gitignored)
- `package.json` - Node.js dependencies and scripts

## 🔧 Available Scripts

- `npm run build-css` - Build minified CSS for production
- `npm run watch-css` - Watch for changes and rebuild
- `npm run dev` - Same as watch-css (for development)

## 🎨 Custom Styles

All custom styles from the original `base.html` have been moved to `static/css/tailwind-input.css`:

- Material Icons styles
- Dark mode styles  
- Custom component styles (tabs, switches, etc.)
- Animations (marquee)

## 🌙 Dark Mode

Dark mode is configured using Tailwind's `class` strategy. The theme toggle in the header adds/removes the `dark` class from the document root.

## 📦 Included Plugins

- `@tailwindcss/forms` - Better form styling
- `@tailwindcss/container-queries` - Container query support

## 🔄 Development Workflow

1. **Making style changes:**
   - Edit `static/css/tailwind-input.css` for custom styles
   - Use Tailwind classes directly in HTML templates
   - Run `npm run dev` to watch for changes

2. **Production build:**
   - Run `npm run build-css` before deploying
   - The generated `tailwind.css` is optimized and minified

## ✅ Benefits

- **Smaller file size:** Only used CSS classes are included
- **Better performance:** No runtime CSS generation
- **Proper caching:** Static CSS file can be cached by browsers
- **Development features:** All Tailwind features available
- **Production ready:** Optimized and minified output 