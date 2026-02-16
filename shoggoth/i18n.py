"""
Internationalization (i18n) module for Shoggoth.
Provides translation support for the user interface.
"""
import json
from pathlib import Path
from typing import Optional

# Directory containing translation files
TRANSLATIONS_DIR = Path(__file__).parent / "translations"

# Currently loaded translations
_current_language = "en"
_translations: dict = {}


def get_available_languages() -> dict[str, str]:
    """
    Get all available languages.
    
    Returns:
        Dictionary mapping language codes to display names.
    """
    languages = {}
    
    if TRANSLATIONS_DIR.exists():
        for file in TRANSLATIONS_DIR.glob("*.json"):
            lang_code = file.stem
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    lang_name = data.get("_language_name", lang_code)
                    languages[lang_code] = lang_name
            except (json.JSONDecodeError, IOError):
                languages[lang_code] = lang_code
    
    # Ensure English is always available
    if "en" not in languages:
        languages["en"] = "English"
    
    return languages


def load_language(lang_code: str) -> bool:
    """
    Load a language file.
    
    Args:
        lang_code: Language code (e.g., 'en', 'es')
    
    Returns:
        True if successful, False otherwise
    """
    global _current_language, _translations
    
    lang_file = TRANSLATIONS_DIR / f"{lang_code}.json"
    
    if not lang_file.exists():
        # Fallback to English if language file not found
        _current_language = "en"
        _translations = {}
        return lang_code == "en"
    
    try:
        with open(lang_file, 'r', encoding='utf-8') as f:
            _translations = json.load(f)
            _current_language = lang_code
            return True
    except (json.JSONDecodeError, IOError):
        _current_language = "en"
        _translations = {}
        return False


def get_current_language() -> str:
    """Get the current language code."""
    return _current_language


def tr(text: str, **kwargs) -> str:
    """
    Translate a text string.
    
    Args:
        text: The original English text to translate
        **kwargs: Format arguments for string interpolation
    
    Returns:
        Translated text, or original text if no translation found
    """
    # Get translation, fallback to original text if not found
    translated = _translations.get(text, text)
    
    if kwargs:
        try:
            return translated.format(**kwargs)
        except KeyError:
            return translated
    
    return translated


def _(text: str, **kwargs) -> str:
    """
    Shorthand alias for tr().
    
    Args:
        text: The original English text to translate
        **kwargs: Format arguments for string interpolation
    
    Returns:
        Translated text
    """
    return tr(text, **kwargs)
