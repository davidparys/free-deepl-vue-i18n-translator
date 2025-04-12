# DeepL Translator for Vue i18n

A Python tool that automatically translates Vue i18n JSON files using the DeepL API.

## Features

- Automatically detects and processes your Nuxt.js i18n configuration
- Translates JSON files recursively, preserving nested structure
- Works as both a CLI tool and a GitHub Action
- Supports formality options for languages that have formal/informal distinctions

## Prerequisites

- Python 3.6+
- DeepL API key (sign up at [DeepL API](https://www.deepl.com/pro-api))

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### As a CLI tool

1. Create a `.env` file with your DeepL API key:

```bash
DEEPL_API_KEY=your-api-key-here
```

2. Run the translator:

```bash
python deepl_translator.py --root /path/to/your/project --formality default
```

#### Command-line options

- `--root`, `-r`: Project root directory (default: current directory). Can be relative to your current working directory.
- `--formality`, `-f`: Translation formality (choices: default, more, less, prefer_more, prefer_less)
- `--api-key`, `-k`: DeepL API key (alternative to .env file)
- `--debug`, `-d`: Enable debug logging to diagnose translation issues
- `--force-retranslate`: Force retranslation of strings that appear identical to source
- `--config-path`, `-c`: Custom path to the nuxt.config.ts/js file
- `--locales-dir`, `-l`: Custom directory for locale files (relative to project root or absolute path)
- `--include-locale`: Only translate the specified locale(s). Can be used multiple times.
- `--override-default-locale`: Override the default locale (source language) specified in the config
- `--output-dir`, `-o`: Custom output directory for translated files
- `--dry-run`: Don't actually translate or save files; just report what would be done
- `--version`, `-v`: Show the version number and exit

### Examples

```bash
# Basic usage with default settings
python deepl_translator.py

# Translate only the Polish locale
python deepl_translator.py --include-locale pl

# Use a specific config file and output directory
python deepl_translator.py --config-path ./custom/nuxt.config.js --output-dir ./translated-locales

# Force retranslate identical strings and enable debug
python deepl_translator.py --force-retranslate --debug

# Dry run to see what would be translated
python deepl_translator.py --dry-run
```

### As a GitHub Action

Add the following to your GitHub workflow:

```yaml
name: Translate i18n files

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Translate i18n files
        uses: your-username/deepl-translator-vue-i18n@main
        with:
          api-key: ${{ secrets.DEEPL_API_KEY }}
          formality: default
          root-dir: .
          
      - name: Commit changes
        uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: Update translations
          file_pattern: '**/*.json'
```

## How it works

1. The tool searches for the `nuxt.config.ts` file in your project
2. It extracts the i18n configuration, including locales and the default locale
3. It looks for locale files in several potential locations:
   - The exact path as specified in the i18n config
   - In the `i18n/locales` directory
   - In the root `locales` directory
   - At the project root
4. It uses the default locale file as the source for translations
5. It translates all other locale files using the DeepL API
6. The translated files are saved in the same location as specified in the i18n configuration

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT 