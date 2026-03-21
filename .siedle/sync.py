#!/usr/bin/env python3
"""
Generates the homeassistant-siedle integration from homeassistant-techpoint.

Usage:
    python3 .siedle/sync.py <output_dir>

Example:
    python3 .siedle/sync.py /tmp/siedle-output
"""

import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TECHPOINT_DIR = os.path.join(REPO_ROOT, "custom_components", "techpoint")
OVERRIDES_DIR = os.path.join(REPO_ROOT, ".siedle", "overrides")
REPO_ROOT_DIR = os.path.join(REPO_ROOT, ".siedle", "repo-root")

OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/siedle-output"
SIEDLE_COMPONENT_DIR = os.path.join(OUTPUT_DIR, "custom_components", "siedle")

# Text replacements applied to all .py files
REPLACEMENTS = [
    ('DOMAIN = "techpoint"', 'DOMAIN = "siedle"'),
    ('MANUFACTURER = "TechSolutions"', 'MANUFACTURER = "Siedle"'),
    ('MODEL_CONTROLLER = "TechPoint"', 'MODEL_CONTROLLER = "SC-600"'),
    ('DEFAULT_NAME = "TechPoint"', 'DEFAULT_NAME = "Siedle SC-600"'),
    ('SIGNAL_EVENT_LOG_UPDATED = "techpoint_event_log_updated"', 'SIGNAL_EVENT_LOG_UPDATED = "siedle_event_log_updated"'),
    ('EVENT_BUS_NAME = "techpoint_event"', 'EVENT_BUS_NAME = "siedle_event"'),
    ('"custom_components.techpoint"', '"custom_components.siedle"'),
    ('"TechPoint:', '"Siedle SC-600:'),
]

# Files/dirs replaced entirely by overrides — skip when copying techpoint
OVERRIDE_FILES = {"manifest.json", "strings.json", "icon.png", "logo.png"}
OVERRIDE_DIRS = {"brand", "translations"}


def patch_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for old, new in REPLACEMENTS:
            content = content.replace(old, new)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except (UnicodeDecodeError, IsADirectoryError):
        pass


def main():
    # Clean output
    if os.path.exists(SIEDLE_COMPONENT_DIR):
        shutil.rmtree(SIEDLE_COMPONENT_DIR)
    os.makedirs(SIEDLE_COMPONENT_DIR, exist_ok=True)

    # Copy techpoint files (excluding override targets)
    for item in os.listdir(TECHPOINT_DIR):
        if item in OVERRIDE_FILES or item in OVERRIDE_DIRS:
            continue
        src = os.path.join(TECHPOINT_DIR, item)
        dst = os.path.join(SIEDLE_COMPONENT_DIR, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Patch all .py files
    for root, _, files in os.walk(SIEDLE_COMPONENT_DIR):
        for fname in files:
            if fname.endswith(".py"):
                patch_file(os.path.join(root, fname))

    # Apply overrides (Siedle-specific strings, logo, manifest, translations)
    for item in os.listdir(OVERRIDES_DIR):
        src = os.path.join(OVERRIDES_DIR, item)
        dst = os.path.join(SIEDLE_COMPONENT_DIR, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    # Copy repo-root files (hacs.json, README etc.) to output root
    if os.path.exists(REPO_ROOT_DIR):
        for item in os.listdir(REPO_ROOT_DIR):
            src = os.path.join(REPO_ROOT_DIR, item)
            dst = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    print(f"Siedle integration generated at: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
