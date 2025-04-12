#!/usr/bin/env python3
"""
Test script for DeepL translator.
This script creates a simple sample Nuxt project structure to test the translator.
"""

import os
import json
import tempfile
import shutil
import subprocess
from pathlib import Path

def create_test_project():
    """Create a test Nuxt project with i18n configuration."""
    # Create a temporary directory
    test_dir = tempfile.mkdtemp()
    print(f"Created test project directory: {test_dir}")
    
    # Create nuxt.config.ts
    nuxt_config = """
export default defineNuxtConfig({
  modules: ['@nuxtjs/i18n'],
  i18n: {
    defaultLocale: 'en',
    locales: [
      { code: 'en', file: 'locales/en.json' },
      { code: 'fr', file: 'locales/fr.json' },
      { code: 'de', file: 'locales/de.json' },
      { code: 'es', file: 'locales/es.json' }
    ]
  }
})
"""
    
    # Create English locale file (source)
    en_locale = {
        "welcome": "Welcome to our website",
        "about": "About us",
        "contact": "Contact us",
        "navigation": {
            "home": "Home",
            "products": "Products",
            "services": "Services"
        },
        "footer": {
            "copyright": "Copyright 2023",
            "terms": "Terms of Service",
            "privacy": "Privacy Policy"
        }
    }
    
    # Write files
    (Path(test_dir) / "nuxt.config.ts").write_text(nuxt_config)
    
    # Test both location structures
    # 1. Standard locales directory
    locales_dir = Path(test_dir) / "locales"
    locales_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. i18n/locales structure for testing alternative lookup
    i18n_locales_dir = Path(test_dir) / "i18n" / "locales"
    i18n_locales_dir.mkdir(parents=True, exist_ok=True)
    
    # Write English locale file to both locations to test lookup
    with open(locales_dir / "en.json", "w", encoding="utf-8") as f:
        json.dump(en_locale, f, ensure_ascii=False, indent=2)
    
    # Create a slightly modified variant in i18n/locales to verify which one is used
    alternative_en_locale = en_locale.copy()
    alternative_en_locale["source"] = "i18n/locales structure"
    
    with open(i18n_locales_dir / "en.json", "w", encoding="utf-8") as f:
        json.dump(alternative_en_locale, f, ensure_ascii=False, indent=2)
    
    return test_dir

def run_translator(test_dir, api_key=None):
    """Run the translator on the test project."""
    script_dir = Path(__file__).parent.absolute()
    script_path = script_dir / "deepl_translator.py"
    
    env = os.environ.copy()
    if api_key:
        env["DEEPL_API_KEY"] = api_key
    
    # Test with both absolute and relative paths
    # 1. First run with absolute path
    cmd_absolute = [
        "python", 
        str(script_path), 
        "--root", 
        test_dir,
        "--formality",
        "more"
    ]
    
    print(f"Running command with absolute path: {' '.join(cmd_absolute)}")
    subprocess.run(cmd_absolute, env=env, check=True)
    
    # 2. Now run with relative path from the current directory
    # First, change to a directory one level up from the test directory
    original_dir = os.getcwd()
    parent_dir = Path(test_dir).parent
    rel_path = Path(test_dir).name
    
    try:
        os.chdir(parent_dir)
        cmd_relative = [
            "python", 
            str(script_path), 
            "--root", 
            rel_path,
            "--formality",
            "more"
        ]
        
        print(f"Changed to directory: {parent_dir}")
        print(f"Running command with relative path: {' '.join(cmd_relative)}")
        subprocess.run(cmd_relative, env=env, check=True)
    finally:
        os.chdir(original_dir)

def check_results(test_dir):
    """Check the results of the translation."""
    # Check both possible locations
    locales_dir = Path(test_dir) / "locales"
    i18n_locales_dir = Path(test_dir) / "i18n" / "locales"
    
    # Check if translation files were created
    fr_path_standard = locales_dir / "fr.json"
    fr_path_i18n = i18n_locales_dir / "fr.json"
    
    de_path_standard = locales_dir / "de.json"
    de_path_i18n = i18n_locales_dir / "de.json"
    
    es_path_standard = locales_dir / "es.json"
    es_path_i18n = i18n_locales_dir / "es.json"
    
    print("\nResults:")
    print(f"French locale file exists (standard): {fr_path_standard.exists()}")
    print(f"French locale file exists (i18n): {fr_path_i18n.exists()}")
    
    print(f"German locale file exists (standard): {de_path_standard.exists()}")
    print(f"German locale file exists (i18n): {de_path_i18n.exists()}")
    
    print(f"Spanish locale file exists (standard): {es_path_standard.exists()}")
    print(f"Spanish locale file exists (i18n): {es_path_i18n.exists()}")
    
    # Print contents of the files if they exist
    if fr_path_standard.exists():
        with open(fr_path_standard, "r", encoding="utf-8") as f:
            fr_data = json.load(f)
        print("\nFrench translation sample (standard):")
        print(json.dumps(fr_data, ensure_ascii=False, indent=2))
        
    if fr_path_i18n.exists():
        with open(fr_path_i18n, "r", encoding="utf-8") as f:
            fr_data = json.load(f)
        print("\nFrench translation sample (i18n):")
        print(json.dumps(fr_data, ensure_ascii=False, indent=2))

def cleanup(test_dir):
    """Clean up the test directory."""
    shutil.rmtree(test_dir)
    print(f"\nCleaned up test directory: {test_dir}")

def main():
    """Main function."""
    # Get API key
    api_key = os.environ.get("DEEPL_API_KEY")
    if not api_key:
        print("Please set the DEEPL_API_KEY environment variable")
        return
    
    # Create test project
    test_dir = create_test_project()
    
    try:
        # Run translator
        run_translator(test_dir, api_key)
        
        # Check results
        check_results(test_dir)
    finally:
        # Ask user if they want to keep the test directory
        keep = input("\nKeep test directory? (y/n): ").lower() == "y"
        if not keep:
            cleanup(test_dir)
        else:
            print(f"Test directory kept at: {test_dir}")

if __name__ == "__main__":
    main() 