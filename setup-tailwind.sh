#!/bin/bash

echo "Setting up Tailwind CSS for production..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Node.js is not installed. Please install Node.js first:"
    echo "https://nodejs.org/"
    exit 1
fi

# Install dependencies
echo "Installing Tailwind CSS and plugins..."
npm install

# Build the CSS file
echo "Building production CSS..."
npm run build-css

echo "✅ Tailwind CSS setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Remove the inline styles from templates/base.html (lines 28-177)"
echo "2. Make sure /static/css/tailwind.css is being served by your Flask app"
echo "3. For development, run: npm run dev (to watch for changes)"
echo "4. For production builds, run: npm run build-css"
echo ""
echo "🚀 Your app is now using production-ready Tailwind CSS!" 