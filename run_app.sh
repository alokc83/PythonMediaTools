#!/bin/bash
set -e

VENV_NAME="venv"

if [ ! -d "$VENV_NAME" ]; then
    echo "Virtual environment not found. Running setup..."
    ./setup_env.sh
fi

source "$VENV_NAME/bin/activate"
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python src/launcher.py
