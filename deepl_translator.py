#!/usr/bin/env python3

import os
import json
import argparse
import logging
import time
import sys
import signal
import threading
from typing import Dict, List, Any, Optional
from pathlib import Path
import requests
from dotenv import load_dotenv

# Set up colored output
try:
    from colorama import init, Fore, Style
    init()  # Initialize colorama
    COLORS_AVAILABLE = True
except ImportError:
    # If colorama is not available, define empty color constants
    class EmptyFore:
        def __getattr__(self, name):
            return ""
    class EmptyStyle:
        def __getattr__(self, name):
            return ""
    Fore = EmptyFore()
    Style = EmptyStyle()
    COLORS_AVAILABLE = False

# Set up logging with color
class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log levels."""
    FORMATS = {
        logging.DEBUG: Style.DIM + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + Style.RESET_ALL,
        logging.INFO: Fore.GREEN + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + Style.RESET_ALL,
        logging.WARNING: Fore.YELLOW + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + Style.RESET_ALL,
        logging.ERROR: Fore.RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + Style.RESET_ALL,
        logging.CRITICAL: Fore.RED + Style.BRIGHT + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + Style.RESET_ALL,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

# Set up logging
logger = logging.getLogger("deepl-translator")
logger.setLevel(logging.DEBUG)

# Console handler with colored output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(ColoredFormatter())
logger.addHandler(console_handler)

# Global variables for interrupt handling
CURRENT_LOCALE_DATA = None
CURRENT_LOCALE_PATH = None
INTERRUPT_RECEIVED = False

# Version information
__version__ = "1.1.0"

def signal_handler(sig, frame):
    """Handle keyboard interrupt by setting a flag."""
    global INTERRUPT_RECEIVED
    if INTERRUPT_RECEIVED:  # If interrupted twice, exit immediately
        print(f"\n{Fore.RED}Forced exit. Partial translations may be lost.{Style.RESET_ALL}")
        sys.exit(1)
    
    INTERRUPT_RECEIVED = True
    print(f"\n{Fore.YELLOW}Interrupt received. Saving current progress and exiting...{Style.RESET_ALL}")
    # The main loop will detect this flag and save before exiting

def progress_bar(current, total, width=50):
    """Display a progress bar."""
    filled = int(width * current // total)
    bar = f"{Fore.GREEN}{'█' * filled}{Fore.YELLOW}{'-' * (width - filled)}{Style.RESET_ALL}"
    percent = current / total * 100
    return f"[{bar}] {current}/{total} ({percent:.1f}%)"

def clear_lines(n=1):
    """Clear n lines from the terminal."""
    if n > 0:
        sys.stdout.write(f"\033[{n}A")  # Move cursor up n lines
        sys.stdout.write("\033[J")  # Clear from cursor to end of screen
        sys.stdout.flush()

def print_box(message, style=Fore.BLUE):
    """Print a message in a styled box."""
    width = min(len(message) + 4, 80)
    print(f"{style}╔{'═' * (width - 2)}╗{Style.RESET_ALL}")
    print(f"{style}║{' ' * (width - 2)}║{Style.RESET_ALL}")
    print(f"{style}║  {message}{' ' * (width - len(message) - 4)}║{Style.RESET_ALL}")
    print(f"{style}║{' ' * (width - 2)}║{Style.RESET_ALL}")
    print(f"{style}╚{'═' * (width - 2)}╝{Style.RESET_ALL}")

def resolve_path(path_str: str) -> Path:
    """
    Resolve a path string to an absolute Path.
    If the path is relative, it will be resolved relative to the current working directory.
    """
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()

def save_current_progress():
    """Save the current translation progress"""
    global CURRENT_LOCALE_DATA, CURRENT_LOCALE_PATH
    
    if CURRENT_LOCALE_DATA and CURRENT_LOCALE_PATH:
        # Count how many entries we're saving
        def count_entries(data):
            if isinstance(data, dict):
                return sum(count_entries(v) for v in data.values())
            elif isinstance(data, list):
                return sum(count_entries(v) for v in data)
            elif isinstance(data, str):
                return 1
            else:
                return 0
                
        entry_count = count_entries(CURRENT_LOCALE_DATA)
        
        # Only save if we have actual translated entries
        if entry_count > 0:
            print(f"\n{Fore.YELLOW}Saving {entry_count} translated entries to {CURRENT_LOCALE_PATH}{Style.RESET_ALL}")
            with open(CURRENT_LOCALE_PATH, 'w', encoding='utf-8') as f:
                json.dump(CURRENT_LOCALE_DATA, f, ensure_ascii=False, indent=2)
            print(f"{Fore.GREEN}✓ Progress saved successfully.{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}No translated entries to save.{Style.RESET_ALL}")

class DeeplTranslator:
    """Class to handle translation using DeepL API."""
    
    API_URL = "https://api-free.deepl.com/v2/translate"
    
    def __init__(self, api_key: str, formality: str = "default"):
        """Initialize the translator with the DeepL API key."""
        self.api_key = api_key
        self.formality = formality
        self.missing_only = False  # Flag to only translate missing keys
        self.force_retranslate = False  # Flag to force retranslate identical strings
        print_box("DeepL Translator initialized", Fore.GREEN)
        logger.info("DeepL Translator initialized")
        
        # Translation statistics
        self.stats = {
            "total_strings": 0,
            "current_string": 0,
        }
        
        # Status line for current translation
        self.status_lines = 4  # Number of lines to clear for status updates
        
    def update_status(self, key_path, source_text, target_text=None, target_lang=None, skipped=False):
        """Update the status display with the current translation."""
        clear_lines(self.status_lines)
        
        # Progress bar
        progress = progress_bar(self.stats["current_string"], self.stats["total_strings"])
        print(f"{Fore.CYAN}Progress: {progress}{Style.RESET_ALL}")
        
        # Current key being translated
        if skipped:
            print(f"{Fore.BLUE}Skipping existing translation: {key_path}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}Translating: {key_path}{Style.RESET_ALL}")
        
        # Source text (truncated for display)
        display_source = source_text if len(source_text) < 70 else source_text[:67] + "..."
        print(f"{Fore.WHITE}Source: {display_source}{Style.RESET_ALL}")
        
        # Show target text if available
        if target_text:
            display_target = target_text if len(target_text) < 70 else target_text[:67] + "..."
            print(f"{Fore.GREEN}Target ({target_lang}): {display_target}{Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}Translating...{Style.RESET_ALL}")
            
        sys.stdout.flush()
        
    def translate_text(self, text: str, target_lang: str, source_lang: str, key_path: str = "") -> str:
        """Translate a single text string."""
        if not text.strip():
            return text
            
        # Update the status with current translation
        self.update_status(key_path, text)
        
        # Check for interrupt
        if INTERRUPT_RECEIVED:
            return text
        
        payload = {
            "auth_key": self.api_key,
            "text": text,
            "target_lang": target_lang,
            "source_lang": source_lang,
        }
        
        if self.formality != "default":
            payload["formality"] = self.formality
            
        try:
            response = requests.post(self.API_URL, data=payload)
            response.raise_for_status()
            translation = response.json()["translations"][0]["text"]
            
            # Update the status with the completed translation
            self.update_status(key_path, text, translation, target_lang)
            
            # Increment the progress counter
            self.stats["current_string"] += 1
            
            return translation
        except requests.RequestException as e:
            logger.error(f"Translation error: {e}")
            self.stats["current_string"] += 1
            return text  # Return original text on error
            
    def translate_nested_json(self, data: Any, target_lang: str, source_lang: str, key_path: str = "", existing_data: Dict = None) -> Any:
        """Recursively translate all string values in a nested JSON structure."""
        # Declare the global variable at the beginning of the function
        global CURRENT_LOCALE_DATA
        
        # Check for interrupt at each level
        if INTERRUPT_RECEIVED:
            # On interrupt, don't return anything to prevent untranslated data from being saved
            # The calling function will use CURRENT_LOCALE_DATA which only contains translated values
            return None
            
        if isinstance(data, str):
            # Check if this string already exists in the target file and is already translated
            if existing_data is not None and key_path:
                # Try to find the existing translation at this path
                parts = key_path.split(".")
                temp = existing_data
                exists = True
                
                try:
                    for part in parts:
                        # Handle array indices in the path
                        if "[" in part and "]" in part:
                            idx_start = part.index("[")
                            idx_end = part.index("]")
                            array_name = part[:idx_start]
                            try:
                                idx = int(part[idx_start+1:idx_end])
                                if array_name in temp and isinstance(temp[array_name], list) and len(temp[array_name]) > idx:
                                    temp = temp[array_name][idx]
                                else:
                                    exists = False
                                    break
                            except (ValueError, IndexError, TypeError):
                                exists = False
                                break
                        elif isinstance(temp, dict) and part in temp:
                            temp = temp[part]
                        else:
                            exists = False
                            break
                except (KeyError, TypeError, IndexError) as e:
                    # If any error occurs during path navigation, consider that the path doesn't exist
                    logger.debug(f"Error finding path {key_path}: {e}")
                    exists = False
                
                # If we found a valid string at this path in the existing data, check if it's actually translated
                if exists and isinstance(temp, str) and temp.strip():
                    # Check if the string is identical to source (untranslated) or if force retranslate is on
                    is_identical = temp == data and data.strip()
                    
                    # Always translate if force_retranslate is on OR if strings are identical (indicating untranslated content)
                    if self.force_retranslate or is_identical:
                        if is_identical:
                            logger.debug(f"Found identical string at {key_path}, will translate: '{data}'")
                        else:
                            logger.debug(f"Force retranslating string at {key_path}: '{data}'")
                    else:
                        # Skip only if it's already translated (different from source)
                        logger.debug(f"Skipping already translated key: {key_path}")
                        self.stats["current_string"] += 1
                        
                        # Update the global variable with existing translation
                        if CURRENT_LOCALE_DATA is not None:
                            try:
                                # Create nested structure in the result
                                parts = key_path.split(".")
                                current = CURRENT_LOCALE_DATA
                                for i, part in enumerate(parts[:-1]):
                                    # Handle array indices
                                    if "[" in part and "]" in part:
                                        idx_start = part.index("[")
                                        idx_end = part.index("]")
                                        array_name = part[:idx_start]
                                        idx = int(part[idx_start+1:idx_end])
                                        
                                        if array_name not in current:
                                            current[array_name] = []
                                        
                                        # Make sure the array is long enough
                                        while len(current[array_name]) <= idx:
                                            current[array_name].append({})
                                        
                                        current = current[array_name][idx]
                                    else:
                                        if part not in current:
                                            current[part] = {}
                                        current = current[part]
                                
                                # Set the value in the last part
                                last_part = parts[-1]
                                if "[" in last_part and "]" in last_part:
                                    idx_start = last_part.index("[")
                                    idx_end = last_part.index("]")
                                    array_name = last_part[:idx_start]
                                    idx = int(last_part[idx_start+1:idx_end])
                                    
                                    if array_name not in current:
                                        current[array_name] = []
                                    
                                    # Make sure the array is long enough
                                    while len(current[array_name]) <= idx:
                                        current[array_name].append(None)
                                    
                                    current[array_name][idx] = temp
                                else:
                                    current[last_part] = temp
                            except (ValueError, KeyError, IndexError) as e:
                                logger.debug(f"Error updating CURRENT_LOCALE_DATA at {key_path}: {e}")
                        
                        # Show the status update to indicate we're reusing the translation
                        self.update_status(key_path, data, temp, target_lang, skipped=True)
                        return temp
            
            # For empty strings, just return them without translation
            if not data.strip():
                return data
                
            return self.translate_text(data, target_lang, source_lang, key_path)
        elif isinstance(data, dict):
            result = {}
            for k, v in data.items():
                current_path = f"{key_path}.{k}" if key_path else k
                
                # Retrieve the existing data for this key if available
                existing_value = None
                if existing_data is not None and isinstance(existing_data, dict) and k in existing_data:
                    existing_value = existing_data[k]
                    
                # Determine if we should skip translating this branch
                should_skip = False
                if self.missing_only and existing_value is not None:
                    if not isinstance(v, dict) and not isinstance(v, list):
                        try:
                            is_string_identical = isinstance(v, str) and isinstance(existing_value, str) and v.strip() and v == existing_value
                            
                            # Skip ONLY if:
                            # 1. Not forcing retranslation AND
                            # 2. The existing value is different from the source (already translated)
                            if not self.force_retranslate and not is_string_identical:
                                should_skip = True
                                logger.debug(f"Skipping already translated key: {current_path}")
                            else:
                                if is_string_identical:
                                    logger.debug(f"Will translate identical string at {current_path}: '{v}'")
                                else:
                                    logger.debug(f"Force retranslating string at {current_path}: '{v}'")
                        except Exception as e:
                            # If there's any error determining whether to skip, don't skip
                            logger.debug(f"Error determining whether to skip {current_path}: {e}")
                            should_skip = False
                
                if should_skip:
                    result[k] = existing_value
                    
                    # Also update CURRENT_LOCALE_DATA
                    if CURRENT_LOCALE_DATA is not None:
                        try:
                            parts = current_path.split(".")
                            temp = CURRENT_LOCALE_DATA
                            for i, part in enumerate(parts[:-1]):
                                # Handle array indices
                                if "[" in part and "]" in part:
                                    idx_start = part.index("[")
                                    idx_end = part.index("]")
                                    array_name = part[:idx_start]
                                    idx = int(part[idx_start+1:idx_end])
                                    
                                    if array_name not in temp:
                                        temp[array_name] = []
                                    
                                    # Make sure the array is long enough
                                    while len(temp[array_name]) <= idx:
                                        temp[array_name].append({})
                                    
                                    temp = temp[array_name][idx]
                                else:
                                    if part not in temp:
                                        temp[part] = {}
                                    temp = temp[part]
                            
                            # Set the value in the last part
                            last_part = parts[-1]
                            if "[" in last_part and "]" in last_part:
                                idx_start = last_part.index("[")
                                idx_end = last_part.index("]")
                                array_name = last_part[:idx_start]
                                idx = int(last_part[idx_start+1:idx_end])
                                
                                if array_name not in temp:
                                    temp[array_name] = []
                                
                                # Make sure the array is long enough
                                while len(temp[array_name]) <= idx:
                                    temp[array_name].append(None)
                                
                                temp[array_name][idx] = existing_value
                            else:
                                temp[last_part] = existing_value
                        except (ValueError, KeyError, IndexError) as e:
                            logger.debug(f"Error updating CURRENT_LOCALE_DATA at {current_path}: {e}")
                        
                    continue
                
                translated_value = self.translate_nested_json(v, target_lang, source_lang, current_path, existing_value)
                
                # If we're interrupted, don't add untranslated values
                if INTERRUPT_RECEIVED and translated_value is None:
                    continue
                    
                result[k] = translated_value
                
                # Update the global variable with current progress
                if CURRENT_LOCALE_DATA is not None:
                    try:
                        # Create nested structure in the result
                        parts = current_path.split(".")
                        temp = CURRENT_LOCALE_DATA
                        for i, part in enumerate(parts[:-1]):
                            if part not in temp:
                                temp[part] = {}
                            temp = temp[part]
                        temp[parts[-1]] = result[k]
                    except (ValueError, KeyError, IndexError) as e:
                        logger.debug(f"Error updating CURRENT_LOCALE_DATA at {current_path}: {e}")
                    
            return result
        elif isinstance(data, list):
            result = []
            for i, item in enumerate(data):
                current_path = f"{key_path}[{i}]"
                
                # Retrieve the existing data for this index if available
                existing_value = None
                if existing_data is not None and isinstance(existing_data, list) and i < len(existing_data):
                    existing_value = existing_data[i]
                
                translated_item = self.translate_nested_json(item, target_lang, source_lang, current_path, existing_value)
                
                # If we're interrupted, don't add untranslated values
                if INTERRUPT_RECEIVED and translated_item is None:
                    continue
                    
                result.append(translated_item)
            return result
        else:
            return data  # Return as is for numbers, booleans, etc.
            
    def count_strings(self, data):
        """Count the total number of strings in the data structure."""
        if isinstance(data, str):
            return 1
        elif isinstance(data, dict):
            return sum(self.count_strings(v) for v in data.values())
        elif isinstance(data, list):
            return sum(self.count_strings(item) for item in data)
        else:
            return 0

class NuxtI18nConfig:
    """Class to handle Nuxt i18n configuration."""
    
    def __init__(self, project_root: Path, config_path: Optional[str] = None, locales_dir: Optional[str] = None):
        """
        Initialize with the project root path.
        
        Args:
            project_root: The root directory of the project
            config_path: Optional path to a custom nuxt.config.ts/js file
            locales_dir: Optional custom directory for locale files
        """
        self.project_root = project_root
        self.locales_dir = Path(locales_dir) if locales_dir else None
        self.config_path = self._find_nuxt_config(config_path)
        self.i18n_config = self._parse_i18n_config()
        
    def _find_nuxt_config(self, custom_config_path: Optional[str] = None) -> Optional[Path]:
        """Find the nuxt.config.ts file."""
        if custom_config_path:
            config_path = resolve_path(custom_config_path)
            if not config_path.exists():
                logger.error(f"Custom nuxt.config file not found at {config_path}")
                return None
            logger.info(f"Using custom nuxt.config file at {config_path}")
            return config_path
            
        logger.info(f"Searching for nuxt.config.ts in {self.project_root}")
        # Try both .ts and .js extensions
        for ext in [".ts", ".js"]:
            config_path = self.project_root / f"nuxt.config{ext}"
            if config_path.exists():
                logger.info(f"Found nuxt.config{ext} at {config_path}")
                return config_path
                
        logger.error("nuxt.config.ts/js not found")
        return None
        
    def _parse_i18n_config(self) -> Dict:
        """Extract i18n configuration from nuxt.config.ts."""
        if not self.config_path:
            return {}
            
        # This is a simple approach that may need refinement
        # depending on the actual structure of the nuxt.config.ts file
        try:
            content = self.config_path.read_text()
            logger.debug(f"Read nuxt.config.ts file with {len(content)} characters")
            
            # Attempt a direct approach for the known structure
            import re
            
            # Match the entire i18n configuration block
            i18n_block_pattern = r'i18n:\s*\{([\s\S]*?)\},'
            i18n_match = re.search(i18n_block_pattern, content)
            
            if i18n_match:
                i18n_block = i18n_match.group(1)
                logger.debug(f"Matched i18n block: {i18n_block}")
                
                # Extract default locale
                default_locale_pattern = r'defaultLocale:\s*[\'"]([^\'"]+)[\'"]'
                default_locale_match = re.search(default_locale_pattern, i18n_block)
                default_locale = default_locale_match.group(1) if default_locale_match else ""
                
                # Extract locales array
                locales_pattern = r'locales:\s*\[([\s\S]*?)\]'
                locales_match = re.search(locales_pattern, i18n_block)
                
                locales = []
                if locales_match:
                    locales_array = locales_match.group(1)
                    logger.debug(f"Matched locales array: {locales_array}")
                    
                    # Extract individual locale objects
                    locale_objects_pattern = r'\{\s*code:\s*[\'"]([^\'"]+)[\'"],\s*name:\s*[\'"][^\'"]+[\'"],\s*file:\s*[\'"]([^\'"]+)[\'"]'
                    locale_objects = re.finditer(locale_objects_pattern, locales_array)
                    
                    for match in locale_objects:
                        code, file = match.groups()
                        locales.append({"code": code, "file": file})
                
                logger.info(f"Found i18n config using direct pattern: defaultLocale={default_locale}, locales={locales}")
                if locales and default_locale:
                    return {
                        "locales": locales,
                        "defaultLocale": default_locale
                    }
                    
            # If the direct approach failed, try the original approach
            logger.debug("Direct pattern matching failed, trying original method")
            
            # Find i18n section
            i18n_start = content.find("i18n: {")
            if i18n_start == -1:
                # Try alternative format
                i18n_start = content.find("i18n:")
                if i18n_start == -1:
                    logger.error("i18n configuration not found in nuxt.config.ts")
                    return {}
            
            # For debugging, show a portion of the found i18n section
            debug_section = content[i18n_start:i18n_start + 200]
            logger.debug(f"Found i18n section: {debug_section}...")
                
            # Extract the i18n object (this is a simplistic approach)
            # In a real implementation, you might need a more robust parser
            i18n_section = content[i18n_start:]
            bracket_count = 0
            i18n_end = 0
            
            # Find the matching closing bracket for the i18n object
            for i, char in enumerate(i18n_section):
                if char == '{':
                    bracket_count += 1
                elif char == '}':
                    bracket_count -= 1
                    if bracket_count == 0:
                        i18n_end = i + 1
                        break
                        
            i18n_text = i18n_section[:i18n_end]
            logger.debug(f"Extracted i18n text: {i18n_text}")
            
            # Parse the extracted text to get locales and defaultLocale
            # This is a simplified implementation
            locales_start = i18n_text.find("locales: [")
            default_locale_start = i18n_text.find("defaultLocale:")
            
            locales = []
            default_locale = ""
            
            if locales_start != -1:
                locales_section = i18n_text[locales_start + len("locales: ["):]
                locales_end = locales_section.find("]")
                locales_text = locales_section[:locales_end]
                logger.debug(f"Locales text: {locales_text}")
                
                # Parse locales with improved regex pattern
                import re
                # Updated pattern to match with or without 'name' field
                locale_pattern = r'\{\s*code:\s*[\'"]([^\'"]+)[\'"],(?:\s*name:\s*[\'"][^\'"]+[\'"],)?\s*file:\s*[\'"]([^\'"]+)[\'"]'
                locale_matches = re.finditer(locale_pattern, locales_text)
                
                for match in locale_matches:
                    code, file = match.groups()
                    locales.append({"code": code, "file": file})
                    
                # If we couldn't parse any locales, try a more lenient approach
                if not locales:
                    logger.warning("Using fallback locale parsing method")
                    # Just extract code and file pairs
                    code_pattern = r'code:\s*[\'"]([^\'"]+)[\'"]'
                    file_pattern = r'file:\s*[\'"]([^\'"]+)[\'"]'
                    
                    code_matches = list(re.finditer(code_pattern, locales_text))
                    file_matches = list(re.finditer(file_pattern, locales_text))
                    
                    logger.debug(f"Found {len(code_matches)} code matches and {len(file_matches)} file matches")
                    
                    codes = [match.group(1) for match in code_matches]
                    files = [match.group(1) for match in file_matches]
                    
                    if len(codes) == len(files) and len(codes) > 0:
                        locales = [{"code": code, "file": file} for code, file in zip(codes, files)]
            
            if default_locale_start != -1:
                default_section = i18n_text[default_locale_start + len("defaultLocale:"):]
                default_match = re.search(r'[\'"]([^\'"]+)[\'"]', default_section)
                if default_match:
                    default_locale = default_match.group(1)
            
            logger.info(f"Found i18n config: defaultLocale={default_locale}, locales={locales}")
            return {
                "locales": locales,
                "defaultLocale": default_locale
            }
        except Exception as e:
            logger.error(f"Error parsing i18n configuration: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
            
    def _find_locale_file(self, file_path: str) -> Optional[Path]:
        """Find a locale file in multiple potential locations."""
        file_name = Path(file_path).name
        logger.debug(f"Looking for locale file with name: {file_name}")
        
        # List of potential locations to check
        potential_paths = []
        
        # If a custom locales directory was specified, check there first
        if self.locales_dir:
            if self.locales_dir.is_absolute():
                potential_paths.append(self.locales_dir / file_name)
            else:
                potential_paths.append(self.project_root / self.locales_dir / file_name)
        
        # Then check the standard locations
        potential_paths.extend([
            # Exact path as specified in config
            self.project_root / file_path,
            # Common i18n directory structure
            self.project_root / "i18n" / "locales" / file_name,
            # Root locales directory
            self.project_root / "locales" / file_name,
            # Just the filename in root
            self.project_root / file_name,
            # locales in current working directory
            Path.cwd() / "locales" / file_name,
        ])
        
        # Try each path and return the first one that exists
        for path in potential_paths:
            logger.debug(f"Checking if locale file exists at: {path}")
            if path.exists():
                logger.info(f"Found locale file at: {path}")
                return path
                
        # If we can't find the file, log a warning
        logger.warning(f"Could not find locale file: {file_path} in any standard location")
        logger.debug(f"Checked paths: {potential_paths}")
        
        # Return a default path where we'll create the file
        default_path = self.project_root / file_path
        logger.info(f"Will create locale file at: {default_path}")
        return default_path
        
    def get_locale_files(self) -> List[Dict]:
        """Get the list of locale files to be translated."""
        locales = self.i18n_config.get("locales", [])
        default_locale = self.i18n_config.get("defaultLocale", "")
        
        logger.debug(f"Processing locales from config: {locales}")
        logger.debug(f"Default locale: {default_locale}")
        
        # Filter out the default locale
        locale_files = [
            locale for locale in locales
            if locale.get("code") != default_locale
        ]
        
        # Find the default locale file path for use as source
        default_file = next(
            (locale.get("file") for locale in locales if locale.get("code") == default_locale),
            None
        )
        
        result = []
        if default_file:
            # Find the default locale file in potential locations
            default_file_path = self._find_locale_file(default_file)
            
            # If default file path exists, we can proceed with translations
            if default_file_path and default_file_path.exists():
                logger.info(f"Using default locale file: {default_file_path}")
                
                for locale in locale_files:
                    locale_file = locale.get("file")
                    # For target files, we'll create them even if they don't exist yet
                    locale_file_path = self._find_locale_file(locale_file)
                    
                    # Ensure the directory exists
                    locale_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    result.append({
                        "code": locale.get("code"),
                        "file": locale_file,
                        "file_path": locale_file_path,
                        "source_file": default_file_path
                    })
            else:
                logger.error(f"Default locale file not found: {default_file}")
        else:
            logger.error(f"No default locale file specified in configuration")
        
        return result

def translate_locale_files(
    project_root: str,
    formality: str = "default",
    api_key: Optional[str] = None,
    force_retranslate: bool = False,
    config_path: Optional[str] = None,
    locales_dir: Optional[str] = None,
    include_locales: Optional[List[str]] = None,
    override_default_locale: Optional[str] = None,
    output_dir: Optional[str] = None,
    dry_run: bool = False
) -> None:
    """
    Translate the locale files using DeepL API.
    
    Args:
        project_root: Path to the project root directory
        formality: DeepL formality setting (default, more, less, etc.)
        api_key: DeepL API key (if not provided, will be read from .env)
        force_retranslate: Whether to retranslate strings that are identical to source
        config_path: Optional custom path to the nuxt.config file
        locales_dir: Optional custom directory for locale files
        include_locales: Optional list of locale codes to include (only these will be translated)
        override_default_locale: Optional override for the default locale (source language)
        output_dir: Optional custom output directory for translated files
        dry_run: If True, don't actually translate or save files; just report what would be done
    """
    global CURRENT_LOCALE_DATA, CURRENT_LOCALE_PATH, INTERRUPT_RECEIVED
    
    # Set up signal handler for keyboard interrupts
    signal.signal(signal.SIGINT, signal_handler)
    
    # Load API key from environment if not provided
    if not api_key:
        load_dotenv()
        api_key = os.getenv("DEEPL_API_KEY")
        
    if not api_key:
        logger.error(f"{Fore.RED}DeepL API key not found. Please set DEEPL_API_KEY environment variable.{Style.RESET_ALL}")
        return
    
    # Convert project_root to absolute path if it's relative
    project_root_path = resolve_path(project_root)
    print_box(f"Using project root: {project_root_path}")
    logger.info(f"Using project root: {project_root_path}")
    
    # Initialize the translator and config
    translator = DeeplTranslator(api_key, formality)
    
    print(f"{Fore.CYAN}Loading Nuxt configuration...{Style.RESET_ALL}")
    config = NuxtI18nConfig(project_root_path, config_path, locales_dir)
    
    # Get locale files to translate
    locale_files = config.get_locale_files()
    
    if not locale_files:
        logger.warning(f"{Fore.YELLOW}No locale files found to translate.{Style.RESET_ALL}")
        return
    
    # Filter locales if include_locales is specified
    if include_locales:
        filtered_locale_files = []
        for locale_info in locale_files:
            if locale_info.get("code") in include_locales:
                filtered_locale_files.append(locale_info)
                
        if not filtered_locale_files:
            logger.warning(f"{Fore.YELLOW}None of the specified locales {include_locales} found in config.{Style.RESET_ALL}")
            return
            
        # Show which locales are being included
        skipped_locales = [l.get("code") for l in locale_files if l.get("code") not in include_locales]
        if skipped_locales:
            print(f"{Fore.YELLOW}Skipping locales: {', '.join(skipped_locales)}{Style.RESET_ALL}")
            
        locale_files = filtered_locale_files
    
    # Get default locale code and allow override
    default_locale = override_default_locale or config.i18n_config.get("defaultLocale", "")
    if override_default_locale:
        print(f"{Fore.CYAN}Overriding default locale: using {override_default_locale} instead of {config.i18n_config.get('defaultLocale', '')}{Style.RESET_ALL}")
    
    # Show translation summary
    target_locales = [locale_info.get("code") for locale_info in locale_files]
    print_box(f"Translating from {Fore.GREEN}{default_locale}{Style.RESET_ALL} to {Fore.CYAN}{', '.join(target_locales)}{Style.RESET_ALL}")
    
    if dry_run:
        print(f"{Fore.YELLOW}DRY RUN MODE - No files will be translated or modified{Style.RESET_ALL}")
        
    translation_stats = {
        "total_files": len(locale_files),
        "processed_files": 0,
        "total_strings": 0,
        "translated_strings": 0,
        "skipped_strings": 0
    }
    
    # Initial space for status lines
    print("\n\n\n\n")  # Reserve 4 lines for status updates
    
    try:
        # Process each locale file
        for locale_info in locale_files:
            target_code = locale_info.get("code")
            target_path = locale_info.get("file_path")
            source_path = locale_info.get("source_file")
            
            clear_lines(translator.status_lines)
            print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Processing translation for locale: {Fore.WHITE}{target_code}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print("\n\n\n\n")  # Reserve lines for status updates
            
            try:
                # Load source locale file (default locale)
                with open(source_path, "r", encoding="utf-8") as f:
                    source_data = json.load(f)
                
                # Count total strings
                string_count = translator.count_strings(source_data)
                translation_stats["total_strings"] += string_count
                
                # Set total strings count for progress tracking
                translator.stats["total_strings"] = string_count
                translator.stats["current_string"] = 0
                
                clear_lines(translator.status_lines)
                print(f"{Fore.GREEN}Found {string_count} strings to translate{Style.RESET_ALL}")
                print("\n\n\n")  # Reserve lines for status updates
                
                # Process output path - use specified output directory if provided
                if output_dir:
                    output_dir_path = resolve_path(output_dir)
                    # Create the output directory if it doesn't exist
                    output_dir_path.mkdir(parents=True, exist_ok=True)
                    # Get just the filename from the target path
                    output_filename = target_path.name
                    # Create a new path in the output directory
                    target_path = output_dir_path / output_filename
                    print(f"{Fore.CYAN}Using custom output path: {target_path}{Style.RESET_ALL}")
                
                # Abort early if this is a dry run
                if dry_run:
                    print(f"{Fore.YELLOW}DRY RUN: Would translate {string_count} strings from {source_path} to {target_path}{Style.RESET_ALL}")
                    if existing_data and missing_key_count > 0:
                        print(f"{Fore.YELLOW}DRY RUN: Would update {missing_key_count} missing or identical strings in {target_path}{Style.RESET_ALL}")
                    translation_stats["processed_files"] += 1
                    continue
                
                # Create target directory if it doesn't exist
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Load existing target file if it exists, for merging and skipping
                existing_data = {}
                use_missing_only = False  # Default to translating everything
                
                if target_path.exists():
                    try:
                        with open(target_path, "r", encoding="utf-8") as f:
                            existing_data = json.load(f)
                        
                        # Compare source and target to check for missing keys
                        missing_key_count = compare_json_structures(source_data, existing_data, source_data=source_data)
                        if missing_key_count > 0:
                            print(f"{Fore.YELLOW}Found {missing_key_count} missing keys in target file{Style.RESET_ALL}")
                            print(f"{Fore.GREEN}Will translate missing keys while preserving existing translations{Style.RESET_ALL}")
                            # Always use missing-only mode when target file exists to protect existing translations
                            use_missing_only = True
                        else:
                            # Even if no missing keys, we should still run the translation process
                            # This ensures we process all keys and don't stop prematurely
                            print(f"{Fore.GREEN}Target file has all keys from source file{Style.RESET_ALL}")
                            print(f"{Fore.GREEN}Will verify all translations are complete{Style.RESET_ALL}")
                            use_missing_only = True  # Still use missing-only to protect existing translations
                            
                        print(f"{Fore.GREEN}Loaded existing translations from {target_path}{Style.RESET_ALL}")
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse existing file {target_path}, will create new file")
                        existing_data = {}
                else:
                    print(f"{Fore.YELLOW}No existing translation file found, creating a new one{Style.RESET_ALL}")
                    # For new files, we need to translate everything
                    use_missing_only = False
                
                # Reset global tracking variables for current file
                CURRENT_LOCALE_DATA = {}
                CURRENT_LOCALE_PATH = target_path
                
                # Set up counters to track new vs. resumed translations 
                if existing_data:
                    # Initialize CURRENT_LOCALE_DATA with a copy of existing_data
                    # This ensures we don't lose any existing translations
                    CURRENT_LOCALE_DATA = json.loads(json.dumps(existing_data))
                    
                    if use_missing_only:
                        print(f"{Fore.CYAN}Running in missing-only mode - will only translate keys not present in target file{Style.RESET_ALL}")
                        if force_retranslate:
                            print(f"{Fore.YELLOW}Force retranslate mode enabled - will retranslate strings identical to source{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}Running in full-check mode - will verify all translations{Style.RESET_ALL}")
                        
                # Translate the JSON data
                clear_lines(translator.status_lines)
                print(f"\n{Fore.MAGENTA}Translating from {default_locale.upper()} to {target_code.upper()}{Style.RESET_ALL}")
                print("\n\n\n")  # Reserve lines for status updates
                
                # Update Translator class to use missing-only mode when appropriate
                translator.missing_only = use_missing_only
                translator.force_retranslate = force_retranslate
                
                translated_data = translator.translate_nested_json(
                    source_data, 
                    target_code.upper(),  # DeepL uses uppercase language codes
                    default_locale.upper(),
                    "", # Starting with empty path
                    existing_data # Pass existing data to check for already translated strings
                )
                
                # Check if we should continue or save and exit
                if INTERRUPT_RECEIVED:
                    # Use whatever we've translated so far from the CURRENT_LOCALE_DATA
                    print(f"{Fore.YELLOW}Translation interrupted. Saving partial results.{Style.RESET_ALL}")
                    
                    # We use CURRENT_LOCALE_DATA which only contains what we've actually translated
                    if CURRENT_LOCALE_DATA:
                        # If we have something in CURRENT_LOCALE_DATA, use it
                        result_data = CURRENT_LOCALE_DATA
                        
                        # Merge with existing data if needed
                        if existing_data:
                            # Create a deep copy of existing data
                            result_data = json.loads(json.dumps(existing_data))
                            
                            # For a proper merge, use a recursive merge function
                            def merge_json(source, target):
                                for key in source:
                                    if key in target:
                                        if isinstance(source[key], dict) and isinstance(target[key], dict):
                                            merge_json(source[key], target[key])
                                        else:
                                            target[key] = source[key]
                                    else:
                                        target[key] = source[key]
                                return target
                            
                            # Merge the new translations in
                            result_data = merge_json(CURRENT_LOCALE_DATA, result_data)
                    else:
                        # If CURRENT_LOCALE_DATA is empty (i.e., immediate interrupt), 
                        # keep existing translations if available
                        result_data = existing_data or {}
                    
                    # Print what's being saved
                    print(f"{Fore.YELLOW}Saving {len(CURRENT_LOCALE_DATA)} newly translated entries{Style.RESET_ALL}")
                else:
                    # Normal completion - use full translated data
                    # But make sure we don't lose any existing translations
                    if existing_data and translated_data:
                        # Merge the translated data with existing data
                        result_data = merged_translations(translated_data, existing_data)
                    else:
                        result_data = translated_data
                
                # Update stats
                translation_stats["translated_strings"] += translator.stats["current_string"]
                
                # Save the translated data
                clear_lines(translator.status_lines)
                print(f"{Fore.GREEN}Saving translated data to: {target_path}{Style.RESET_ALL}")
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                    
                # Verify the final translation has all keys by comparing with source
                if not INTERRUPT_RECEIVED:
                    missing_keys = compare_json_structures(source_data, result_data, source_data=source_data)
                    if missing_keys > 0:
                        print(f"{Fore.YELLOW}Warning: Final translation has {missing_keys} missing keys compared to source file{Style.RESET_ALL}")
                        print(f"{Fore.YELLOW}You may want to run the tool again to fill in these keys{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.GREEN}Verification successful: All keys from source file are present and translated in target file{Style.RESET_ALL}")
                
                translation_stats["processed_files"] += 1
                print(f"{Fore.GREEN}Successfully translated and saved: {target_path}{Style.RESET_ALL}")
                
                # Check if interrupt was received
                if INTERRUPT_RECEIVED:
                    break
                    
            except Exception as e:
                logger.error(f"Error processing {target_code}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                
                # Try to save progress even if an error occurred
                if CURRENT_LOCALE_DATA and target_path:
                    try:
                        with open(target_path, "w", encoding="utf-8") as f:
                            # Merge with existing data if possible
                            if existing_data:
                                def merge_json(source, target):
                                    for key in source:
                                        if key in target:
                                            if isinstance(source[key], dict) and isinstance(target[key], dict):
                                                merge_json(source[key], target[key])
                                            else:
                                                target[key] = source[key]
                                        else:
                                            target[key] = source[key]
                                    return target
                                
                                result_data = json.loads(json.dumps(existing_data))
                                result_data = merge_json(CURRENT_LOCALE_DATA, result_data)
                                json.dump(result_data, f, ensure_ascii=False, indent=2)
                            else:
                                json.dump(CURRENT_LOCALE_DATA, f, ensure_ascii=False, indent=2)
                                
                        print(f"{Fore.YELLOW}Saved partial progress despite error: {target_path}{Style.RESET_ALL}")
                    except Exception as save_err:
                        logger.error(f"Failed to save partial progress: {save_err}")
        
        # Show translation statistics
        clear_lines(translator.status_lines)
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Translation Statistics{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Files processed:     {translation_stats['processed_files']}/{translation_stats['total_files']}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Strings translated:  {translation_stats['translated_strings']}/{translation_stats['total_strings']}{Style.RESET_ALL}")
        
        success_rate = (translation_stats['translated_strings'] / translation_stats['total_strings']) * 100 if translation_stats['total_strings'] > 0 else 0
        print(f"{Fore.GREEN}Success rate:        {success_rate:.2f}%{Style.RESET_ALL}")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        # Always try to save progress on any exception
        save_current_progress()
    finally:
        # Reset global variables
        CURRENT_LOCALE_DATA = None
        CURRENT_LOCALE_PATH = None

def compare_json_structures(source: Any, target: Any, path: str = "", source_data=None) -> int:
    """
    Compare two JSON structures to find missing keys in target.
    Returns the count of missing keys.
    
    Args:
        source: The source JSON structure to compare against
        target: The target JSON structure being checked for missing keys
        path: Current path in the JSON structure (for recursive calls)
        source_data: The original complete source data (to check for untranslated strings)
    """
    if path == "":  # Only at the root level
        # Initialize with a deep comparison at the root level
        source_data = source if source_data is None else source_data
        return compare_json_structures(source, target, "root", source_data=source_data)
    
    missing_count = 0
    
    if isinstance(source, dict):
        if not isinstance(target, dict):
            # If source is a dict but target is not, the entire structure is missing
            return count_strings_in_structure(source)
            
        for key, value in source.items():
            current_path = f"{path}.{key}" if path != "root" else key
            
            if key not in target:
                # If key is missing in target, count all strings in this branch
                missing_count += count_strings_in_structure(value)
            else:
                # Recursively check this branch
                missing_count += compare_json_structures(value, target[key], current_path, source_data=source_data)
                
    elif isinstance(source, list):
        if not isinstance(target, list):
            # If source is a list but target is not, the entire structure is missing
            return count_strings_in_structure(source)
            
        # For lists, we can't easily track by index since translations might 
        # result in different orders, so we count any length differences
        if len(source) > len(target):
            # Roughly estimate missing items based on length difference
            for i in range(len(target), len(source)):
                missing_count += count_strings_in_structure(source[i])
        
        # Also check the common items
        for i in range(min(len(source), len(target))):
            current_path = f"{path}[{i}]"
            missing_count += compare_json_structures(source[i], target[i], current_path, source_data=source_data)
            
    elif isinstance(source, str):
        # We consider a string missing or untranslated if:
        # 1. Target is not a string OR
        # 2. Target is an empty string OR
        # 3. Target string is identical to source (likely untranslated)
        if not isinstance(target, str) or not target.strip():
            missing_count += 1
        # Check if the target string is identical to the source string
        # This typically indicates it hasn't been translated
        elif target == source and source.strip():  # Only count non-empty strings
            missing_count += 1
            # Debugging output to show the untranslated string
            logger.debug(f"Found untranslated string at {path}: {source}")
            
    return missing_count

def count_strings_in_structure(data: Any) -> int:
    """Count the number of strings in a nested structure."""
    if isinstance(data, str):
        return 1
    elif isinstance(data, dict):
        return sum(count_strings_in_structure(v) for v in data.values())
    elif isinstance(data, list):
        return sum(count_strings_in_structure(item) for item in data)
    else:
        return 0

def merged_translations(new_data, existing_data):
    """
    Merge new translations with existing data, prioritizing new translations
    except where they would overwrite non-empty existing translations.
    """
    result = {}
    
    if isinstance(new_data, dict) and isinstance(existing_data, dict):
        # Process all keys in both new and existing data
        all_keys = set(list(new_data.keys()) + list(existing_data.keys()))
        
        for key in all_keys:
            if key in new_data and key in existing_data:
                # Both have this key - recursively merge
                result[key] = merged_translations(new_data[key], existing_data[key])
            elif key in new_data:
                # Only in new data
                result[key] = new_data[key]
            else:
                # Only in existing data
                result[key] = existing_data[key]
                
    elif isinstance(new_data, list) and isinstance(existing_data, list):
        # For lists, prefer the list with more items
        if len(new_data) >= len(existing_data):
            result = new_data
        else:
            result = existing_data
    else:
        # For simple values (strings, etc.), prefer new_data unless it's empty
        if isinstance(new_data, str) and not new_data.strip() and isinstance(existing_data, str) and existing_data.strip():
            # If new data is empty but existing data isn't, keep existing
            result = existing_data
        else:
            # Otherwise prefer the new data
            result = new_data
            
    return result

def main():
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description="DeepL Translator for Vue/Nuxt i18n - Automatically translate locale files using DeepL API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
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
"""
    )
    
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"DeepL Translator for Vue i18n v{__version__}",
        help="Show the version number and exit"
    )
    
    parser.add_argument(
        "--root", "-r",
        type=str,
        default=".",
        help="Project root directory (default: current directory)"
    )
    
    parser.add_argument(
        "--formality", "-f",
        type=str,
        choices=["default", "more", "less", "prefer_more", "prefer_less"],
        default="default",
        help="Translation formality (default: default)"
    )
    
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        help="DeepL API key (otherwise read from DEEPL_API_KEY in .env)"
    )
    
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging to diagnose translation issues"
    )
    
    parser.add_argument(
        "--force-retranslate", 
        action="store_true",
        help="Force retranslation of strings that appear identical to source"
    )
    
    parser.add_argument(
        "--config-path", "-c",
        type=str,
        help="Custom path to the nuxt.config.ts/js file"
    )
    
    parser.add_argument(
        "--locales-dir", "-l",
        type=str,
        help="Custom directory for locale files (relative to project root or absolute path)"
    )
    
    parser.add_argument(
        "--include-locale",
        type=str,
        action="append",
        help="Only translate the specified locale(s). Can be used multiple times. If not specified, translates all locales defined in config."
    )
    
    parser.add_argument(
        "--override-default-locale",
        type=str,
        help="Override the default locale (source language) specified in the config"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        help="Custom output directory for translated files"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually translate or save files; just report what would be done"
    )
    
    args = parser.parse_args()
    
    # Set up debug logging if requested
    if args.debug:
        console_handler.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        print(f"{Fore.CYAN}Debug logging enabled{Style.RESET_ALL}")
    
    print_box("DeepL Translator for Vue i18n", Fore.BLUE)
    
    try:
        translate_locale_files(
            project_root=args.root,
            formality=args.formality,
            api_key=args.api_key,
            force_retranslate=args.force_retranslate,
            config_path=args.config_path,
            locales_dir=args.locales_dir,
            include_locales=args.include_locale,
            override_default_locale=args.override_default_locale,
            output_dir=args.output_dir,
            dry_run=args.dry_run
        )
        
        if not INTERRUPT_RECEIVED:
            print_box("Translation process completed", Fore.GREEN)
        else:
            print_box("Translation process interrupted but partial results saved", Fore.YELLOW)
    except KeyboardInterrupt:
        save_current_progress()
        print_box("Translation process interrupted but partial results saved", Fore.YELLOW)

if __name__ == "__main__":
    main() 