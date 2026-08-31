"""
Compact editor structural stylesheet for the card/face editor pane.

No custom color palette — every rule below is sizing/spacing/shape only (font-size,
padding, border-radius, etc.) and colors are left to the application's native Qt theme.
Where a border is structurally needed (the Numbers mini-panel, band hairlines), the
widgets use native QFrame shapes (Sunken/StyledPanel) in compact_widgets.py instead of
hardcoded colors, so they follow whatever palette the app is actually running under.

Applied by calling ``widget.setStyleSheet(EDITOR_QSS)`` on the CardEditor root widget only —
Qt stylesheets cascade to children, so this never leaks into the file-tree sidebar or the
preview dock elsewhere in the main window.
"""

EDITOR_QSS = """
QLabel[role="band-label"], QToolButton[role="band-label"] {
    font-size: 9.5px;
    font-weight: 600;
}

QLabel[role="band-hint"] {
    font-size: 9.5px;
}

QFrame[role="hairline"] {
    max-height: 1px;
    min-height: 1px;
}

QFrame[role="divider"] {
    max-width: 1px;
    min-width: 1px;
}

QLabel[role="field-label"] {
    font-size: 9px;
    font-weight: 600;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    padding: 6px 8px;
    font-size: 12.5px;
}

QCheckBox {
    spacing: 6px;
}

QPushButton[role="stepper-btn"] {
    padding: 0px;
    font-weight: 600;
}

QLineEdit[role="stepper-value"] {
    padding: 2px;
    font-weight: 600;
    qproperty-alignment: AlignCenter;
}

QPushButton[chip="tag"] {
    background: palette(button);
    border: 1px solid palette(mid);
    border-radius: 5px;
    font-size: 11px;
    padding: 4px 9px;
}

QPushButton[chip="tag-add"], QPushButton[chip="tag-ghost"] {
    background: transparent;
    border: 1px dashed palette(mid);
    border-radius: 5px;
    font-size: 11px;
    padding: 4px 9px;
}

QPushButton[role="segment"] {
    font-size: 11px;
    font-weight: 600;
    padding: 5px 14px;
}

/* Flat dropdown: no box/border, just the current value + a small native arrow —
   used where a full combo-box frame wastes width (e.g. the per-icon skill counts).
   Deliberately does NOT style the ::drop-down/::down-arrow subcontrols — on this
   Qt style (Fusion) doing so drops the arrow glyph entirely instead of repositioning
   it, so the native drop-down box (unstyled) is what actually draws the arrow. */
QComboBox[role="flat-combo"] {
    border: none;
    background: transparent;
    padding: 2px 0px 2px 4px;
    font-weight: 600;
}

QComboBox[role="flat-combo"]:on {
    background: transparent;
}

QPushButton[role="unique-btn"] {
    font-size: 13px;
    padding: 0px;
}

QPushButton[role="per-btn"] {
    font-size: 10px;
    font-weight: 600;
    padding: 0px;
}

/* Selected-state feedback uses the OS theme's own highlight color (not a custom
   palette) — checkable segments are otherwise indistinguishable when checked.
   (Class chips use their own semantic per-class colors set directly, not this rule.) */
QPushButton[role="segment"]:checked, QPushButton[role="unique-btn"]:checked,
QPushButton[role="per-btn"]:checked {
    background: palette(highlight);
    color: palette(highlighted-text);
}
"""
