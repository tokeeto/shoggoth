"""
CelaenoProvider: submits exports to Shoggoth Cloud / Library of Celaeno
(celaeno.cards) for review, the only CloudProvider implementation today. An
admin marks a project "Published" (catalogue/frontpage visibility) from the
website once it's been vetted -- this provider no longer publishes anything
itself. See CLOUD.md for the full desktop<->backend contract this wraps.
"""
from pathlib import Path

from shoggoth.cloud.provider import CloudProvider
from shoggoth.files import safe_filename
from shoggoth.i18n import tr


def _image_remote_name(card, path):
    """The server's images/<encounter-set>/<file> layout groups each card's
    exported image(s) under its encounter set's name, matching how the card
    list already groups cards -- flat (no subfolder) for player cards, which
    have no encounter set."""
    if card.encounter:
        return f'{safe_filename(card.encounter.name)}/{Path(path).name}'
    return Path(path).name


def _card_manifest_image_path(card, path):
    """Like _image_remote_name, but for CardEntry.front/back_image_path
    rather than an upload's remote_name: those need the full path relative
    to the entry's own root -- matching ProjectFile.path's convention -- not
    just the filename-under-encounter-set that _image_remote_name returns,
    which omits the "images/" kind prefix because upload_file/
    upload_translation_file add that separately from the URL's own `kind`
    segment."""
    return f'images/{_image_remote_name(card, path)}'


def _build_card_manifest(cards, card_faces):
    """The id -> name/encounter-set/image-path mapping the cloud review
    browser needs (see CardEntry in shoggoth_web's models.py) -- one entry
    per card, regardless of whether it happens to have an exported image this
    run (a card manifest sync always replaces the whole set server-side, so a
    card missing its images here would otherwise silently vanish from a
    previously-synced manifest).

    Deduped by card.id (last one in `cards` wins) before returning -- the
    server's own CardEntry rows are unique per (project/translation, card_id)
    and would otherwise reject two entries for the same id in one manifest."""
    manifest = {}
    for card in cards:
        faces = card_faces.get(card.id, {})
        front, back = faces.get('front'), faces.get('back')
        manifest[card.id] = {
            'card_id': card.id,
            'name': card.name,
            'encounter_set_id': card.encounter.id if card.encounter else None,
            'encounter_set_name': card.encounter.name if card.encounter else None,
            'front_image_path': _card_manifest_image_path(card, front) if front else None,
            'back_image_path': _card_manifest_image_path(card, back) if back else None,
            'sort_key': str(card.project_number),
        }
    return list(manifest.values())


class CelaenoProvider(CloudProvider):
    key = 'celaeno'
    display_name = 'Library of Celaeno'

    def is_available(self, config) -> bool:
        return bool(config.get('Shoggoth', 'publish_token', '')) and config.getboolean(
            'Shoggoth', 'publish_has_access', False
        )

    def run(self, parent, project, cards, card_faces, produced, tts_result, settings):
        """Upload this entry's window of produced content to Shoggoth Cloud
        for review. Returns a summary message, or None if the user
        cancelled from the progress dialog."""
        import shoggoth
        from shoggoth.ui.cloud.publish_dialog import PublishProgressDialog

        config = shoggoth.app.config
        base_url = config.get('Shoggoth', 'publish_base_url', '')
        token = config.get('Shoggoth', 'publish_token', '')
        if not token or not config.getboolean('Shoggoth', 'publish_has_access', False):
            raise RuntimeError(tr("PUBLISH_NOT_LOGGED_IN"))

        # Only synced when Images actually produced something in this
        # entry's window -- syncing a manifest without image paths would
        # just overwrite a previously-synced one with a strictly worse
        # (image-less) version, since a sync always replaces the whole set.
        card_manifest = (
            _build_card_manifest(cards, card_faces) if settings.get('images') and card_faces else None
        )

        files = []  # list of (kind, local_path, remote_name)
        if settings.get('images'):
            files += [('images', p, _image_remote_name(card, p)) for card, p in produced['images']]
        if settings.get('pdf'):
            files += [('pdf', p, Path(p).name) for p in produced['pdf']]
        if settings.get('guides'):
            files += [('pdf', p, Path(p).name) for p in produced['guides']]
        if settings.get('arkham_build'):
            files += [('data', p, Path(p).name) for p in produced['data']]
        if settings.get('tts') and tts_result:
            files += [('tts', p, Path(p).name) for p in tts_result['image_paths']]

        # Dedupe (e.g. a shared generic-back image showing up from both the
        # Images and TTS entries), preserving first-seen order.
        seen = set()
        unique_files = []
        for kind, path, remote_name in files:
            fkey = (kind, path)
            if fkey not in seen:
                seen.add(fkey)
                unique_files.append((kind, path, remote_name))

        # When the active project is a translation view (opened via "Load
        # Translation"), publish everything into that translation's own
        # cloud subfolder instead of the base project's -- see
        # PublishProgressDialog's docstring.
        translation = getattr(project, '_translation', None)

        dialog = PublishProgressDialog(
            project, base_url, token, unique_files,
            tts_result if settings.get('tts') else None, parent,
            translation=translation,
            card_manifest=card_manifest,
        )
        dialog.start()
        dialog.exec()
        return dialog.summary()
