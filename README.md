# DeepL Translator for Vue i18n

![GitHub Action](https://img.shields.io/badge/GitHub-Action-blue?logo=github&logoColor=white)
![DeepL API](https://img.shields.io/badge/DeepL-API-009393?logo=deepl&logoColor=white)
![Vue i18n](https://img.shields.io/badge/Vue-i18n-41B883?logo=vuedotjs&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.6+-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

Automatically translate your Vue i18n JSON localization files using the powerful DeepL API. This GitHub Action helps you keep your multilingual applications up to date with minimal effort.

<p align="center">
  <img src="https://repository-images.githubusercontent.com/612691485/c9d1b0bd-e1ee-4dc9-acff-6ba367d5c3a5" alt="DeepL Translator for Vue i18n" width="600">
</p>

## ✨ Features

- 🔍 **Smart Detection** - Automatically detects and processes your Nuxt.js i18n configuration
- 🌴 **Structure Preservation** - Translates JSON files recursively, preserving nested structure
- 🛠️ **Versatile Usage** - Works as both a CLI tool and a GitHub Action
- 🎭 **Formality Options** - Supports formality levels for languages with formal/informal distinctions
- ✅ **Simple Setup** - Easy to integrate into your CI/CD pipeline
- 🔄 **Review Workflow** - Option to create pull requests for reviewing translations before merging

## 📋 Prerequisites

- DeepL API key (sign up at [DeepL API](https://www.deepl.com/pro-api))
- For CLI usage: Python 3.6+

## 🚀 GitHub Action Usage

Add the following to your GitHub workflow file (e.g., `.github/workflows/translate.yml`):

### Option 1: Create Pull Requests for Translation Review (Recommended)

This approach allows team members to review translations before they're merged into your codebase.

```yaml
name: Translate i18n files

on:
  push:
    branches: [ main ]
    paths:
      - 'locales/en.json'  # Only run when the source locale file changes
  workflow_dispatch:  # Allow manual triggering

jobs:
  translate:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v3
      
      - name: Translate i18n files
        uses: mountainwebstudio/deepl-translator-vue-i18n@v1  # Update with your username and tag
        with:
          api-key: ${{ secrets.DEEPL_API_KEY }}
          formality: default
          root-dir: .
          # Optional parameters:
          # include-locale: fr,de,es  # Only translate these locales
          # force-retranslate: true   # Force retranslation of identical strings
          
      # Using GitHub CLI
      - name: Create Pull Request
        run: |
          # Create a new branch for the translations
          git checkout -b update-translations-$(date +%Y%m%d-%H%M%S)
          
          # Add and commit the changes
          git config user.name "DeepL Translation Bot"
          git config user.email "bot@example.com"
          git add .
          git commit -m "chore: update translations with DeepL"
          
          # Push the branch and create a PR
          git push -u origin HEAD
          gh pr create --title "Update translations with DeepL" \
            --body "This PR contains automatically generated translations using DeepL API. Please review the translations before merging." \
            --label "translations,automated"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Option 2: Alternative PR Creation Method

You can also use a dedicated action for creating PRs:

```yaml
- name: Create Pull Request
  uses: peter-evans/create-pull-request@v5
  with:
    token: ${{ secrets.GITHUB_TOKEN }}
    commit-message: "chore: update translations with DeepL"
    branch: update-translations
    delete-branch: true
    title: "Update translations with DeepL"
    body: |
      This PR contains automatically generated translations using DeepL API.
      Please review the translations before merging.
    labels: |
      translations
      automated
```

### Option 3: Direct Commit (No Review)

If you prefer to bypass the review process, you can commit changes directly:

```yaml
- name: Commit changes
  uses: stefanzweifel/git-auto-commit-action@v4
  with:
    commit_message: "chore: update translations with DeepL"
    file_pattern: '**/*.json'
    commit_user_name: "DeepL Translation Bot"
    commit_user_email: "bot@example.com"
```

### 🔧 Action Parameters

| Parameter | Description | Required | Default |
|-----------|-------------|----------|---------|
| `api-key` | DeepL API Key | Yes | - |
| `formality` | Translation formality (default, more, less, prefer_more, prefer_less) | No | `default` |
| `root-dir` | Project root directory | No | `.` |
| `force-retranslate` | Force retranslation of strings that appear identical to source | No | `false` |
| `config-path` | Custom path to the nuxt.config.ts/js file | No | - |
| `locales-dir` | Custom directory for locale files | No | - |
| `include-locale` | Only translate specified locales (comma-separated) | No | - |
| `override-default-locale` | Override the default locale (source language) | No | - |
| `output-dir` | Custom output directory for translated files | No | - |
| `debug` | Enable debug logging | No | `false` |
| `dry-run` | Do not actually translate or save files | No | `false` |

## 🛡️ Translation Validation Strategies

When using pull requests for translations, consider these validation strategies:

1. **Manual Review**: Team members review the PR to check translation quality
2. **Spot Checking**: Review a sample of translations to verify quality
3. **Automated Tests**: Add tests that validate translation formatting and structure
4. **Translation Comments**: Leave notes directly in the PR for specific translations
5. **Per-Language Reviewers**: Assign specific team members for each target language

## 💻 CLI Usage

For local development and testing, you can also use the tool as a CLI application.

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

1. Create a `.env` file with your DeepL API key:

```bash
DEEPL_API_KEY=your-api-key-here
```

2. Run the translator:

```bash
python deepl_translator.py --root /path/to/your/project --formality default
```

### Command-line Options

| Option | Description |
|--------|-------------|
| `--root`, `-r` | Project root directory (default: current directory) |
| `--formality`, `-f` | Translation formality (choices: default, more, less, prefer_more, prefer_less) |
| `--api-key`, `-k` | DeepL API key (alternative to .env file) |
| `--debug`, `-d` | Enable debug logging to diagnose translation issues |
| `--force-retranslate` | Force retranslation of strings that appear identical to source |
| `--config-path`, `-c` | Custom path to the nuxt.config.ts/js file |
| `--locales-dir`, `-l` | Custom directory for locale files |
| `--include-locale` | Only translate the specified locale(s). Can be used multiple times |
| `--override-default-locale` | Override the default locale (source language) specified in the config |
| `--output-dir`, `-o` | Custom output directory for translated files |
| `--dry-run` | Don't actually translate or save files; just report what would be done |
| `--version`, `-v` | Show the version number and exit |

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

## 🔍 How it Works

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

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

MIT 