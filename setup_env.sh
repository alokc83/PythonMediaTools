#!/bin/bash
set -e

VENV_NAME="venv"

echo "Setting up virtual environment..."

if [ ! -d "$VENV_NAME" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV_NAME"
else
    echo "venv already exists."
fi

echo "Activating venv..."
source "$VENV_NAME/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing requirements..."
if [ -f "requirement.txt" ]; then
    pip install -r requirement.txt
else
    echo "Warning: requirement.txt not found!"
fi

echo "Setup complete. To run the app:"
echo "  source $VENV_NAME/bin/activate"
echo "  python src/launcher.py"
echo ""
echo "Or use the run script: ./run_app.sh"
