"""
Content-area switching: one show_* function per element type.

Every view switch shares the same choreography — activate the element's
project, record navigation, tear down the old editor, remember the
selection, toggle the preview docks, and mount the new editor — handled
by _begin_view()/_mount(); the individual functions only contribute what
differs per view.
"""
from PySide6.QtWidgets import QScrollArea, QWidget

from shoggoth.i18n import tr
from shoggoth.ui.card_editor import CardEditor
from shoggoth.ui.encounter_editor import EncounterSetEditor


def clear_editor(window):
    """Clear and cleanup the current editor"""
    # Clear all widgets in content layout
    while window.content_layout.count():
        item = window.content_layout.takeAt(0)
        widget = item.widget()
        if widget:
            # Call cleanup if the widget has it (recursively for nested widgets)
            _cleanup_widget(widget)
            widget.setParent(None)
            widget.deleteLater()


def _cleanup_widget(widget):
    """Recursively cleanup a widget and its children"""
    # Check if this widget has cleanup method
    if hasattr(widget, 'cleanup'):
        try:
            widget.cleanup()
        except Exception as e:
            print(f"Error during widget cleanup: {e}")

    # Recursively cleanup children
    for child in widget.findChildren(QWidget):
        if hasattr(child, 'cleanup'):
            try:
                child.cleanup()
            except Exception as e:
                print(f"Error during child cleanup: {e}")


def _begin_view(window, project, nav_type, nav_id, remember=True):
    """Common preamble for every view switch"""
    window.file_browser.set_active_project(project)
    window.nav.push(nav_type, nav_id)
    clear_editor(window)
    if remember:
        window.session.set_last_selected(nav_id, nav_type)


def _mount(window, widget, scroll=True):
    """Add a widget to the content area, optionally wrapped in a scroll area"""
    if scroll:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        widget = area
    window.content_layout.addWidget(widget)


def show_card(window, card):
    """Display a card in the card editor with live preview"""
    _begin_view(window, card.project, 'card', card.id)

    window.current_card = card
    window.current_editor = None

    # Update file monitoring for this card's dependencies
    if window.card_file_monitor:
        card_files = window.card_file_monitor.get_card_file_dependencies(card)
        window.card_file_monitor.set_card_files(card_files)

    editor = CardEditor(card)
    window.current_editor = editor

    # Connect data change signal to debounced preview update
    editor.data_changed.connect(window.schedule_preview_update)

    # Wire renderer helpers into the illustration widgets
    window.preview.connect_illustration_widgets(editor)

    # Show preview dock
    window.preview_dock.show()
    window.toggle_preview_action.setChecked(True)

    # Enter translation mode if this card belongs to a translation project
    if card.project.data.get('project'):
        editor.enter_translation_mode()

    _mount(window, editor)

    # Update preview
    window.preview.render_current_sync()


def show_encounter(window, encounter):
    """Display an encounter set in the editor"""
    _begin_view(window, encounter.project, 'encounter', encounter.id)

    # Hide preview for non-card views
    window.preview_dock.hide()
    window.guide_preview_dock.hide()

    editor = EncounterSetEditor(encounter, window.card_renderer)
    editor.card_clicked.connect(window.show_card)
    _mount(window, editor)

    window.status_bar.showMessage(tr("STATUS_EDITING_ENCOUNTER_SET").format(name=encounter.name))


def show_project(window, project):
    """Display project editor"""
    _begin_view(window, project, 'project', project.file_path, remember=False)

    # Hide preview for non-card views
    window.preview_dock.hide()
    window.guide_preview_dock.hide()
    window.toggle_preview_action.setChecked(False)

    from shoggoth.ui.project_editor import ProjectEditor
    editor = ProjectEditor(project, window.card_renderer)
    _mount(window, editor)

    window.status_bar.showMessage(tr("STATUS_EDITING_PROJECT").format(name=project['name']))


def show_guide(window, guide):
    """Display guide editor"""
    _begin_view(window, guide.project, 'guide', guide.id)

    # Switch docks: hide card preview, show guide preview
    window.preview_dock.hide()
    window.guide_preview_widget.cleanup()
    window.guide_preview_widget.set_guide(guide)
    window.guide_preview_dock.show()

    # Require Prince for guide preview and PDF export
    from shoggoth.pdf_exporter import check_prince_installed
    if not check_prince_installed():
        from shoggoth.ui.main_window import exports
        exports.open_prince_installer(window)

    from shoggoth.ui.guide_editor import GuideEditor
    editor = GuideEditor(guide)
    editor.guide_content_changed.connect(window.guide_preview_widget.schedule_render)
    _mount(window, editor, scroll=False)

    window.current_guide = guide
    window.current_guide_editor = editor


def show_locations(window, encounter_set):
    """Display location connection editor for an encounter set"""
    _begin_view(window, encounter_set.project, 'locations', encounter_set.id)

    # Hide preview for non-card views
    window.preview_dock.hide()
    window.guide_preview_dock.hide()

    from shoggoth.ui.location_view import LocationViewWidget
    window.location_view = LocationViewWidget(encounter_set, window.card_renderer)
    window.location_view.card_selected.connect(
        lambda card: (window.show_card(card), window.select_item_in_tree(card.id))
    )
    window.location_view.location_view.connections_changed.connect(window.on_location_connections_changed)
    _mount(window, window.location_view, scroll=False)

    window.status_bar.showMessage(tr("STATUS_EDITING_LOCATIONS").format(name=encounter_set.name))
