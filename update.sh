#!/bin/bash

# Variables
VENV_DIR=./.venv
LATEST_TAG=$(git describe --tags $(git rev-list --tags --max-count=1))
CURRENT_TAG=$(git describe --tags)

# Git update
git fetch --tags
echo "Latest version:   $LATEST_TAG"
echo "Current version:  $CURRENT_TAG"

if [ "$LATEST_TAG" == "$CURRENT_TAG" ]; then
    if [ -d $VENV_DIR ]; then
        echo "RaspenBeere is up to date ($LATEST_TAG). No update needed."
        read -p "Press Enter to exit..."
        exit 0
    else
        echo "rasp_berry is up to date ($LATEST_TAG), but no virtual environment found."
    fi
else
    echo "Updating RaspenBeere from $CURRENT_TAG to $LATEST_TAG..."
    git checkout $LATEST_TAG
fi

# Pip update
echo "Creating virtual environment..."
python -m venv $VENV_DIR
source $VENV_DIR/Scripts/activate

python -m pip install --upgrade pip
pip freeze | xargs pip uninstall -y || true
pip install -r requirements.txt
read -p "Press enter to exit"
