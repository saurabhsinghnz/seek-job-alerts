#!/bin/bash
# Quick setup script for Seek Job Alert Bot

set -e

echo "🚀 Setting up Seek Job Alert Bot..."
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

echo "✅ Python $(python3 --version) found"
echo ""

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
pip install -q -r requirements.txt
echo "✅ Dependencies installed"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your Telegram credentials"
    echo ""
    echo "To get credentials:"
    echo "  1. Bot Token: Talk to @BotFather on Telegram"
    echo "  2. Chat ID: Talk to @userinfobot on Telegram"
else
    echo "✅ .env file already exists"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Telegram credentials"
echo "  2. Run: source venv/bin/activate"
echo "  3. Run: python seek_job_alert.py"
echo ""
