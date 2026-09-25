import os

import streamlit.components.v1 as components

_component = components.declare_component('sql_editor', path=os.path.dirname(os.path.abspath(__file__)))


def sql_editor(value, version, tab, words_url=None, extra_words=None, height=300, key=None):
    """Ace-based SQL editor. Returns None until the user edits, then a dict:
    {text, version, tab, run, selection, nonce}. `run` is True when Ctrl+Enter was pressed."""
    return _component(value=value, version=version, tab=tab, words_url=words_url,
                      extra_words=extra_words or [], height=height, key=key, default=None)
