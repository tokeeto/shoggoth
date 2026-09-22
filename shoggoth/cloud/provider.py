"""
CloudProvider: the interface a cloud publish backend implements to plug into
the export entry system (a 'publish' entry's settings carry a `provider` key
resolved through `shoggoth.cloud.registry`).

There's only one real implementation today (`shoggoth.cloud.celaeno.
CelaenoProvider`) and no dynamic loading of third-party providers yet -- this
class exists to give that one implementation a well-defined shape so a second
provider is additive later rather than a rewrite.
"""


class CloudProvider:
    key = None            # stable id, stored in an entry's settings['provider']
    display_name = None   # shown in the "Add Entry" menu ("Publish to {display_name}")

    # Content kinds this provider can selectively include when publishing --
    # drives the generic per-kind checkboxes in ui/cloud/entry_widget.py.
    content_kinds = ('images', 'pdf', 'tts', 'guides', 'arkham_build')

    def is_available(self, config) -> bool:
        """Whether this provider should be offered at all right now (e.g.
        logged in with access) -- `config` is `shoggoth.app.config`."""
        raise NotImplementedError

    def default_settings(self) -> dict:
        return {'provider': self.key, **{kind: True for kind in self.content_kinds}}

    def run(self, parent, project, cards, card_faces, produced, tts_result, settings):
        """Execute this provider's publish flow for one 'publish' entry.

        `cards`/`card_faces` are what the 'images' entries run since the
        previous publish entry (or run start) contributed; `produced` is the
        matching {'images', 'pdf', 'data', 'guides'} -> local paths produced
        in that same window; `tts_result` is the most recent TTS entry's
        result in that window, or None. `settings` is this entry's own
        settings dict (includes `provider` plus this provider's own fields).

        May open Qt UI (a progress dialog) and block until it's done. Returns
        a summary message, or None if the user cancelled. Raises on failure.
        """
        raise NotImplementedError
